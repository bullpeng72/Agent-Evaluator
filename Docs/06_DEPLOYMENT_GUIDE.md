# 🚀 배포 가이드

CI/CD 통합 및 프로덕션 배포 전략

# Deployment Guide

## 목차

  1. [개요](<#개요>)
  2. [Prerequisites](<#prerequisites>)
  3. [Installation](<#installation>)
  4. [Environment Setup](<#environment-setup>)
  5. [CI/CD Integration](<#cicd-integration>)
  6. [Docker Deployment](<#docker-deployment>)
  7. [Production Configuration](<#production-configuration>)
  8. [Monitoring & Logging](<#monitoring-logging>)
  9. [Security](<#security>)
  10. [Performance Optimization](<#performance-optimization>)
  11. [Troubleshooting](<#troubleshooting>)
  12. [Maintenance](<#maintenance>)
  13. [💻 개발자 가이드 (Developer Guide)](<#dev-guide>)
     * [13.1 배포 자동화](<#dev-deployment-automation>)
     * [13.2 환경별 배포 전략](<#dev-environment-strategy>)
     * [13.3 롤백 및 복구](<#dev-rollback>)
     * [13.4 배포 디버깅](<#dev-debugging>)
     * [13.5 성능 튜닝](<#dev-optimization>)

* * *

## 개요

### Agent Evaluator란?

**Agent Evaluator** 는 AI 에이전트의 성능을 평가하고 모니터링하는 프레임워크입니다. 프로덕션 환경에서 에이전트의 품질을 보장하고, CI/CD 파이프라인에 통합하여 자동화된 품질 게이트를 구현할 수 있습니다.

### Deployment 시나리오

#### 1\. Local Development

  * 개발자 개인 환경
  * 빠른 실험과 반복
  * 느슨한 threshold

#### 2\. CI/CD Pipeline

  * GitLab CI, Jenkins 등
  * 자동화된 품질 게이트
  * 배포 전 검증

#### 3\. Production Monitoring

  * 실시간 성능 모니터링
  * Dashboard 통합
  * 알림 및 보고

* * *

## Prerequisites

### System Requirements

**최소 사양** : - Python: 3.8+ - RAM: 2GB+ - Disk: 1GB+ (로그 및 결과 저장)

**권장 사양** : - Python: 3.11+ (실제 프로젝트는 Python 3.11 기준) - RAM: 4GB+ - Disk: 5GB+ (대량 평가 및 히스토리)

### Dependencies

**Core Dependencies** (필수):
```json
    [](<#cb1-1>)# 데이터 처리
    [](<#cb1-2>)numpy>=1.20.0
    [](<#cb1-3>)pandas>=1.3.0
    [](<#cb1-4>)
    [](<#cb1-5>)# 웹 대시보드 (FastAPI)
    [](<#cb1-6>)fastapi>=0.110.0
    [](<#cb1-7>)uvicorn[standard]>=0.29.0
    [](<#cb1-8>)
    [](<#cb1-11>)# 환경 변수 관리
    [](<#cb1-12>)python-dotenv>=1.0.0
```

**고급 통합 클래스**

평가 클래스를 사용하면 Layer 1/2/3 메트릭을 자동으로 추적할 수 있습니다:

  * `CrewAIEvaluator` \- Agent Coordination 자동 추적
  * `LangChainEvaluator` \- Tool Selection 자동 추적
  * `LangGraphEvaluator` \- Workflow Execution 자동 추적
  * `AutoGenEvaluator` \- 에이전트 상호작용 추적

자세한 내용은 [프레임워크 통합 가이드](<FRAMEWORK_INTEGRATION.html>)를 참고하세요.

**Framework Integration** (선택 - 사용하는 프레임워크만 설치):
```bash
    [](<#cb2-1>)# LangChain 통합
    [](<#cb2-2>)pip install langchain>=1.0.0
    [](<#cb2-3>)pip install langchain-core>=1.0.0
    [](<#cb2-4>)pip install langchain-community>=1.0.0
    [](<#cb2-5>)
    [](<#cb2-6>)# LangGraph 통합
    [](<#cb2-7>)pip install langgraph>=1.0.0
    [](<#cb2-8>)
    [](<#cb2-9>)# CrewAI 통합
    [](<#cb2-10>)pip install crewai>=1.0.0
    [](<#cb2-11>)
    [](<#cb2-12>)
    [](<#cb2-13>)# AutoGen 통합
    [](<#cb2-14>)pip install autogen-agentchat>=0.4.0 autogen-core>=0.4.0
```

**Advanced Metrics** (선택 - Layer 3 고급 메트릭 사용 시):
```bash
    [](<#cb3-1>)# DeepEval - G-Eval, Hallucination, Toxicity, Bias 탐지
    [](<#cb3-2>)pip install deepeval>=0.20.0
    [](<#cb3-3>)
    [](<#cb3-4>)# Ragas - RAG 시스템 평가
    [](<#cb3-5>)pip install ragas>=0.4.0
    [](<#cb3-6>)
    [](<#cb3-7>)# LangChain OpenAI (DeepEval, Ragas 의존성)
    [](<#cb3-8>)pip install langchain-openai>=1.0.0
    [](<#cb3-9>)
    [](<#cb3-10>)# Datasets (Ragas 의존성)
    [](<#cb3-11>)pip install "datasets>=4.0.0,<6.0.0"
    [](<#cb3-12>)
    [](<#cb3-13>)# LangSmith (선택 - 프로덕션 추적)
    [](<#cb3-14>)pip install langsmith>=0.1.0
```

**Korean RAG Dataset Generator** (선택):
```bash
    [](<#cb4-1>)# PDF 처리
    [](<#cb4-2>)pip install pypdf>=3.0.0
    [](<#cb4-3>)# 또는 pdfplumber>=0.10.0  # 더 정확한 추출
    [](<#cb4-4>)
    [](<#cb4-5>)# OpenAI API
    [](<#cb4-6>)pip install openai>=1.0.0
```

### API Keys

**OpenAI API** (선택): - DeepEval, Ragas, 일부 고급 메트릭 사용 시 필요 - Layer 1 (Native Metrics)만 사용 시 불필요
```bash
    [](<#cb5-1>)export OPENAI_API_KEY='your-api-key-here'
```

**기타 LLM API** (선택): - Anthropic Claude API - Cohere API - 자체 호스팅 모델

* * *

## Installation

### Method 1: From Source (현재 프로젝트 방식)
```bash
    [](<#cb6-1>)# Repository clone
    [](<#cb6-2>)# 프로젝트 디렉토리로 이동
    [](<#cb6-3>)cd Agent_Evaluator
    [](<#cb6-4>)
    [](<#cb6-5>)# Conda 가상환경 생성 (권장 - Python 3.11)
    [](<#cb6-6>)conda create --name Evaluator python=3.11
    [](<#cb6-7>)conda activate Evaluator
    [](<#cb6-12>)
    [](<#cb6-13>)# 의존성 설치
    [](<#cb6-14>)pip install -r requirements.txt
```

### Method 2: 최소 설치 (Native Metrics만 사용)
```bash
    [](<#cb7-1>)# Core dependencies만 설치
    [](<#cb7-2>)pip install agent-evaluator[serve]
```

### Method 3: 완전 설치 (모든 기능 사용)
```bash
    [](<#cb8-1>)# 모든 의존성 설치
    [](<#cb8-2>)pip install -r requirements.txt
```

### Verification

설치 확인:
```python
    [](<#cb9-1>)# Python 버전 확인
    [](<#cb9-2>)python --version  # Python 3.11+ 권장
    [](<#cb9-3>)
    [](<#cb9-4>)# 주요 모듈 import 확인
    [](<#cb9-5>)python -c "import agent_evaluator; from agent_evaluator.serve import server; print('Installation successful!')"
    [](<#cb9-6>)
    [](<#cb9-7>)# 대시보드 실행 테스트
    [](<#cb9-8>)agent-eval dashboard
```

### Project Structure

v0.6.0 기준 프로젝트는 4개의 독립적인 컴포넌트로 구성됩니다:

#### 1\. 📦 agent_evaluator/ - Core Python Package

**목적** : PyPI 배포 가능한 핵심 평가 패키지

**설치** : `pip install agent-evaluator`
```python
    agent_evaluator/
    ├── __init__.py                     # Package entry point
    │                                   # from agent_evaluator import PerformanceMonitor
    │
    ├── core/                           # 📊 핵심 평가 엔진
    │   ├── agent_evaluator.py          # PerformanceMonitor + 16개 트래커
    │   │                               # - Layer 1 메트릭: TCR, Accuracy, Hallucination, Quality, Latency, TokenEconomy
    │   │                               # - Layer 2 에이전틱: Tool Call, Retry, Tool Selection, Coordination, Workflow
    │   │                               # - Layer 2 보안: Input Sanitization, Output Leakage, Authorization, Privilege, Attack
    │   └── hybrid_monitor.py           # HybridPerformanceMonitor 클래스
    │                                   # - Layer 3 고급 메트릭 (DeepEval, Ragas 통합)
    │
    ├── integrations/                   # 🔌 Framework 통합
    │   ├── crewai_integration.py       # CrewAI → Agent Coordination 자동 추적
    │   ├── langchain_integration.py    # LangChain → Tool Selection 자동 추적
    │   ├── langgraph_integration.py    # LangGraph → Workflow Execution 자동 추적
    │   └── autogen_integration.py      # AutoGen → Agent Coordination 자동 추적
    │
    ├── datasets/                       # 📚 Dataset 관리
    │   └── korean_rag_dataset_generator.py  # PDF → Korean Golden Dataset 자동 생성
    │                                   # - 한국어/영어 지원
    │                                   # - Question-Answer-Context 트리플 생성
    │
    ├── utils/                          # 🛠️ 유틸리티
    │   ├── path_helpers.py             # Zero Configuration 경로 탐지
    │   │                               # - find_project_root()
    │   │                               # - get_evaluation_results_dir()
    │   ├── data_registry.py            # 평가 결과 데이터 레지스트리
    │   ├── dashboard_integration.py    # Dashboard 저장 경로 헬퍼
    │   └── transparency_manager.py # TestTransparencyManager 클래스 (프로덕션)
    │                                   # - 이상치 탐지, Traces, Audit Log
    │
    ├── helpers/                        # 📝 Helper 클래스
    │   └── taskresult_helpers.py       # create_taskresult() 헬퍼
    │                                   # - 점수 자동 계산
    │
    └── reporting/                      # 📄 보고서
        └── comprehensive_report.py     # ComprehensiveReportGenerator 클래스
                                        # - HTML/텍스트 종합 보고서 생성
```

#### 2\. 📚 Evaluator_Examples/ - Examples & Tutorials

**목적** : 실행 가능한 예제 코드 모음

**사용** : agent_evaluator 패키지 설치 후 예제 실행
```
    Evaluator_Examples/
    ├── 01_quality_eval.py     # 🎯 품질 지표 — Accuracy, Hallucination, Quality, RAG
    ├── 02_performance_eval.py # ⚡ 성능 지표 — TCR, Latency (p50/p95/p99), Token Economy
    ├── 03_agentic_eval.py     # 🤖 에이전틱 지표 — Tool Call, Coordination, Workflow, Retry
    └── 04_security_eval.py   # 🔒 보안 지표 — Input Sanitization, Leakage, Auth, Escalation, Attack
```

#### 3\. 🌐 FastAPI Dashboard (패키지 내장)

**목적** : 평가 결과 시각화 및 관리 — 관점 기반 UI (품질/성능/에이전틱/보안)

**위치** : `agent_evaluator/serve/` (패키지 내장, v0.5.2+)

```bash
    # 기본 실행 (포트 8765, 브라우저 자동 오픈)
    agent-eval dashboard

    # 결과 디렉토리 지정
    agent-eval dashboard results/

    # 옵션 지정
    agent-eval dashboard --port 8080        # 포트 변경
    agent-eval dashboard --watch            # 파일 변경 감시 (자동 갱신)
    agent-eval dashboard --no-open          # 브라우저 자동 오픈 비활성화
    agent-eval dashboard --host 0.0.0.0  # 외부 접근 허용
    agent-eval dashboard --offline          # 오프라인 모드
    agent-eval dashboard --title "내 평가"  # 대시보드 제목 지정
```

데이터는 `results/` 디렉토리에서 자동으로 로드됩니다.

#### 4\. 📖 Docs/ - Documentation (Standalone)

**목적** : HTML 문서 (GitHub Pages 배포 가능)

**접근** : 웹 브라우저로 직접 열기 또는 `index.html`
```
    Docs/
    ├── index.html                      # 📑 문서 인덱스 (진입점)
    ├── index_content.html              # 인덱스 컨텐츠
    │
    ├── 🚀 Quick Start & Overview
    │   ├── README.html                 # 프로젝트 README
    │   ├── GETTING_STARTED.html        # 시작 가이드
    │   └── DEVELOPER_QUICKSTART_GUIDE.html # 개발자 빠른 시작
    │
    ├── 📚 Core Documentation
    │   ├── API_REFERENCE.html          # API 레퍼런스 (전체)
    │   │                               # - PerformanceMonitor, HybridMonitor
    │   │                               # - Framework Integrations API
    │   │
    │   ├── METRICS_GUIDE.html          # 메트릭 종합 가이드
    │   │                               # - Layer 1: TCR, Accuracy, Hallucination, Quality
    │   │                               # - Layer 2: Tool Selection, Agent Coordination
    │   │                               # - Layer 3: DeepEval, Ragas
    │   │
    │   ├── AGENTIC_AI_METRICS_GUIDE.html # Agentic AI 메트릭 전문 가이드
    │   │                               # - Multi-Agent 시스템 평가
    │   │                               # - Tool Selection, Workflow 메트릭 상세
    │   │
    │   └── SECURITY_METRICS_GUIDE.html # 보안 메트릭 전문 가이드
    │                                   # - Layer 2 Security: Input Sanitization, Output Leakage 등
    │                                   # - Layer 2 Security: Privilege Escalation, Attack Detection 등
    │
    ├── 🎯 Feature Guides
    │   ├── FRAMEWORK_INTEGRATION.html  # Framework 통합 가이드
    │   │                               # - CrewAI, LangChain, LangGraph, AutoGen
    │   │                               # - 각 프레임워크별 사용법
    │   │
    │   ├── GOLDEN_DATASET_GUIDE.html   # Golden Dataset 가이드
    │   │                               # - PDF → Golden Dataset 자동 생성
    │   │                               # - 한국어/영어 지원
    │   │
    │   ├── KOREAN_RAG_GUIDE.html       # 한국어 RAG 평가 가이드
    │   │                               # - 한국어 특화 RAG 평가
    │   │                               # - Faithfulness, Answer Relevancy
    │   │
    │   ├── THRESHOLD_CONFIGURATION_GUIDE.html # Threshold 설정 가이드
    │   │                               # - Quality Gate 설정
    │   │                               # - 환경별 임계값 (dev/staging/prod)
    │   │
    │   └── ZERO_CONFIGURATION_GUIDE.html # Zero Configuration 가이드
    │                                   # - 자동 경로 탐지 (find_project_root)
    │                                   # - 프로젝트 루트 설정
    │
    ├── 🌐 Dashboard & Tools
    │   ├── DASHBOARD.html              # Dashboard 사용 가이드
    │   │                               # - 12 탭 구조 설명
    │   │                               # - 설치 및 실행 방법
    │   │
    │   ├── DATA_EDITOR_TRANSPARENCY_GUIDE.html # 데이터 편집 & 투명성 가이드
    │   │                               # - Test Configuration 편집
    │   │                               # - Audit Log, 투명성 보고서
    │   │
    │   └── DEPLOYMENT_GUIDE.html       # 배포 가이드 (현재 문서)
    │                                   # - CI/CD 통합 (GitLab CI, GitHub Actions)
    │                                   # - 환경별 설정 (dev/staging/prod)
    │
    ├── 📖 Learning Resources
    │   └── LEARNING_GUIDE.html         # 학습 로드맵
    │                                   # - Layer 1 → Layer 2 → Layer 3 순서
    │                                   # - 예제별 학습 경로
    │
    ├── styles/                         # 🎨 CSS 스타일시트
    │   └── docs.css                    # 통합 문서 스타일
    │
    └── scripts/                        # ⚙️ JavaScript
        └── docs.js                     # 문서 인터랙션
```

#### 프로젝트 루트 구조
```bash
    Agent_Evaluator/                    # 프로젝트 루트
    ├── agent_evaluator/                # → 1. Core Package (pip install)
    ├── Evaluator_Examples/             # → 2. Examples & Tutorials
    │   └── Dashboard/                  # → 3. Web Dashboard (독립 실행)
    ├── Docs/                           # → 4. Documentation (독립 접근)
    ├── setup.py                        # PyPI 패키징 설정
    ├── requirements.txt                # Core 패키지 의존성
    └── README.md                       # 프로젝트 README
```

**⚡ 독립 실행 가능 컴포넌트:**

  * **agent_evaluator/** : PyPI 패키지로 독립 설치 가능
  * **Dashboard/** : agent_evaluator 설치 후 독립 실행 가능
  * **Docs/** : 웹 브라우저로 직접 열기 가능
  * **Evaluator_Examples/** : agent_evaluator 의존성 있음 (pip install 필요)

* * *

## Environment Setup

### Development Environment

**목적** : 빠른 실험과 반복

**설정** :
```python
    [](<#cb11-1>)# config/dev.py
    [](<#cb11-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb11-3>)
    [](<#cb11-4>)def get_dev_monitor():
    [](<#cb11-5>)    monitor = PerformanceMonitor()
    [](<#cb11-6>)
    [](<#cb11-7>)    monitor.thresholds = {
    [](<#cb11-8>)        'tcr': 70.0,
    [](<#cb11-9>)        'accuracy': 65.0,
    [](<#cb11-10>)        'hallucination': 15.0
    [](<#cb11-11>)    }
    [](<#cb11-12>)
    [](<#cb11-13>)    return monitor
```

**환경 변수** (`.env.dev`):
```json
    [](<#cb12-1>)# Agent Evaluator 환경 변수 설정
    [](<#cb12-2>)
    [](<#cb12-3>)# =============================================================================
    [](<#cb12-4>)# API 키
    [](<#cb12-5>)# =============================================================================
    [](<#cb12-6>)
    [](<#cb12-7>)# OpenAI API 키 (선택 - Layer 3 고급 메트릭 및 Golden Dataset 생성 시 필요)
    [](<#cb12-8>)OPENAI_API_KEY='your-api-key-here'
    [](<#cb12-9>)
    [](<#cb12-10>)# =============================================================================
    [](<#cb12-11>)# 환경 설정
    [](<#cb12-12>)# =============================================================================
    [](<#cb12-13>)
    [](<#cb12-14>)ENV=development
    [](<#cb12-15>)LOG_LEVEL=DEBUG
    [](<#cb12-16>)GOLDEN_DATASET_PATH=golden_datasets/dev_dataset.json
    [](<#cb12-17>)ENABLE_TRANSPARENCY=true
    [](<#cb12-18>)CACHE_ENABLED=true
```

### Staging Environment

**목적** : 프로덕션 준비 검증

**설정** :
```python
    [](<#cb13-1>)# config/staging.py
    [](<#cb13-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb13-3>)
    [](<#cb13-4>)def get_staging_monitor():
    [](<#cb13-5>)    monitor = PerformanceMonitor()
    [](<#cb13-6>)
    [](<#cb13-7>)    monitor.thresholds = {
    [](<#cb13-8>)        'tcr': 85.0,
    [](<#cb13-9>)        'accuracy': 80.0,
    [](<#cb13-10>)        'hallucination': 8.0,
    [](<#cb13-11>)        'tool_selection_accuracy': 75.0,
    [](<#cb13-12>)        'agent_coordination': 7.0,
    [](<#cb13-13>)        'workflow_execution': 85.0
    [](<#cb13-14>)    }
    [](<#cb13-15>)
    [](<#cb13-16>)    return monitor
```

**환경 변수** (`.env.staging`):
```json
    [](<#cb14-1>)ENV=staging
    [](<#cb14-2>)LOG_LEVEL=INFO
    [](<#cb14-3>)GOLDEN_DATASET_PATH=golden_datasets/staging_dataset.json
    [](<#cb14-4>)ENABLE_TRANSPARENCY=true
    [](<#cb14-5>)ALERT_WEBHOOK=https://hooks.slack.com/services/YOUR/STAGING/WEBHOOK
```

### Production Environment

**목적** : 최고 품질 보장

**설정** :
```python
    [](<#cb15-1>)# config/production.py
    [](<#cb15-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb15-3>)import os
    [](<#cb15-4>)
    [](<#cb15-5>)def get_production_monitor():
    [](<#cb15-6>)    monitor = PerformanceMonitor()
    [](<#cb15-7>)
    [](<#cb15-8>)    monitor.thresholds = {
    [](<#cb15-9>)        # Layer 1: 엄격한 기준
    [](<#cb15-10>)        'tcr': 95.0,
    [](<#cb15-11>)        'accuracy': 90.0,
    [](<#cb15-12>)        'hallucination': 3.0,
    [](<#cb15-13>)        'latency': 3.0,
    [](<#cb15-14>)        'cost_per_task': 0.15,
    [](<#cb15-15>)
    [](<#cb15-16>)        # Layer 2: Agentic
    [](<#cb15-17>)        'tool_selection_accuracy': 85.0,
    [](<#cb15-18>)        'agent_coordination': 8.5,
    [](<#cb15-19>)        'workflow_execution': 95.0
    [](<#cb15-20>)    }
    [](<#cb15-21>)
    [](<#cb15-22>)    return monitor
```

**환경 변수** (`.env.production`):
```json
    [](<#cb16-1>)ENV=production
    [](<#cb16-2>)LOG_LEVEL=WARNING
    [](<#cb16-3>)GOLDEN_DATASET_PATH=golden_datasets/production_dataset.json
    [](<#cb16-4>)ENABLE_TRANSPARENCY=true
    [](<#cb16-5>)ALERT_WEBHOOK=https://hooks.slack.com/services/YOUR/PROD/WEBHOOK
    [](<#cb16-6>)SENTRY_DSN=https://your-sentry-dsn
    [](<#cb16-7>)MONITORING_ENABLED=true
```

### Environment Auto-Detection
```python
    [](<#cb17-1>)# config/__init__.py
    [](<#cb17-2>)import os
    [](<#cb17-3>)from .dev import get_dev_monitor
    [](<#cb17-4>)from .staging import get_staging_monitor
    [](<#cb17-5>)from .production import get_production_monitor
    [](<#cb17-6>)
    [](<#cb17-7>)def get_monitor():
    [](<#cb17-8>)    """환경에 따라 적절한 Monitor 반환"""
    [](<#cb17-9>)    env = os.getenv("ENV", "development")
    [](<#cb17-10>)
    [](<#cb17-11>)    if env == "production":
    [](<#cb17-12>)        return get_production_monitor()
    [](<#cb17-13>)    elif env == "staging":
    [](<#cb17-14>)        return get_staging_monitor()
    [](<#cb17-15>)    else:
    [](<#cb17-16>)        return get_dev_monitor()
```

* * *

## CI/CD Integration

### CI/CD 통합 (GitLab CI / Jenkins 권장)

#### Basic Quality Gate
```json
    [](<#cb18-1>)# .github/workflows/quality-gate.yml
    [](<#cb18-2>)name: Agent Quality Gate
    [](<#cb18-3>)
    [](<#cb18-4>)on:
    [](<#cb18-5>)  push:
    [](<#cb18-6>)    branches: [main, develop]
    [](<#cb18-7>)  pull_request:
    [](<#cb18-8>)    branches: [main]
    [](<#cb18-9>)
    [](<#cb18-10>)jobs:
    [](<#cb18-11>)  quality-gate:
    [](<#cb18-12>)    runs-on: ubuntu-latest
    [](<#cb18-13>)
    [](<#cb18-14>)    steps:
    [](<#cb18-15>)      - name: Checkout code
    [](<#cb18-16>)        uses: actions/checkout@v3
    [](<#cb18-17>)
    [](<#cb18-18>)      - name: Set up Python
    [](<#cb18-19>)        uses: actions/setup-python@v4
    [](<#cb18-20>)        with:
    [](<#cb18-21>)          python-version: '3.11'
    [](<#cb18-22>)
    [](<#cb18-23>)      - name: Install dependencies
    [](<#cb18-24>)        run: |
    [](<#cb18-25>)          python -m pip install --upgrade pip
    [](<#cb18-26>)          pip install agent-evaluator
    [](<#cb18-27>)
    [](<#cb18-28>)      - name: Run Quality Gate
    [](<#cb18-29>)        env:
    [](<#cb18-30>)          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    [](<#cb18-31>)          ENV: ${{ github.ref == 'refs/heads/main' && 'production' || 'staging' }}
    [](<#cb18-32>)        run: |
    [](<#cb18-33>)          python scripts/quality_gate.py
    [](<#cb18-34>)
    [](<#cb18-35>)      - name: Upload Results
    [](<#cb18-36>)        if: always()
    [](<#cb18-37>)        uses: actions/upload-artifact@v3
    [](<#cb18-38>)        with:
    [](<#cb18-39>)          name: evaluation-results
    [](<#cb18-40>)          path: evaluation_results/
```

#### Advanced: Multi-Environment
```json
    [](<#cb19-1>)# .github/workflows/multi-env-test.yml
    [](<#cb19-2>)name: Multi-Environment Testing
    [](<#cb19-3>)
    [](<#cb19-4>)on:
    [](<#cb19-5>)  push:
    [](<#cb19-6>)    branches: [main, develop, 'feature/**']
    [](<#cb19-7>)
    [](<#cb19-8>)jobs:
    [](<#cb19-9>)  test-dev:
    [](<#cb19-10>)    runs-on: ubuntu-latest
    [](<#cb19-11>)    env:
    [](<#cb19-12>)      ENV: development
    [](<#cb19-13>)
    [](<#cb19-14>)    steps:
    [](<#cb19-15>)      - uses: actions/checkout@v3
    [](<#cb19-16>)      - uses: actions/setup-python@v4
    [](<#cb19-17>)        with:
    [](<#cb19-18>)          python-version: '3.11'
    [](<#cb19-19>)      - run: |
    [](<#cb19-20>)          pip install --upgrade pip
    [](<#cb19-21>)          pip install agent-evaluator
    [](<#cb19-22>)          python scripts/quality_gate.py
    [](<#cb19-23>)
    [](<#cb19-24>)  test-staging:
    [](<#cb19-25>)    runs-on: ubuntu-latest
    [](<#cb19-26>)    if: github.ref == 'refs/heads/develop' || github.event_name == 'pull_request'
    [](<#cb19-27>)    env:
    [](<#cb19-28>)      ENV: staging
    [](<#cb19-29>)
    [](<#cb19-30>)    steps:
    [](<#cb19-31>)      - uses: actions/checkout@v3
    [](<#cb19-32>)      - uses: actions/setup-python@v4
    [](<#cb19-33>)        with:
    [](<#cb19-34>)          python-version: '3.11'
    [](<#cb19-35>)      - run: |
    [](<#cb19-36>)          pip install --upgrade pip
    [](<#cb19-37>)          pip install agent-evaluator
    [](<#cb19-38>)          python scripts/quality_gate.py
    [](<#cb19-39>)
    [](<#cb19-40>)  test-production:
    [](<#cb19-41>)    runs-on: ubuntu-latest
    [](<#cb19-42>)    if: github.ref == 'refs/heads/main'
    [](<#cb19-43>)    env:
    [](<#cb19-44>)      ENV: production
    [](<#cb19-45>)
    [](<#cb19-46>)    steps:
    [](<#cb19-47>)      - uses: actions/checkout@v3
    [](<#cb19-48>)      - uses: actions/setup-python@v4
    [](<#cb19-49>)        with:
    [](<#cb19-50>)          python-version: '3.11'
    [](<#cb19-51>)      - run: |
    [](<#cb19-52>)          pip install --upgrade pip
    [](<#cb19-53>)          pip install agent-evaluator
    [](<#cb19-54>)          python scripts/quality_gate.py
    [](<#cb19-55>)
    [](<#cb19-56>)      - name: Notify on failure
    [](<#cb19-57>)        if: failure()
    [](<#cb19-58>)        uses: 8398a7/action-slack@v3
    [](<#cb19-59>)        with:
    [](<#cb19-60>)          status: ${{ job.status }}
    [](<#cb19-61>)          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

### GitLab CI/CD
```json
    [](<#cb20-1>)# .gitlab-ci.yml
    [](<#cb20-2>)stages:
    [](<#cb20-3>)  - test
    [](<#cb20-4>)  - quality-gate
    [](<#cb20-5>)  - deploy
    [](<#cb20-6>)
    [](<#cb20-7>)variables:
    [](<#cb20-8>)  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"
    [](<#cb20-9>)
    [](<#cb20-10>)cache:
    [](<#cb20-11>)  paths:
    [](<#cb20-12>)    - .cache/pip
    [](<#cb20-13>)
    [](<#cb20-14>)before_script:
    [](<#cb20-15>)  - python -m pip install --upgrade pip
    [](<#cb20-16>)  - pip install agent-evaluator
    [](<#cb20-17>)
    [](<#cb20-18>)quality-gate-dev:
    [](<#cb20-19>)  stage: quality-gate
    [](<#cb20-20>)  script:
    [](<#cb20-21>)    - export ENV=development
    [](<#cb20-22>)    - python scripts/quality_gate.py
    [](<#cb20-23>)  only:
    [](<#cb20-24>)    - branches
    [](<#cb20-25>)  except:
    [](<#cb20-26>)    - main
    [](<#cb20-27>)    - develop
    [](<#cb20-28>)
    [](<#cb20-29>)quality-gate-staging:
    [](<#cb20-30>)  stage: quality-gate
    [](<#cb20-31>)  script:
    [](<#cb20-32>)    - export ENV=staging
    [](<#cb20-33>)    - python scripts/quality_gate.py
    [](<#cb20-34>)  only:
    [](<#cb20-35>)    - develop
    [](<#cb20-36>)  artifacts:
    [](<#cb20-37>)    when: always
    [](<#cb20-38>)    paths:
    [](<#cb20-39>)      - evaluation_results/
    [](<#cb20-40>)
    [](<#cb20-41>)quality-gate-production:
    [](<#cb20-42>)  stage: quality-gate
    [](<#cb20-43>)  script:
    [](<#cb20-44>)    - export ENV=production
    [](<#cb20-45>)    - python scripts/quality_gate.py
    [](<#cb20-46>)  only:
    [](<#cb20-47>)    - main
    [](<#cb20-48>)  artifacts:
    [](<#cb20-49>)    when: always
    [](<#cb20-50>)    paths:
    [](<#cb20-51>)      - evaluation_results/
    [](<#cb20-52>)  allow_failure: false
```

### Jenkins Pipeline
```json
    [](<#cb21-1>)// Jenkinsfile
    [](<#cb21-2>)pipeline {
    [](<#cb21-3>)    agent any
    [](<#cb21-4>)
    [](<#cb21-5>)    environment {
    [](<#cb21-6>)        OPENAI_API_KEY = credentials('openai-api-key')
    [](<#cb21-7>)    }
    [](<#cb21-8>)
    [](<#cb21-9>)    stages {
    [](<#cb21-10>)        stage('Setup') {
    [](<#cb21-11>)            steps {
    [](<#cb21-12>)                sh '''
    [](<#cb21-13>)                    conda create --name Evaluator python=3.11 -y
    [](<#cb21-14>)                    source activate Evaluator
    [](<#cb21-15>)                    pip install --upgrade pip
    [](<#cb21-16>)                    pip install agent-evaluator
    [](<#cb21-17>)                '''
    [](<#cb21-18>)            }
    [](<#cb21-19>)        }
    [](<#cb21-20>)
    [](<#cb21-21>)        stage('Quality Gate - Development') {
    [](<#cb21-22>)            when {
    [](<#cb21-23>)                not {
    [](<#cb21-24>)                    anyOf {
    [](<#cb21-25>)                        branch 'main'
    [](<#cb21-26>)                        branch 'develop'
    [](<#cb21-27>)                    }
    [](<#cb21-28>)                }
    [](<#cb21-29>)            }
    [](<#cb21-30>)            environment {
    [](<#cb21-31>)                ENV = 'development'
    [](<#cb21-32>)            }
    [](<#cb21-33>)            steps {
    [](<#cb21-34>)                sh '''
    [](<#cb21-35>)                    source activate Evaluator
    [](<#cb21-36>)                    python scripts/quality_gate.py
    [](<#cb21-37>)                '''
    [](<#cb21-38>)            }
    [](<#cb21-39>)        }
    [](<#cb21-40>)
    [](<#cb21-41>)        stage('Quality Gate - Staging') {
    [](<#cb21-42>)            when {
    [](<#cb21-43>)                branch 'develop'
    [](<#cb21-44>)            }
    [](<#cb21-45>)            environment {
    [](<#cb21-46>)                ENV = 'staging'
    [](<#cb21-47>)            }
    [](<#cb21-48>)            steps {
    [](<#cb21-49>)                sh '''
    [](<#cb21-50>)                    source activate Evaluator
    [](<#cb21-51>)                    python scripts/quality_gate.py
    [](<#cb21-52>)                '''
    [](<#cb21-53>)            }
    [](<#cb21-54>)        }
    [](<#cb21-55>)
    [](<#cb21-56>)        stage('Quality Gate - Production') {
    [](<#cb21-57>)            when {
    [](<#cb21-58>)                branch 'main'
    [](<#cb21-59>)            }
    [](<#cb21-60>)            environment {
    [](<#cb21-61>)                ENV = 'production'
    [](<#cb21-62>)            }
    [](<#cb21-63>)            steps {
    [](<#cb21-64>)                sh '''
    [](<#cb21-65>)                    source activate Evaluator
    [](<#cb21-66>)                    python scripts/quality_gate.py
    [](<#cb21-67>)                '''
    [](<#cb21-68>)            }
    [](<#cb21-69>)        }
    [](<#cb21-70>)
    [](<#cb21-71>)        stage('Archive Results') {
    [](<#cb21-72>)            steps {
    [](<#cb21-73>)                archiveArtifacts artifacts: 'evaluation_results/**/*', allowEmptyArchive: true
    [](<#cb21-74>)            }
    [](<#cb21-75>)        }
    [](<#cb21-76>)    }
    [](<#cb21-77>)
    [](<#cb21-78>)    post {
    [](<#cb21-79>)        failure {
    [](<#cb21-80>)            slackSend(
    [](<#cb21-81>)                channel: '#alerts-ci',
    [](<#cb21-82>)                color: 'danger',
    [](<#cb21-83>)                message: "Quality Gate Failed: ${env.JOB_NAME} - ${env.BUILD_NUMBER}"
    [](<#cb21-84>)            )
    [](<#cb21-85>)        }
    [](<#cb21-86>)    }
    [](<#cb21-87>)}
```

### Quality Gate Script

실제 프로젝트 기반 예제:
```python
    [](<#cb22-1>)# scripts/quality_gate.py
    [](<#cb22-2>)import os
    [](<#cb22-3>)import sys
    [](<#cb22-4>)from dotenv import load_dotenv
    [](<#cb22-5>)from agent_evaluator import PerformanceMonitor
    [](<#cb22-7>)
    [](<#cb22-8>)# 환경 변수 로드
    [](<#cb22-9>)load_dotenv()
    [](<#cb22-10>)
    [](<#cb22-11>)def main():
    [](<#cb22-12>)    """Quality Gate 실행"""
    [](<#cb22-13>)    env = os.getenv("ENV", "development")
    [](<#cb22-14>)    print(f"Environment: {env}")
    [](<#cb22-15>)
    [](<#cb22-16>)    # PerformanceMonitor 초기화
    [](<#cb22-17>)    monitor = PerformanceMonitor()
    [](<#cb22-18>)
    [](<#cb22-19>)    # 환경별 Threshold 설정
    [](<#cb22-20>)    if env == "production":
    [](<#cb22-21>)        monitor.thresholds = {
    [](<#cb22-22>)            # Layer 1: Foundation Metrics
    [](<#cb22-23>)            'tcr': 95.0,
    [](<#cb22-24>)            'accuracy': 90.0,
    [](<#cb22-25>)            'hallucination': 3.0,
    [](<#cb22-26>)            'latency': 3.0,
    [](<#cb22-27>)            'cost_per_task': 0.15,
    [](<#cb22-28>)
    [](<#cb22-29>)            # Layer 2: Agentic Metrics
    [](<#cb22-30>)            'tool_selection_accuracy': 85.0,
    [](<#cb22-31>)            'agent_coordination': 8.5,
    [](<#cb22-32>)            'workflow_execution': 95.0
    [](<#cb22-33>)        }
    [](<#cb22-34>)    elif env == "staging":
    [](<#cb22-35>)        monitor.thresholds = {
    [](<#cb22-36>)            'tcr': 85.0,
    [](<#cb22-37>)            'accuracy': 80.0,
    [](<#cb22-38>)            'hallucination': 8.0,
    [](<#cb22-39>)            'tool_selection_accuracy': 75.0,
    [](<#cb22-40>)            'agent_coordination': 7.0,
    [](<#cb22-41>)            'workflow_execution': 85.0
    [](<#cb22-42>)        }
    [](<#cb22-43>)    else:  # development
    [](<#cb22-44>)        monitor.thresholds = {
    [](<#cb22-45>)            'tcr': 70.0,
    [](<#cb22-46>)            'accuracy': 65.0,
    [](<#cb22-47>)            'hallucination': 15.0
    [](<#cb22-48>)        }
    [](<#cb22-49>)
    [](<#cb22-50>)    print(f"\nThresholds configured for {env}:")
    [](<#cb22-51>)    for metric, value in monitor.thresholds.items():
    [](<#cb22-52>)        print(f"  {metric}: {value}")
    [](<#cb22-53>)
    [](<#cb22-54>)    # Golden Dataset 경로
    [](<#cb22-55>)    dataset_path = os.getenv("GOLDEN_DATASET_PATH", "golden_datasets/sample_dataset.json")
    [](<#cb22-56>)    print(f"\nGolden Dataset: {dataset_path}")
    [](<#cb22-57>)
    [](<#cb22-58>)    # Golden Dataset 평가 실행
    [](<#cb22-59>)    print(f"\nRunning evaluation...")
    [](<#cb22-60>)    try:
    [](<#cb22-61>)        results = monitor.evaluate_with_golden_dataset(
    [](<#cb22-62>)            agent_fn=my_agent,
    [](<#cb22-63>)            dataset_path=dataset_path,
    [](<#cb22-64>)            enable_layer2_metrics=True  # Layer 2 메트릭 활성화
    [](<#cb22-65>)        )
    [](<#cb22-66>)        print(f"Evaluation completed: {len(results)} tasks evaluated")
    [](<#cb22-67>)    except Exception as e:
    [](<#cb22-68>)        print(f"ERROR: Evaluation failed - {e}")
    [](<#cb22-69>)        sys.exit(1)
    [](<#cb22-70>)
    [](<#cb22-71>)    # Threshold 비교
    [](<#cb22-72>)    print(f"\nThreshold Comparison:")
    [](<#cb22-73>)    comparison = monitor.compare_with_thresholds()
    [](<#cb22-74>)
    [](<#cb22-75>)    passed = []
    [](<#cb22-76>)    failed = []
    [](<#cb22-77>)
    [](<#cb22-78>)    for metric, data in comparison.items():
    [](<#cb22-79>)        status = "PASS" if data['status'] == 'pass' else "FAIL"
    [](<#cb22-80>)        symbol = "✓" if data['status'] == 'pass' else "✗"
    [](<#cb22-81>)        print(f"  [{symbol}] {data['name']}: {data['value']:.1f}{data['unit']} (threshold: {data['threshold']}{data['unit']}) - {status}")
    [](<#cb22-82>)
    [](<#cb22-83>)        if data['status'] == 'pass':
    [](<#cb22-84>)            passed.append(metric)
    [](<#cb22-85>)        else:
    [](<#cb22-86>)            failed.append(metric)
    [](<#cb22-87>)
    [](<#cb22-88>)    # 결과 요약
    [](<#cb22-89>)    print(f"\n{'='*60}")
    [](<#cb22-90>)    print(f"Summary:")
    [](<#cb22-91>)    print(f"  Passed: {len(passed)}/{len(comparison)}")
    [](<#cb22-92>)    print(f"  Failed: {len(failed)}/{len(comparison)}")
    [](<#cb22-93>)    print(f"{'='*60}")
    [](<#cb22-94>)
    [](<#cb22-95>)    # CI/CD 판정
    [](<#cb22-96>)    if failed:
    [](<#cb22-97>)        print(f"\nQUALITY GATE FAILED")
    [](<#cb22-98>)        print(f"\nFailed metrics:")
    [](<#cb22-99>)        for metric in failed:
    [](<#cb22-100>)            data = comparison[metric]
    [](<#cb22-101>)            print(f"  - {data['name']}: {data['value']:.1f}{data['unit']} (required: {data['threshold']}{data['unit']})")
    [](<#cb22-102>)
    [](<#cb22-103>)        # Slack 알림 (선택)
    [](<#cb22-104>)        send_slack_notification(failed, env, comparison)
    [](<#cb22-105>)
    [](<#cb22-106>)        sys.exit(1)  # CI/CD 실패
    [](<#cb22-107>)    else:
    [](<#cb22-108>)        print(f"\nQUALITY GATE PASSED")
    [](<#cb22-109>)        sys.exit(0)  # CI/CD 성공
    [](<#cb22-110>)
    [](<#cb22-111>)
    [](<#cb22-112>)def my_agent(question: str, context: str = "", **kwargs):
    [](<#cb22-113>)    """
    [](<#cb22-114>)    에이전트 구현 예제
    [](<#cb22-115>)    실제 프로젝트에서는 여기에 AI Agent 로직 구현
    [](<#cb22-116>)    """
    [](<#cb22-117>)    # 예제: 간단한 응답 생성
    [](<#cb22-118>)    # 실제로는 LangChain, CrewAI, LangGraph 등을 사용
    [](<#cb22-119>)    response = f"Answer to: {question}"
    [](<#cb22-120>)
    [](<#cb22-121>)    return {
    [](<#cb22-122>)        'answer': response,
    [](<#cb22-123>)        'tool_calls': [],
    [](<#cb22-124>)        'execution_time': 1.0,
    [](<#cb22-125>)        'tokens_used': {'prompt': 100, 'completion': 50}
    [](<#cb22-126>)    }
    [](<#cb22-127>)
    [](<#cb22-128>)
    [](<#cb22-129>)def send_slack_notification(failed_metrics, env, comparison):
    [](<#cb22-130>)    """Slack 알림 전송 (선택)"""
    [](<#cb22-131>)    webhook_url = os.getenv("ALERT_WEBHOOK")
    [](<#cb22-132>)    if not webhook_url:
    [](<#cb22-133>)        return
    [](<#cb22-134>)
    [](<#cb22-135>)    try:
    [](<#cb22-136>)        import requests
    [](<#cb22-137>)
    [](<#cb22-138>)        failed_details = []
    [](<#cb22-139>)        for metric in failed_metrics:
    [](<#cb22-140>)            data = comparison[metric]
    [](<#cb22-141>)            failed_details.append(
    [](<#cb22-142>)                f"• {data['name']}: {data['value']:.1f}{data['unit']} (required: {data['threshold']}{data['unit']})"
    [](<#cb22-143>)            )
    [](<#cb22-144>)
    [](<#cb22-145>)        message = {
    [](<#cb22-146>)            "text": f"Quality Gate Failed ({env})",
    [](<#cb22-147>)            "blocks": [
    [](<#cb22-148>)                {
    [](<#cb22-149>)                    "type": "header",
    [](<#cb22-150>)                    "text": {
    [](<#cb22-151>)                        "type": "plain_text",
    [](<#cb22-152>)                        "text": f"Quality Gate Failed - {env.upper()}"
    [](<#cb22-153>)                    }
    [](<#cb22-154>)                },
    [](<#cb22-155>)                {
    [](<#cb22-156>)                    "type": "section",
    [](<#cb22-157>)                    "text": {
    [](<#cb22-158>)                        "type": "mrkdwn",
    [](<#cb22-159>)                        "text": f"*Environment:* `{env}`\n*Failed Metrics:* {len(failed_metrics)}"
    [](<#cb22-160>)                    }
    [](<#cb22-161>)                },
    [](<#cb22-162>)                {
    [](<#cb22-163>)                    "type": "section",
    [](<#cb22-164>)                    "text": {
    [](<#cb22-165>)                        "type": "mrkdwn",
    [](<#cb22-166>)                        "text": "*Failed Metrics Details:*\n" + "\n".join(failed_details)
    [](<#cb22-167>)                    }
    [](<#cb22-168>)                }
    [](<#cb22-169>)            ]
    [](<#cb22-170>)        }
    [](<#cb22-171>)
    [](<#cb22-172>)        response = requests.post(webhook_url, json=message)
    [](<#cb22-173>)        if response.status_code == 200:
    [](<#cb22-174>)            print("Slack notification sent successfully")
    [](<#cb22-175>)        else:
    [](<#cb22-176>)            print(f"Failed to send Slack notification: {response.status_code}")
    [](<#cb22-177>)    except Exception as e:
    [](<#cb22-178>)        print(f"Error sending Slack notification: {e}")
    [](<#cb22-179>)
    [](<#cb22-180>)
    [](<#cb22-181>)if __name__ == "__main__":
    [](<#cb22-182>)    main()
```

* * *

## Docker Deployment

### Dockerfile

실제 프로젝트 기반:
```json
    [](<#cb23-1>)# Dockerfile
    [](<#cb23-2>)FROM python:3.11-slim
    [](<#cb23-3>)
    [](<#cb23-4>)LABEL maintainer="Agent Evaluator Team"
    [](<#cb23-5>)LABEL description="AI Agent Performance Evaluation System"
    [](<#cb23-6>)
    [](<#cb23-7>)WORKDIR /app
    [](<#cb23-8>)
    [](<#cb23-9>)# System dependencies
    [](<#cb23-10>)RUN apt-get update && apt-get install -y \
    [](<#cb23-11>)    git \
    [](<#cb23-12>)    curl \
    [](<#cb23-13>)    && rm -rf /var/lib/apt/lists/*
    [](<#cb23-14>)
    [](<#cb23-15>)# Python dependencies
    [](<#cb23-16>)COPY requirements.txt .
    [](<#cb23-17>)RUN pip install --no-cache-dir --upgrade pip && \
    [](<#cb23-18>)    pip install --no-cache-dir -r requirements.txt
    [](<#cb23-19>)
    [](<#cb23-20>)# Application code (Core Package)
    [](<#cb23-21>)COPY agent_evaluator/ ./agent_evaluator/
    [](<#cb23-22>)
    [](<#cb23-23>)# Dashboard and Examples
    [](<#cb23-24>)COPY Evaluator_Examples/ ./Evaluator_Examples/
    [](<#cb23-38>)
    [](<#cb23-39>)# Create evaluation_results directory
    [](<#cb23-40>)RUN mkdir -p evaluation_results/test_configs \
    [](<#cb23-41>)    evaluation_results/traces \
    [](<#cb23-42>)    evaluation_results/annotations \
    [](<#cb23-43>)    evaluation_results/audit_logs \
    [](<#cb23-44>)    evaluation_results/edit_history \
    [](<#cb23-45>)    evaluation_results/versions
    [](<#cb23-46>)
    [](<#cb23-47>)# Environment
    [](<#cb23-48>)ENV ENV=production
    [](<#cb23-49>)ENV LOG_LEVEL=INFO
    [](<#cb23-50>)ENV PYTHONUNBUFFERED=1
    [](<#cb23-51>)
    [](<#cb23-25>)# Health check
    [](<#cb23-26>)HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    [](<#cb23-27>)    CMD python -c "import agent_evaluator; print('OK')" || exit 1
    [](<#cb23-28>)
    [](<#cb23-29>)# Expose FastAPI dashboard port
    [](<#cb23-30>)EXPOSE 8765
    [](<#cb23-31>)
    [](<#cb23-32>)# Default command: Run dashboard
    [](<#cb23-33>)CMD ["agent-eval", "dashboard", "--port", "8765", "--no-open"]
```

### docker-compose.yml

실제 프로젝트 기반:
```json
    [](<#cb24-1>)# docker-compose.yml
    [](<#cb24-2>)version: '3.8'
    [](<#cb24-3>)
    [](<#cb24-4>)services:
    [](<#cb24-5>)  # FastAPI Dashboard Service
    [](<#cb24-6>)  dashboard:
    [](<#cb24-7>)    build: .
    [](<#cb24-8>)    container_name: agent-evaluator-dashboard
    [](<#cb24-9>)    ports:
    [](<#cb24-10>)      - "8765:8765"
    [](<#cb24-11>)    environment:
    [](<#cb24-12>)      - ENV=${ENV:-production}
    [](<#cb24-13>)      - OPENAI_API_KEY=${OPENAI_API_KEY}
    [](<#cb24-14>)      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    [](<#cb24-15>)      - PYTHONUNBUFFERED=1
    [](<#cb24-16>)    volumes:
    [](<#cb24-17>)      - ./evaluation_results:/app/evaluation_results
    [](<#cb24-18>)      - ./golden_datasets:/app/golden_datasets
    [](<#cb24-19>)      - ./.env:/app/.env
    [](<#cb24-20>)    command: agent-eval dashboard --port 8765 --no-open
    [](<#cb24-21>)    restart: unless-stopped
    [](<#cb24-22>)    healthcheck:
    [](<#cb24-23>)      test: ["CMD", "curl", "-f", "http://localhost:8765/health"]
    [](<#cb24-24>)      interval: 30s
    [](<#cb24-25>)      timeout: 10s
    [](<#cb24-26>)      retries: 3
    [](<#cb24-27>)      start_period: 40s
    [](<#cb24-28>)
    [](<#cb24-29>)  # Quality Gate Service (CI/CD용)
    [](<#cb24-30>)  quality-gate:
    [](<#cb24-31>)    build: .
    [](<#cb24-32>)    container_name: agent-evaluator-quality-gate
    [](<#cb24-33>)    environment:
    [](<#cb24-34>)      - ENV=${ENV:-staging}
    [](<#cb24-35>)      - OPENAI_API_KEY=${OPENAI_API_KEY}
    [](<#cb24-36>)      - GOLDEN_DATASET_PATH=${GOLDEN_DATASET_PATH:-golden_datasets/sample_dataset.json}
    [](<#cb24-37>)      - ALERT_WEBHOOK=${ALERT_WEBHOOK}
    [](<#cb24-38>)    volumes:
    [](<#cb24-39>)      - ./evaluation_results:/app/evaluation_results
    [](<#cb24-40>)      - ./golden_datasets:/app/golden_datasets
    [](<#cb24-41>)      - ./.env:/app/.env
    [](<#cb24-42>)      - ./scripts:/app/scripts
    [](<#cb24-43>)    command: python scripts/quality_gate.py
    [](<#cb24-44>)    profiles:
    [](<#cb24-45>)      - ci-cd  # docker-compose --profile ci-cd up 으로 실행
    [](<#cb24-46>)
    [](<#cb24-47>)volumes:
    [](<#cb24-48>)  evaluation_results:
    [](<#cb24-49>)  golden_datasets:
```

### .dockerignore
```python
    # .dockerignore
    __pycache__/
    *.py[cod]
    *$py.class
    *.so
    .Python
    venv/
    env/
    ENV/
    .venv
    .git
    .gitignore
    .github/
    .gitlab-ci.yml
    *.md
    !README.md
    .DS_Store
    .env
    evaluation_results/*.json
    !evaluation_results/test_configs/
    *.log
    .pytest_cache/
    .coverage
    htmlcov/
    dist/
    build/
    *.egg-info/
```

### Build and Run
```json
    [](<#cb26-1>)# ============================================================================
    [](<#cb26-2>)# 방법 1: Docker Compose 사용 (권장)
    [](<#cb26-3>)# ============================================================================
    [](<#cb26-4>)
    [](<#cb26-5>)# Dashboard 실행
    [](<#cb26-6>)docker-compose up -d dashboard
    [](<#cb26-7>)
    [](<#cb26-8>)# 브라우저에서 접속
    [](<#cb26-9>)# http://localhost:8765
    [](<#cb26-10>)
    [](<#cb26-11>)# 로그 확인
    [](<#cb26-12>)docker-compose logs -f dashboard
    [](<#cb26-13>)
    [](<#cb26-14>)# Quality Gate 실행 (CI/CD)
    [](<#cb26-15>)docker-compose --profile ci-cd up quality-gate
    [](<#cb26-16>)
    [](<#cb26-17>)# 모두 중지
    [](<#cb26-18>)docker-compose down
    [](<#cb26-19>)
    [](<#cb26-20>)# ============================================================================
    [](<#cb26-21>)# 방법 2: Docker 직접 사용
    [](<#cb26-22>)# ============================================================================
    [](<#cb26-23>)
    [](<#cb26-24>)# 이미지 빌드
    [](<#cb26-25>)docker build -t agent-evaluator:latest .
    [](<#cb26-26>)
    [](<#cb26-27>)# Dashboard 실행
    [](<#cb26-28>)docker run -d \
    [](<#cb26-29>)  --name agent-evaluator-dashboard \
    [](<#cb26-30>)  -p 8765:8765 \
    [](<#cb26-31>)  -e OPENAI_API_KEY=${OPENAI_API_KEY} \
    [](<#cb26-32>)  -e ENV=production \
    [](<#cb26-33>)  -v $(pwd)/evaluation_results:/app/evaluation_results \
    [](<#cb26-34>)  -v $(pwd)/golden_datasets:/app/golden_datasets \
    [](<#cb26-35>)  agent-evaluator:latest
    [](<#cb26-36>)
    [](<#cb26-37>)# Dashboard 로그 확인
    [](<#cb26-38>)docker logs -f agent-evaluator-dashboard
    [](<#cb26-39>)
    [](<#cb26-40>)# Quality Gate 실행
    [](<#cb26-41>)docker run --rm \
    [](<#cb26-42>)  -e ENV=production \
    [](<#cb26-43>)  -e OPENAI_API_KEY=${OPENAI_API_KEY} \
    [](<#cb26-44>)  -e GOLDEN_DATASET_PATH=golden_datasets/sample_dataset.json \
    [](<#cb26-45>)  -v $(pwd)/evaluation_results:/app/evaluation_results \
    [](<#cb26-46>)  -v $(pwd)/golden_datasets:/app/golden_datasets \
    [](<#cb26-47>)  -v $(pwd)/scripts:/app/scripts \
    [](<#cb26-48>)  agent-evaluator:latest \
    [](<#cb26-49>)  python scripts/quality_gate.py
    [](<#cb26-50>)
    [](<#cb26-51>)# 컨테이너 중지 및 제거
    [](<#cb26-52>)docker stop agent-evaluator-dashboard
    [](<#cb26-53>)docker rm agent-evaluator-dashboard
    [](<#cb26-54>)
    [](<#cb26-55>)# ============================================================================
    [](<#cb26-56>)# 개발 모드 (로컬 코드 마운트)
    [](<#cb26-57>)# ============================================================================
    [](<#cb26-58>)
    [](<#cb26-59>)docker run -d \
    [](<#cb26-60>)  --name agent-evaluator-dev \
    [](<#cb26-61>)  -p 8765:8765 \
    [](<#cb26-62>)  -e ENV=development \
    [](<#cb26-63>)  -e OPENAI_API_KEY=${OPENAI_API_KEY} \
    [](<#cb26-64>)  -v $(pwd):/app \
    [](<#cb26-65>)  agent-evaluator:latest
    [](<#cb26-66>)
    [](<#cb26-67>)# ============================================================================
    [](<#cb26-68>)# 유용한 Docker 명령어
    [](<#cb26-69>)# ============================================================================
    [](<#cb26-70>)
    [](<#cb26-71>)# 이미지 확인
    [](<#cb26-72>)docker images | grep agent-evaluator
    [](<#cb26-73>)
    [](<#cb26-74>)# 실행 중인 컨테이너 확인
    [](<#cb26-75>)docker ps | grep agent-evaluator
    [](<#cb26-76>)
    [](<#cb26-77>)# 컨테이너 내부 접속
    [](<#cb26-78>)docker exec -it agent-evaluator-dashboard /bin/bash
    [](<#cb26-79>)
    [](<#cb26-80>)# 헬스체크 확인
    [](<#cb26-81>)docker inspect --format='{{json .State.Health}}' agent-evaluator-dashboard
    [](<#cb26-82>)
    [](<#cb26-83>)# 리소스 사용량 확인
    [](<#cb26-84>)docker stats agent-evaluator-dashboard
```

* * *

## Production Configuration

### config/production.py
```python
    [](<#cb27-1>)import os
    [](<#cb27-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb27-3>)
    [](<#cb27-4>)def get_production_monitor():
    [](<#cb27-5>)    """프로덕션 Monitor 생성"""
    [](<#cb27-6>)    monitor = PerformanceMonitor(
    [](<#cb27-7>)        output_dir="results/",
    [](<#cb27-8>)        enable_security_metrics=True
    [](<#cb27-9>)    )
    [](<#cb27-10>)
    [](<#cb27-11>)    # 프로덕션 임계값 설정
    [](<#cb27-12>)    monitor.thresholds = {
    [](<#cb27-13>)        # Layer 1: Foundation Metrics
    [](<#cb27-14>)        'tcr': 95.0,
    [](<#cb27-15>)        'accuracy': 90.0,
    [](<#cb27-16>)        'hallucination': 3.0,
    [](<#cb27-17>)        'latency': 3.0,
    [](<#cb27-18>)        'cost_per_task': 0.15,
    [](<#cb27-19>)
    [](<#cb27-20>)        # Layer 2: Agentic Metrics
    [](<#cb27-21>)        'tool_selection_accuracy': 85.0,
    [](<#cb27-22>)        'agent_coordination': 8.5,
    [](<#cb27-23>)        'workflow_execution': 95.0
    [](<#cb27-24>)    }
    [](<#cb27-56>)    return monitor
```

* * *

## Monitoring & Logging

### Logging Configuration
```python
    [](<#cb28-1>)# logging_config.py
    [](<#cb28-2>)import logging
    [](<#cb28-3>)import os
    [](<#cb28-4>)
    [](<#cb28-5>)def setup_logging():
    [](<#cb28-6>)    """로깅 설정"""
    [](<#cb28-7>)    level = os.getenv("LOG_LEVEL", "INFO")
    [](<#cb28-8>)
    [](<#cb28-9>)    logging.basicConfig(
    [](<#cb28-10>)        level=getattr(logging, level),
    [](<#cb28-11>)        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    [](<#cb28-12>)        handlers=[
    [](<#cb28-13>)            logging.FileHandler("evaluation_results/agent_evaluator.log"),
    [](<#cb28-14>)            logging.StreamHandler()
    [](<#cb28-15>)        ]
    [](<#cb28-16>)    )
    [](<#cb28-17>)
    [](<#cb28-18>)    return logging.getLogger("agent_evaluator")
```

### Sentry Integration
```python
    [](<#cb29-1>)# monitoring.py
    [](<#cb29-2>)import sentry_sdk
    [](<#cb29-3>)import os
    [](<#cb29-4>)
    [](<#cb29-5>)def setup_sentry():
    [](<#cb29-6>)    """Sentry 오류 추적"""
    [](<#cb29-7>)    dsn = os.getenv("SENTRY_DSN")
    [](<#cb29-8>)    if dsn:
    [](<#cb29-9>)        sentry_sdk.init(
    [](<#cb29-10>)            dsn=dsn,
    [](<#cb29-11>)            environment=os.getenv("ENV", "development"),
    [](<#cb29-12>)            traces_sample_rate=0.1
    [](<#cb29-13>)        )
```

### Prometheus Metrics
```python
    [](<#cb30-1>)# metrics.py
    [](<#cb30-2>)from prometheus_client import Counter, Histogram, Gauge, start_http_server
    [](<#cb30-3>)
    [](<#cb30-4>)# Metrics
    [](<#cb30-5>)evaluation_counter = Counter('agent_evaluations_total', 'Total evaluations', ['environment'])
    [](<#cb30-6>)evaluation_duration = Histogram('agent_evaluation_duration_seconds', 'Evaluation duration')
    [](<#cb30-7>)threshold_failures = Counter('agent_threshold_failures_total', 'Threshold failures', ['metric'])
    [](<#cb30-8>)tcr_gauge = Gauge('agent_tcr', 'Task Completion Rate')
    [](<#cb30-9>)
    [](<#cb30-10>)def start_metrics_server(port=9090):
    [](<#cb30-11>)    """Prometheus 메트릭 서버 시작"""
    [](<#cb30-12>)    start_http_server(port)
```

* * *

## Security

### API Key Management

**DO** : - 환경 변수로 관리 - Secrets Manager 사용 (AWS Secrets Manager, HashiCorp Vault) - CI/CD에서 안전하게 주입
```json
    [](<#cb31-1>)# .env (Git에 커밋하지 말 것!)
    [](<#cb31-2>)OPENAI_API_KEY=sk-...
```

**DON’T** : - 코드에 하드코딩 - Git에 커밋 - 로그에 출력

### Input Validation
```python
    [](<#cb32-1>)def validate_input(question: str):
    [](<#cb32-2>)    """입력 검증"""
    [](<#cb32-3>)    if not question or len(question) > 10000:
    [](<#cb32-4>)        raise ValueError("Invalid question length")
    [](<#cb32-5>)
    [](<#cb32-6>)    # SQL Injection 방지
    [](<#cb32-7>)    if any(keyword in question.lower() for keyword in ["drop", "delete", "truncate"]):
    [](<#cb32-8>)        raise ValueError("Suspicious input detected")
    [](<#cb32-9>)
    [](<#cb32-10>)    return True
```

### Rate Limiting
```python
    [](<#cb33-1>)from functools import wraps
    [](<#cb33-2>)import time
    [](<#cb33-3>)
    [](<#cb33-4>)def rate_limit(max_calls, period):
    [](<#cb33-5>)    """Rate limiting decorator"""
    [](<#cb33-6>)    calls = []
    [](<#cb33-7>)
    [](<#cb33-8>)    def decorator(func):
    [](<#cb33-9>)        @wraps(func)
    [](<#cb33-10>)        def wrapper(*args, **kwargs):
    [](<#cb33-11>)            now = time.time()
    [](<#cb33-12>)            calls[:] = [c for c in calls if c > now - period]
    [](<#cb33-13>)
    [](<#cb33-14>)            if len(calls) >= max_calls:
    [](<#cb33-15>)                raise Exception("Rate limit exceeded")
    [](<#cb33-16>)
    [](<#cb33-17>)            calls.append(now)
    [](<#cb33-18>)            return func(*args, **kwargs)
    [](<#cb33-19>)
    [](<#cb33-20>)        return wrapper
    [](<#cb33-21>)    return decorator
    [](<#cb33-22>)
    [](<#cb33-23>)@rate_limit(max_calls=100, period=60)
    [](<#cb33-24>)def evaluate_agent(question):
    [](<#cb33-25>)    """Rate limited evaluation"""
    [](<#cb33-26>)    pass
```

* * *

## Performance Optimization

### Caching
```python
    [](<#cb34-1>)from functools import lru_cache
    [](<#cb34-2>)
    [](<#cb34-3>)@lru_cache(maxsize=1000)
    [](<#cb34-4>)def compute_similarity(text1: str, text2: str):
    [](<#cb34-5>)    """유사도 계산 캐싱"""
    [](<#cb34-6>)    # 계산 로직
    [](<#cb34-7>)    pass
```

### Batch Processing
```python
    [](<#cb35-1>)def batch_evaluate(questions: List[str], batch_size=10):
    [](<#cb35-2>)    """배치 평가로 성능 향상"""
    [](<#cb35-3>)    results = []
    [](<#cb35-4>)
    [](<#cb35-5>)    for i in range(0, len(questions), batch_size):
    [](<#cb35-6>)        batch = questions[i:i+batch_size]
    [](<#cb35-7>)        batch_results = [evaluate(q) for q in batch]
    [](<#cb35-8>)        results.extend(batch_results)
    [](<#cb35-9>)
    [](<#cb35-10>)    return results
```

### Parallel Execution
```python
    [](<#cb36-1>)from concurrent.futures import ThreadPoolExecutor
    [](<#cb36-2>)
    [](<#cb36-3>)def parallel_evaluate(questions: List[str], max_workers=4):
    [](<#cb36-4>)    """병렬 평가"""
    [](<#cb36-5>)    with ThreadPoolExecutor(max_workers=max_workers) as executor:
    [](<#cb36-6>)        results = list(executor.map(evaluate, questions))
    [](<#cb36-7>)    return results
```

* * *

## Troubleshooting

### Common Issues

#### Issue 1: Import Error
```python
    ModuleNotFoundError: No module named 'agent_evaluator'
```

**Solution** :
```bash
    [](<#cb38-1>)pip install agent-evaluator
```

#### Issue 2: API Key Error
```python
    AuthenticationError: Invalid API key
```

**Solution** :
```bash
    [](<#cb40-1>)export OPENAI_API_KEY='your-valid-key'
```

#### Issue 3: Memory Error
```python
    MemoryError: Unable to allocate memory
```

**Solution** : - Reduce batch size - Enable caching - Increase system RAM

* * *

## Maintenance

### Updating Agent Evaluator
```bash
    [](<#cb42-1>)# 최신 버전으로 업데이트
    [](<#cb42-2>)pip install --upgrade agent-evaluator
    [](<#cb42-3>)
    [](<#cb42-4>)# 특정 버전으로 업데이트
    [](<#cb42-5>)pip install agent-evaluator==0.6.3
```

### Golden Dataset Maintenance

  * **주간** : 실패한 QAPair 검토
  * **월간** : 새 QAPair 추가, 오래된 것 제거
  * **분기** : 전체 Dataset 재검토

### Threshold Review

  * **주간** : 현재 성능 확인, 작은 조정
  * **월간** : Threshold 상향
  * **분기** : 전체 Threshold 체계 재검토

* * *

## Production Checklist

배포 전 확인 사항:

### 1\. 환경 설정 확인
```json
    [](<#cb43-1>)# ✓ Python 버전 확인
    [](<#cb43-2>)python --version  # 3.11+ 권장
    [](<#cb43-3>)
    [](<#cb43-4>)# ✓ 의존성 설치 확인
    [](<#cb43-5>)pip list | grep -E "numpy|pandas|fastapi|uvicorn"
    [](<#cb43-6>)
    [](<#cb43-7>)# ✓ 환경 변수 확인
    [](<#cb43-8>)python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('OPENAI_API_KEY:', 'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET')"
    [](<#cb43-9>)
    [](<#cb43-10>)# ✓ 디렉토리 구조 확인
    [](<#cb43-11>)ls -la golden_datasets/ evaluation_results/
```

### 2\. 기능 테스트
```bash
    [](<#cb44-1>)# ✓ Core 모듈 import 테스트
    [](<#cb44-2>)python -c "
    [](<#cb44-3>)from agent_evaluator import PerformanceMonitor, HybridPerformanceMonitor
    [](<#cb44-4>)print('All imports successful')
    [](<#cb44-5>)"
    [](<#cb44-6>)
    [](<#cb44-7>)# ✓ Golden Dataset 로드 테스트
    [](<#cb44-8>)python -c "
    [](<#cb44-9>)import json
    [](<#cb44-10>)with open('data/golden_datasets/sample_dataset.json', 'r', encoding='utf-8') as f:
    [](<#cb44-11>)    data = json.load(f)
    [](<#cb44-12>)print(f'Golden Dataset loaded: {len(data)} QA pairs')
    [](<#cb44-13>)"
    [](<#cb44-16>)
    [](<#cb44-17>)# ✓ 패키지 import 테스트
    [](<#cb44-18>)python -c "from agent_evaluator import PerformanceMonitor; print('✅ Package import OK')"
```

### 3\. 성능 및 보안
```bash
    [](<#cb45-1>)# ✓ .env 파일이 Git에 포함되지 않았는지 확인
    [](<#cb45-2>)git check-ignore .env  # .env 출력되어야 함
    [](<#cb45-3>)
    [](<#cb45-4>)# ✓ API 키 노출 확인
    [](<#cb45-5>)grep -r "sk-" *.py | grep -v ".env" | grep -v "# " || echo "No API keys in code"
    [](<#cb45-6>)
    [](<#cb45-7>)# ✓ 메모리 사용량 확인 (Python 프로세스)
    [](<#cb45-8>)python -c "
    [](<#cb45-9>)from agent_evaluator import PerformanceMonitor
    [](<#cb45-10>)import sys
    [](<#cb45-11>)monitor = PerformanceMonitor()
    [](<#cb45-12>)print(f'Memory usage: {sys.getsizeof(monitor)} bytes')
    [](<#cb45-13>)"
```

### 4\. CI/CD 통합 확인
```json
    [](<#cb46-1>)# ✓ Quality Gate 스크립트 테스트
    [](<#cb46-2>)python scripts/quality_gate.py
    [](<#cb46-3>)
    [](<#cb46-4>)# ✓ Threshold 설정 확인
    [](<#cb46-5>)python -c "
    [](<#cb46-6>)from agent_evaluator import PerformanceMonitor
    [](<#cb46-7>)monitor = PerformanceMonitor()
    [](<#cb46-8>)monitor.thresholds = {'tcr': 95.0, 'accuracy': 90.0}
    [](<#cb46-9>)print('Thresholds:', monitor.thresholds)
    [](<#cb46-10>)"
```

### 5\. Docker 배포 (선택)
```bash
    [](<#cb47-1>)# ✓ Dockerfile 존재 확인
    [](<#cb47-2>)test -f Dockerfile && echo "Dockerfile exists" || echo "Dockerfile missing"
    [](<#cb47-3>)
    [](<#cb47-4>)# ✓ docker-compose.yml 확인
    [](<#cb47-5>)test -f docker-compose.yml && echo "docker-compose.yml exists" || echo "docker-compose.yml missing"
    [](<#cb47-6>)
    [](<#cb47-7>)# ✓ Docker 이미지 빌드 테스트
    [](<#cb47-8>)docker build -t agent-evaluator:test .
    [](<#cb47-9>)
    [](<#cb47-10>)# ✓ 컨테이너 실행 테스트
    [](<#cb47-11>)docker run --rm -e ENV=test agent-evaluator:test python -c "import agent_evaluator; print('OK')"
```

### 6\. 문서화

  * README.md 업데이트
  * 팀 위키에 배포 프로세스 문서화
  * API 키 관리 방법 공유
  * 트러블슈팅 가이드 작성
  * 환경별 Threshold 설정 문서화

### 7\. 모니터링 설정

  * Sentry DSN 설정 (선택)
  * Slack Webhook 설정 (선택)
  * 로그 수집 경로 확인
  * 디스크 공간 모니터링 설정
  * 백업 전략 수립

* * *

## Quick Reference

### 주요 파일 위치
```python
    Agent_Evaluator/
    ├── agent_evaluator/                          # Core Python Package
    │   ├── core/
    │   │   ├── agent_evaluator.py                # PerformanceMonitor 클래스
    │   │   └── hybrid_monitor.py                 # HybridPerformanceMonitor 클래스
    │   ├── integrations/                         # Framework 통합
    │   ├── utils/                                # 유틸리티 (path_helpers 등)
    │   └── helpers/                              # Helper 클래스
    ├── Evaluator_Examples/                       # 예제 코드
    │   └── Dashboard/                            # Dashboard 데이터 디렉토리
    │       └── data/                             # 데이터 저장소
    │           ├── evaluation_results/           # 평가 결과
    │           └── golden_datasets/              # Golden Dataset
    ├── requirements.txt                          # Core 패키지 의존성
    ├── setup.py                                  # PyPI 패키징
    └── .env                                      # 환경 변수 (OPENAI_API_KEY)
```

### 주요 명령어
```bash
    [](<#cb49-1>)# Dashboard 실행
    [](<#cb49-2>)agent-eval dashboard
    [](<#cb49-3>)
    [](<#cb49-4>)# Quality Gate 실행 (예제 스크립트)
    [](<#cb49-5>)python scripts/quality_gate.py  # 사용자가 직접 작성 필요
    [](<#cb49-6>)
    [](<#cb49-7>)# Golden Dataset 생성 (예제)
    [](<#cb49-8>)python Evaluator_Examples/03_golden_dataset_evaluation_example.py
    [](<#cb49-9>)
    [](<#cb49-10>)# Layer 2 메트릭 평가 (예제)
    [](<#cb49-11>)python Evaluator_Examples/07_framework_with_layer2_example.py
    [](<#cb49-12>)
    [](<#cb49-13>)# Hybrid 평가 (Layer 3, 예제)
    [](<#cb49-14>)python Evaluator_Examples/01_hybrid_evaluation_example.py
```

### 환경 변수
```json
    [](<#cb50-1>)# 필수
    [](<#cb50-2>)OPENAI_API_KEY=your-api-key-here
    [](<#cb50-3>)
    [](<#cb50-4>)# 선택
    [](<#cb50-5>)ENV=development|staging|production
    [](<#cb50-6>)LOG_LEVEL=DEBUG|INFO|WARNING|ERROR
    [](<#cb50-7>)GOLDEN_DATASET_PATH=golden_datasets/sample_dataset.json
    [](<#cb50-8>)ALERT_WEBHOOK=https://hooks.slack.com/services/...
    [](<#cb50-9>)SENTRY_DSN=https://...
```

### 포트 및 네트워크
```python
    FastAPI Dashboard:   http://localhost:8765
    Docker Dashboard:    http://localhost:8765
    Health Check:        http://localhost:8765/health
```

* * *

## Next Steps

배포를 완료했다면:

  1. **모니터링 설정** : Sentry, Prometheus 통합
  2. **알림 설정** : Slack, Email 알림
  3. **Dashboard 확인** : 실시간 메트릭 모니터링
  4. **문서화** : 팀 위키에 배포 프로세스 문서화
  5. **Golden Dataset 구축** : 프로덕션 환경에 맞는 Golden Dataset 생성
  6. **Threshold 조정** : 프로덕션 데이터 기반 Threshold 최적화
  7. **CI/CD 통합** : GitLab CI, Jenkins 설정
  8. **팀 교육** : 평가 시스템 사용법 교육

* * *

## 💻 개발자 가이드 (Developer Guide)

Agent Evaluator를 효율적으로 배포하고 관리하기 위한 개발자 중심의 실전 가이드입니다.

### 13.1 배포 자동화

#### 13.1.1 배포 스크립트 (deploy.sh)
```python
    #!/bin/bash
    # deploy.sh - Agent Evaluator 자동 배포 스크립트
    set -e  # Exit on error
    
    # 설정
    ENV=${1:-staging}  # dev, staging, production
    VERSION=${2:-latest}
    DEPLOY_DIR="/opt/agent-evaluator"
    BACKUP_DIR="/opt/backups"
    LOG_FILE="/var/log/agent-evaluator/deploy.log"
    
    # 색상 출력
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[1;33m'
    NC='\033[0m'  # No Color
    
    log() {
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
    }
    
    success() {
        echo -e "${GREEN}✓ $1${NC}" | tee -a "$LOG_FILE"
    }
    
    error() {
        echo -e "${RED}✗ $1${NC}" | tee -a "$LOG_FILE"
        exit 1
    }
    
    warn() {
        echo -e "${YELLOW}⚠ $1${NC}" | tee -a "$LOG_FILE"
    }
    
    # 1. Pre-deployment checks
    log "=== Pre-deployment checks ==="
    
    # Check environment
    if [[ ! "$ENV" =~ ^(dev|staging|production)$ ]]; then
        error "Invalid environment: $ENV (must be dev, staging, or production)"
    fi
    
    # Check Python version
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    REQUIRED_VERSION="3.9"
    if [[ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]]; then
        error "Python $REQUIRED_VERSION+ required, found $PYTHON_VERSION"
    fi
    success "Python version: $PYTHON_VERSION"
    
    # Check disk space (minimum 5GB)
    AVAILABLE_SPACE=$(df -BG "$DEPLOY_DIR" | tail -1 | awk '{print $4}' | sed 's/G//')
    if [ "$AVAILABLE_SPACE" -lt 5 ]; then
        error "Insufficient disk space: ${AVAILABLE_SPACE}GB (minimum 5GB required)"
    fi
    success "Disk space: ${AVAILABLE_SPACE}GB available"
    
    # Check if service is running
    if systemctl is-active --quiet agent-evaluator; then
        warn "Service is running, will restart after deployment"
        SERVICE_WAS_RUNNING=true
    else
        SERVICE_WAS_RUNNING=false
    fi
    
    # 2. Backup current version
    log "=== Backup current version ==="
    BACKUP_FILE="$BACKUP_DIR/agent-evaluator-$(date +%Y%m%d-%H%M%S).tar.gz"
    mkdir -p "$BACKUP_DIR"
    
    if [ -d "$DEPLOY_DIR" ]; then
        tar -czf "$BACKUP_FILE" -C "$DEPLOY_DIR" .
        success "Backup created: $BACKUP_FILE"
    else
        warn "No existing installation to backup"
    fi
    
    # 3. Pull latest code
    log "=== Pull latest code ==="
    cd "$DEPLOY_DIR"
    
    if [ "$VERSION" == "latest" ]; then
        git fetch origin
        git checkout main
        git pull origin main
    else
        git fetch --tags
        git checkout "$VERSION"
    fi
    success "Code updated to version: $(git describe --tags --always)"
    
    # 4. Install dependencies
    log "=== Install dependencies ==="
    
    # Create/activate conda environment
    if ! conda env list | grep -q "^Evaluator "; then
        conda create --name Evaluator python=3.11 -y
        success "Conda environment created"
    fi
    
    source activate Evaluator
    
    # Upgrade pip
    pip install --upgrade pip setuptools wheel
    
    # Install requirements based on environment
    if [ "$ENV" == "production" ]; then
        pip install agent-evaluator --no-cache-dir
    else
        pip install agent-evaluator
        # pip install -r requirements-dev.txt  # Dev dependencies for local dev
    fi
    success "Dependencies installed"
    
    # 5. Run migrations (if any)
    log "=== Run migrations ==="
    # Add migration commands here if needed
    success "Migrations completed"
    
    # 6. Run tests (non-production only)
    if [ "$ENV" != "production" ]; then
        log "=== Run tests ==="
        pytest tests/ -v --tb=short || warn "Some tests failed"
    fi
    
    # 7. Build assets (if needed)
    log "=== Build assets ==="
    # Add asset build commands here
    success "Assets built"
    
    # 8. Update configuration
    log "=== Update configuration ==="
    cp "config/$ENV.env" .env
    success "Configuration updated for $ENV"
    
    # 9. Restart service
    log "=== Restart service ==="
    if [ "$SERVICE_WAS_RUNNING" = true ]; then
        sudo systemctl restart agent-evaluator
        sleep 5
    
        if systemctl is-active --quiet agent-evaluator; then
            success "Service restarted successfully"
        else
            error "Service failed to start"
        fi
    else
        sudo systemctl start agent-evaluator
        success "Service started"
    fi
    
    # 10. Health check
    log "=== Health check ==="
    MAX_RETRIES=10
    RETRY_COUNT=0
    HEALTH_URL="http://localhost:8000/health"
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -f -s "$HEALTH_URL" > /dev/null; then
            success "Health check passed"
            break
        fi
    
        RETRY_COUNT=$((RETRY_COUNT + 1))
        warn "Health check attempt $RETRY_COUNT/$MAX_RETRIES failed, retrying..."
        sleep 3
    done
    
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        error "Health check failed after $MAX_RETRIES attempts"
    fi
    
    # 11. Smoke tests
    log "=== Smoke tests ==="
    python3 scripts/smoke_test.py --env "$ENV" || error "Smoke tests failed"
    success "Smoke tests passed"
    
    # 12. Cleanup old backups (keep last 10)
    log "=== Cleanup old backups ==="
    ls -t "$BACKUP_DIR"/*.tar.gz | tail -n +11 | xargs -r rm
    success "Old backups cleaned up"
    
    log "=== Deployment completed successfully ==="
    log "Environment: $ENV"
    log "Version: $(git describe --tags --always)"
    log "Backup: $BACKUP_FILE"
    
```

#### 13.1.2 CI/CD 파이프라인 통합

**GitHub Actions 예제**
```python
    # .github/workflows/deploy.yml
    name: Deploy Agent Evaluator
    
    on:
      push:
        branches:
          - main
          - staging
          - develop
      workflow_dispatch:
        inputs:
          environment:
            description: 'Deployment environment'
            required: true
            type: choice
            options:
              - dev
              - staging
              - production
    
    jobs:
      test:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v3
    
          - name: Set up Python
            uses: actions/setup-python@v4
            with:
              python-version: '3.11'
    
          - name: Cache dependencies
            uses: actions/cache@v3
            with:
              path: ~/.cache/pip
              key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
    
          - name: Install dependencies
            run: |
              pip install agent-evaluator
              # pip install -r requirements-dev.txt  # For linting/testing tools
    
          - name: Run linters
            run: |
              flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
              black --check .
              isort --check-only .
    
          - name: Run tests
            run: |
              pytest tests/ -v --cov=agent_evaluator --cov-report=xml
    
          - name: Upload coverage
            uses: codecov/codecov-action@v3
            with:
              file: ./coverage.xml
    
      deploy:
        needs: test
        runs-on: ubuntu-latest
        environment:
          name: ${{ github.event.inputs.environment || 'staging' }}
    
        steps:
          - uses: actions/checkout@v3
    
          - name: Set deployment environment
            id: set-env
            run: |
              if [ "${{ github.ref }}" == "refs/heads/main" ]; then
                echo "ENV=production" >> $GITHUB_OUTPUT
              elif [ "${{ github.ref }}" == "refs/heads/staging" ]; then
                echo "ENV=staging" >> $GITHUB_OUTPUT
              else
                echo "ENV=dev" >> $GITHUB_OUTPUT
              fi
    
          - name: Deploy to server
            uses: appleboy/ssh-action@master
            with:
              host: ${{ secrets.DEPLOY_HOST }}
              username: ${{ secrets.DEPLOY_USER }}
              key: ${{ secrets.DEPLOY_KEY }}
              script: |
                cd /opt/agent-evaluator
                ./deploy.sh ${{ steps.set-env.outputs.ENV }}
    
          - name: Notify Slack
            if: always()
            uses: 8398a7/action-slack@v3
            with:
              status: ${{ job.status }}
              text: |
                Deployment to ${{ steps.set-env.outputs.ENV }}
                Result: ${{ job.status }}
                Commit: ${{ github.sha }}
              webhook_url: ${{ secrets.SLACK_WEBHOOK }}
    
```

#### 13.1.3 Blue-Green 배포 스크립트
```python
    #!/usr/bin/env python3
    """
    blue_green_deploy.py - Blue-Green 배포 자동화
    """
    import os
    import sys
    import time
    import subprocess
    from typing import Tuple
    
    class BlueGreenDeployer:
        def __init__(self, environment: str):
            self.environment = environment
            self.blue_port = 8000
            self.green_port = 8001
            self.nginx_config = f"/etc/nginx/sites-available/agent-evaluator-{environment}"
    
        def get_active_env(self) -> str:
            """현재 활성화된 환경 확인 (blue 또는 green)"""
            try:
                with open(self.nginx_config, 'r') as f:
                    config = f.read()
                    if f"proxy_pass http://localhost:{self.blue_port}" in config:
                        return "blue"
                    else:
                        return "green"
            except FileNotFoundError:
                return "blue"  # Default
    
        def get_target_env(self) -> Tuple[str, int]:
            """배포할 타겟 환경 결정"""
            active = self.get_active_env()
            if active == "blue":
                return "green", self.green_port
            else:
                return "blue", self.blue_port
    
        def deploy_to_target(self, target: str, port: int) -> bool:
            """타겟 환경에 새 버전 배포"""
            print(f"🚀 Deploying to {target} environment (port {port})...")
    
            # 1. Stop target service
            subprocess.run([
                "sudo", "systemctl", "stop", f"agent-evaluator-{target}"
            ])
    
            # 2. Update code
            deploy_dir = f"/opt/agent-evaluator-{target}"
            subprocess.run(["git", "pull"], cwd=deploy_dir, check=True)
    
            # 3. Install dependencies (using conda environment)
            conda_env_path = os.path.expanduser("~/anaconda3/envs/Evaluator/bin/pip")
            subprocess.run([
                conda_env_path, "install", "-r",
                f"{deploy_dir}/requirements.txt"
            ], check=True)
    
            # 4. Update environment config
            subprocess.run([
                "cp", f"{deploy_dir}/config/{self.environment}.env",
                f"{deploy_dir}/.env"
            ], check=True)
    
            # 5. Start target service
            subprocess.run([
                "sudo", "systemctl", "start", f"agent-evaluator-{target}"
            ], check=True)
    
            # 6. Wait for service to be ready
            print(f"⏳ Waiting for {target} service to be ready...")
            for i in range(30):
                try:
                    result = subprocess.run([
                        "curl", "-f", "-s",
                        f"http://localhost:{port}/health"
                    ], capture_output=True, timeout=5)
    
                    if result.returncode == 0:
                        print(f"✓ {target} service is ready")
                        return True
                except subprocess.TimeoutExpired:
                    pass
    
                time.sleep(2)
    
            print(f"✗ {target} service failed to start")
            return False
    
        def smoke_test(self, port: int) -> bool:
            """Smoke test 실행"""
            print(f"🧪 Running smoke tests on port {port}...")
    
            tests = [
                f"http://localhost:{port}/health",
                f"http://localhost:{port}/api/metrics",
                f"http://localhost:{port}/api/evaluations"
            ]
    
            for url in tests:
                result = subprocess.run([
                    "curl", "-f", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                    url
                ], capture_output=True, text=True)
    
                status_code = result.stdout.strip()
                if status_code not in ["200", "204"]:
                    print(f"✗ Test failed: {url} returned {status_code}")
                    return False
    
            print("✓ All smoke tests passed")
            return True
    
        def switch_traffic(self, target_port: int) -> bool:
            """트래픽을 타겟 환경으로 전환"""
            print(f"🔄 Switching traffic to port {target_port}...")
    
            # Update Nginx config
            with open(self.nginx_config, 'r') as f:
                config = f.read()
    
            # Replace proxy_pass port
            import re
            new_config = re.sub(
                r'proxy_pass http://localhost:\d+',
                f'proxy_pass http://localhost:{target_port}',
                config
            )
    
            with open(self.nginx_config, 'w') as f:
                f.write(new_config)
    
            # Reload Nginx
            result = subprocess.run(
                ["sudo", "nginx", "-t"],
                capture_output=True
            )
    
            if result.returncode != 0:
                print("✗ Nginx config test failed")
                return False
    
            subprocess.run(["sudo", "systemctl", "reload", "nginx"], check=True)
            print("✓ Traffic switched successfully")
            return True
    
        def rollback(self, active_env: str, active_port: int):
            """배포 실패 시 롤백"""
            print(f"⚠️ Rolling back to {active_env} (port {active_port})...")
            self.switch_traffic(active_port)
            print("✓ Rollback completed")
    
        def deploy(self):
            """Blue-Green 배포 실행"""
            print("=== Blue-Green Deployment Started ===")
    
            # 1. 현재 활성 환경 확인
            active_env = self.get_active_env()
            target_env, target_port = self.get_target_env()
            active_port = self.blue_port if active_env == "blue" else self.green_port
    
            print(f"Active: {active_env} (port {active_port})")
            print(f"Target: {target_env} (port {target_port})")
    
            # 2. 타겟 환경에 배포
            if not self.deploy_to_target(target_env, target_port):
                print("✗ Deployment failed")
                sys.exit(1)
    
            # 3. Smoke test
            if not self.smoke_test(target_port):
                print("✗ Smoke tests failed, stopping deployment")
                sys.exit(1)
    
            # 4. 트래픽 전환
            if not self.switch_traffic(target_port):
                print("✗ Traffic switch failed")
                self.rollback(active_env, active_port)
                sys.exit(1)
    
            # 5. Final validation
            time.sleep(5)
            if not self.smoke_test(target_port):
                print("✗ Post-switch validation failed")
                self.rollback(active_env, active_port)
                sys.exit(1)
    
            print("=== Deployment Completed Successfully ===")
            print(f"New active environment: {target_env} (port {target_port})")
    
    if __name__ == "__main__":
        if len(sys.argv) < 2:
            print("Usage: python3 blue_green_deploy.py ")
            sys.exit(1)
    
        environment = sys.argv[1]
        deployer = BlueGreenDeployer(environment)
        deployer.deploy()
    
```

### 13.2 환경별 배포 전략

#### 13.2.1 환경 구성 매트릭스

환경 | 목적 | 배포 주기 | 승인 프로세스 | 롤백 정책  
---|---|---|---|---  
🔧 Development | 개발자 로컬 테스트 | 수시 (push 시마다) | 승인 불필요 | 자동 롤백 (테스트 실패 시)  
🧪 Staging | QA 테스트, 통합 검증 | 일 1~2회 | Tech Lead 승인 | 자동 롤백 (smoke test 실패)  
🚀 Production | 실사용자 서비스 | 주 1회 (정기 배포) | PM + Tech Lead 승인 | 수동 롤백 (모니터링 기반)  
🔬 Canary | 일부 사용자 선행 배포 | Production 배포 전 | PM + Tech Lead 승인 | 자동 롤백 (에러율 > 1%)  
  
#### 13.2.2 환경별 설정 파일 관리
```
    # 디렉토리 구조
    config/
    ├── common.env          # 공통 설정
    ├── dev.env            # 개발 환경
    ├── staging.env        # 스테이징 환경
    ├── production.env     # 프로덕션 환경
    └── secrets/           # 민감 정보 (Git 제외)
        ├── dev-secrets.env
        ├── staging-secrets.env
        └── prod-secrets.env
    
```

**환경 설정 예시**
```python
    # config/production.env
    # Application
    APP_ENV=production
    DEBUG=false
    LOG_LEVEL=INFO
    
    # Database
    DB_HOST=prod-db.example.com
    DB_PORT=5432
    DB_NAME=agent_evaluator_prod
    DB_POOL_SIZE=20
    DB_MAX_OVERFLOW=10
    
    # Cache
    REDIS_HOST=prod-redis.example.com
    REDIS_PORT=6379
    REDIS_DB=0
    CACHE_TTL=3600
    
    # Monitoring
    SENTRY_DSN=https://xxx@sentry.io/yyy
    SENTRY_ENVIRONMENT=production
    ENABLE_APM=true
    APM_SERVICE_NAME=agent-evaluator-prod
    
    # Performance
    MAX_WORKERS=8
    WORKER_TIMEOUT=300
    BATCH_SIZE=100
    
    # Security
    ALLOWED_HOSTS=agent-evaluator.example.com
    CORS_ORIGINS=https://app.example.com
    SESSION_COOKIE_SECURE=true
    CSRF_COOKIE_SECURE=true
    
```

#### 13.2.3 Canary 배포 전략
```python
    #!/usr/bin/env python3
    """
    canary_deploy.py - Canary 배포 및 자동 모니터링
    """
    import time
    import requests
    from dataclasses import dataclass
    from typing import Dict, Optional
    
    @dataclass
    class CanaryConfig:
        canary_percentage: int = 10  # 10% 트래픽
        duration_minutes: int = 30
        error_threshold: float = 0.01  # 1% 에러율
        latency_threshold_ms: int = 500
        rollback_on_failure: bool = True
    
    class CanaryDeployer:
        def __init__(self, config: CanaryConfig):
            self.config = config
            self.stable_version = None
            self.canary_version = None
    
        def get_metrics(self, version: str) -> Dict:
            """특정 버전의 메트릭 수집"""
            response = requests.get(
                f"http://localhost:9090/api/v1/query",
                params={
                    "query": f'http_requests_total{{version="{version}"}}'
                }
            )
            data = response.json()
    
            # Parse Prometheus metrics
            total_requests = int(data['data']['result'][0]['value'][1])
    
            # Get error count
            response = requests.get(
                f"http://localhost:9090/api/v1/query",
                params={
                    "query": f'http_requests_total{{version="{version}",status=~"5.."}}'
                }
            )
            error_data = response.json()
            error_count = int(error_data['data']['result'][0]['value'][1]) if error_data['data']['result'] else 0
    
            # Get latency
            response = requests.get(
                f"http://localhost:9090/api/v1/query",
                params={
                    "query": f'http_request_duration_seconds{{version="{version}",quantile="0.95"}}'
                }
            )
            latency_data = response.json()
            p95_latency = float(latency_data['data']['result'][0]['value'][1]) * 1000  # Convert to ms
    
            error_rate = error_count / total_requests if total_requests > 0 else 0
    
            return {
                "total_requests": total_requests,
                "error_count": error_count,
                "error_rate": error_rate,
                "p95_latency_ms": p95_latency
            }
    
        def compare_versions(self) -> bool:
            """Canary와 Stable 버전 비교"""
            stable_metrics = self.get_metrics(self.stable_version)
            canary_metrics = self.get_metrics(self.canary_version)
    
            print(f"\n=== Metrics Comparison ===")
            print(f"Stable: {stable_metrics}")
            print(f"Canary: {canary_metrics}")
    
            # Check error rate
            if canary_metrics['error_rate'] > self.config.error_threshold:
                print(f"❌ Canary error rate too high: {canary_metrics['error_rate']:.2%}")
                return False
    
            if canary_metrics['error_rate'] > stable_metrics['error_rate'] * 2:
                print(f"❌ Canary error rate 2x higher than stable")
                return False
    
            # Check latency
            if canary_metrics['p95_latency_ms'] > self.config.latency_threshold_ms:
                print(f"❌ Canary latency too high: {canary_metrics['p95_latency_ms']:.0f}ms")
                return False
    
            if canary_metrics['p95_latency_ms'] > stable_metrics['p95_latency_ms'] * 1.5:
                print(f"❌ Canary latency 50% higher than stable")
                return False
    
            print("✅ Canary metrics look good")
            return True
    
        def deploy_canary(self):
            """Canary 배포 실행"""
            print(f"=== Canary Deployment Started ===")
            print(f"Config: {self.config}")
    
            # 1. Deploy canary version
            print(f"\n🚀 Deploying canary ({self.config.canary_percentage}% traffic)...")
            # Deploy logic here
    
            # 2. Monitor for duration
            start_time = time.time()
            check_interval = 60  # 1 minute
    
            while time.time() - start_time < self.config.duration_minutes * 60:
                elapsed = int((time.time() - start_time) / 60)
                print(f"\n⏱️ Monitoring... ({elapsed}/{self.config.duration_minutes} minutes)")
    
                if not self.compare_versions():
                    if self.config.rollback_on_failure:
                        print("\n⚠️ Rolling back canary...")
                        # Rollback logic
                        return False
                    else:
                        print("\n⚠️ Metrics concerning but continuing...")
    
                time.sleep(check_interval)
    
            # 3. Final validation
            print(f"\n✅ Canary validation passed")
            print(f"🚀 Promoting canary to 100% traffic...")
            # Promote canary
    
            return True
    
    if __name__ == "__main__":
        config = CanaryConfig(
            canary_percentage=10,
            duration_minutes=30,
            error_threshold=0.01,
            latency_threshold_ms=500
        )
    
        deployer = CanaryDeployer(config)
        deployer.stable_version = "v1.2.3"
        deployer.canary_version = "v1.2.4"
    
        success = deployer.deploy_canary()
        exit(0 if success else 1)
    
```

### 13.3 롤백 및 복구

#### 13.3.1 즉시 롤백 스크립트
```python
    #!/bin/bash
    # rollback.sh - 이전 버전으로 즉시 롤백
    set -e
    
    DEPLOY_DIR="/opt/agent-evaluator"
    BACKUP_DIR="/opt/backups"
    
    # 1. List available backups
    echo "=== Available Backups ==="
    ls -lht "$BACKUP_DIR"/*.tar.gz | head -10
    
    # 2. Select backup
    if [ -z "$1" ]; then
        echo "Usage: ./rollback.sh "
        echo "Example: ./rollback.sh agent-evaluator-20251201-143000.tar.gz"
        exit 1
    fi
    
    BACKUP_FILE="$BACKUP_DIR/$1"
    
    if [ ! -f "$BACKUP_FILE" ]; then
        echo "❌ Backup file not found: $BACKUP_FILE"
        exit 1
    fi
    
    echo "🔄 Rolling back to: $BACKUP_FILE"
    
    # 3. Stop service
    echo "⏸️ Stopping service..."
    sudo systemctl stop agent-evaluator
    
    # 4. Create backup of current state (just in case)
    EMERGENCY_BACKUP="$BACKUP_DIR/emergency-$(date +%Y%m%d-%H%M%S).tar.gz"
    tar -czf "$EMERGENCY_BACKUP" -C "$DEPLOY_DIR" .
    echo "✓ Current state backed up to: $EMERGENCY_BACKUP"
    
    # 5. Extract backup
    echo "📦 Extracting backup..."
    rm -rf "$DEPLOY_DIR"/*
    tar -xzf "$BACKUP_FILE" -C "$DEPLOY_DIR"
    echo "✓ Backup extracted"
    
    # 6. Restart service
    echo "▶️ Starting service..."
    sudo systemctl start agent-evaluator
    
    # 7. Wait and health check
    sleep 5
    MAX_RETRIES=10
    RETRY_COUNT=0
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -f -s "http://localhost:8000/health" > /dev/null; then
            echo "✅ Rollback successful - service is healthy"
            exit 0
        fi
    
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo "⏳ Health check attempt $RETRY_COUNT/$MAX_RETRIES..."
        sleep 3
    done
    
    echo "❌ Rollback completed but health check failed"
    echo "Check logs: sudo journalctl -u agent-evaluator -n 100"
    exit 1
    
```

#### 13.3.2 데이터베이스 마이그레이션 롤백
```python
    #!/usr/bin/env python3
    """
    db_rollback.py - 데이터베이스 마이그레이션 롤백
    """
    import sys
    from alembic.config import Config
    from alembic import command
    
    def rollback_migration(steps: int = 1):
        """마이그레이션 롤백 실행"""
        print(f"🔄 Rolling back {steps} migration(s)...")
    
        # Alembic 설정
        alembic_cfg = Config("alembic.ini")
    
        # 현재 버전 확인
        print("\nCurrent migration:")
        command.current(alembic_cfg, verbose=True)
    
        # 롤백 실행
        print(f"\nRolling back...")
        command.downgrade(alembic_cfg, f"-{steps}")
    
        # 롤백 후 버전 확인
        print("\nAfter rollback:")
        command.current(alembic_cfg, verbose=True)
    
        print("\n✅ Migration rollback completed")
    
    if __name__ == "__main__":
        steps = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    
        print(f"⚠️  WARNING: This will rollback {steps} database migration(s)")
        confirm = input("Are you sure? (yes/no): ")
    
        if confirm.lower() == "yes":
            rollback_migration(steps)
        else:
            print("Rollback cancelled")
    
```

#### 13.3.3 자동 롤백 트리거

트리거 조건 | 임계값 | 롤백 방식 | 알림  
---|---|---|---  
Error Rate 급증 | > 5% (5분 평균) | 즉시 자동 롤백 | Slack + PagerDuty  
Latency 증가 | P95 > 2초 | 10분 대기 후 롤백 | Slack  
Health Check 실패 | 3회 연속 | 즉시 자동 롤백 | PagerDuty  
CPU/Memory 급증 | CPU > 90%, Memory > 95% | 15분 대기 후 롤백 | Slack  
  
### 13.4 배포 디버깅

#### 13.4.1 배포 후 즉시 체크 스크립트
```python
    #!/usr/bin/env python3
    """
    post_deploy_check.py - 배포 후 즉시 실행하는 종합 체크
    """
    import requests
    import subprocess
    import sys
    from typing import List, Tuple
    
    class PostDeployChecker:
        def __init__(self, base_url: str = "http://localhost:8000"):
            self.base_url = base_url
            self.checks_passed = 0
            self.checks_failed = 0
    
        def check(self, name: str, func) -> bool:
            """개별 체크 실행"""
            try:
                print(f"\n🔍 Checking: {name}")
                result, message = func()
                if result:
                    print(f"  ✅ {message}")
                    self.checks_passed += 1
                    return True
                else:
                    print(f"  ❌ {message}")
                    self.checks_failed += 1
                    return False
            except Exception as e:
                print(f"  ❌ Error: {str(e)}")
                self.checks_failed += 1
                return False
    
        def check_health_endpoint(self) -> Tuple[bool, str]:
            """Health endpoint 체크"""
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return True, f"Health check passed: {data}"
            return False, f"Status code: {response.status_code}"
    
        def check_api_endpoints(self) -> Tuple[bool, str]:
            """주요 API endpoints 체크"""
            endpoints = [
                "/api/metrics",
                "/api/evaluations",
                "/api/config"
            ]
    
            for endpoint in endpoints:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                if response.status_code not in [200, 204]:
                    return False, f"{endpoint} returned {response.status_code}"
    
            return True, f"All {len(endpoints)} endpoints responding"
    
        def check_database_connection(self) -> Tuple[bool, str]:
            """데이터베이스 연결 체크"""
            response = requests.get(f"{self.base_url}/api/db-check", timeout=5)
            if response.status_code == 200:
                return True, "Database connection OK"
            return False, "Database connection failed"
    
        def check_service_status(self) -> Tuple[bool, str]:
            """서비스 상태 체크"""
            result = subprocess.run(
                ["systemctl", "is-active", "agent-evaluator"],
                capture_output=True,
                text=True
            )
    
            if result.stdout.strip() == "active":
                return True, "Service is active"
            return False, f"Service status: {result.stdout.strip()}"
    
        def check_logs_for_errors(self) -> Tuple[bool, str]:
            """최근 로그에서 에러 확인"""
            result = subprocess.run(
                ["journalctl", "-u", "agent-evaluator", "-n", "100", "--no-pager"],
                capture_output=True,
                text=True
            )
    
            error_keywords = ["ERROR", "CRITICAL", "Exception", "Traceback"]
            error_count = sum(1 for keyword in error_keywords if keyword in result.stdout)
    
            if error_count == 0:
                return True, "No errors in recent logs"
            return False, f"Found {error_count} error indicators in logs"
    
        def check_disk_space(self) -> Tuple[bool, str]:
            """디스크 공간 체크"""
            result = subprocess.run(
                ["df", "-h", "/opt/agent-evaluator"],
                capture_output=True,
                text=True
            )
    
            lines = result.stdout.strip().split('\n')
            usage_line = lines[1].split()
            usage_pct = int(usage_line[4].rstrip('%'))
    
            if usage_pct < 85:
                return True, f"Disk usage: {usage_pct}%"
            return False, f"Disk usage high: {usage_pct}%"
    
        def check_memory_usage(self) -> Tuple[bool, str]:
            """메모리 사용량 체크"""
            result = subprocess.run(
                ["free", "-m"],
                capture_output=True,
                text=True
            )
    
            lines = result.stdout.strip().split('\n')
            mem_line = lines[1].split()
            total = int(mem_line[1])
            used = int(mem_line[2])
            usage_pct = (used / total) * 100
    
            if usage_pct < 90:
                return True, f"Memory usage: {usage_pct:.1f}%"
            return False, f"Memory usage high: {usage_pct:.1f}%"
    
        def check_process_count(self) -> Tuple[bool, str]:
            """프로세스 수 체크"""
            result = subprocess.run(
                ["pgrep", "-f", "agent-evaluator"],
                capture_output=True,
                text=True
            )
    
            process_count = len(result.stdout.strip().split('\n'))
    
            if 1 <= process_count <= 16:  # 예상 범위
                return True, f"Process count: {process_count}"
            return False, f"Unexpected process count: {process_count}"
    
        def run_all_checks(self):
            """모든 체크 실행"""
            print("="*60)
            print("POST-DEPLOYMENT CHECKS")
            print("="*60)
    
            self.check("Health Endpoint", self.check_health_endpoint)
            self.check("API Endpoints", self.check_api_endpoints)
            self.check("Database Connection", self.check_database_connection)
            self.check("Service Status", self.check_service_status)
            self.check("Recent Logs", self.check_logs_for_errors)
            self.check("Disk Space", self.check_disk_space)
            self.check("Memory Usage", self.check_memory_usage)
            self.check("Process Count", self.check_process_count)
    
            print("\n" + "="*60)
            print(f"RESULTS: {self.checks_passed} passed, {self.checks_failed} failed")
            print("="*60)
    
            if self.checks_failed > 0:
                print("\n⚠️  Some checks failed - investigate before proceeding")
                return False
            else:
                print("\n✅ All checks passed - deployment looks good")
                return True
    
    if __name__ == "__main__":
        checker = PostDeployChecker()
        success = checker.run_all_checks()
        sys.exit(0 if success else 1)
    
```

#### 13.4.2 배포 문제 트러블슈팅 가이드

증상 | 가능한 원인 | 디버깅 방법 | 해결책  
---|---|---|---  
서비스 시작 실패 | 의존성 누락, 설정 오류 | `journalctl -u agent-evaluator -n 100` | 의존성 재설치, 설정 검증  
Health check 실패 | 포트 충돌, 방화벽 | `netstat -tulpn | grep 8000` | 포트 변경, 방화벽 규칙 수정  
DB 연결 실패 | 네트워크, 인증 오류 | `telnet db-host 5432` | DB 연결 정보 확인, 네트워크 점검  
느린 응답 | 리소스 부족, N+1 쿼리 | `htop`, APM 도구 | 리소스 증설, 쿼리 최적화  
메모리 누수 | 객체 해제 누락 | `py-spy top --pid PID` | 메모리 프로파일링, 코드 수정  
  
### 13.5 성능 튜닝

#### 13.5.1 Gunicorn 최적 설정
```python
    # gunicorn_config.py
    import multiprocessing
    import os
    
    # Server socket
    bind = "0.0.0.0:8000"
    backlog = 2048
    
    # Worker processes
    workers = multiprocessing.cpu_count() * 2 + 1
    worker_class = "uvicorn.workers.UvicornWorker"
    worker_connections = 1000
    max_requests = 10000  # Restart worker after N requests
    max_requests_jitter = 1000  # Add randomness to prevent simultaneous restarts
    timeout = 120
    graceful_timeout = 30
    keepalive = 5
    
    # Logging
    accesslog = "/var/log/agent-evaluator/access.log"
    errorlog = "/var/log/agent-evaluator/error.log"
    loglevel = "info"
    access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
    
    # Process naming
    proc_name = "agent-evaluator"
    
    # Server mechanics
    daemon = False
    pidfile = "/var/run/agent-evaluator.pid"
    user = "www-data"
    group = "www-data"
    tmp_upload_dir = None
    
    # SSL (if needed)
    # keyfile = "/path/to/key.pem"
    # certfile = "/path/to/cert.pem"
    
    def on_starting(server):
        """서버 시작 시 실행"""
        print(f"Starting Agent Evaluator with {workers} workers")
    
    def on_reload(server):
        """리로드 시 실행"""
        print("Reloading Agent Evaluator")
    
    def worker_exit(server, worker):
        """워커 종료 시 실행"""
        print(f"Worker {worker.pid} exited")
    
    def pre_fork(server, worker):
        """워커 fork 전 실행"""
        pass
    
    def post_fork(server, worker):
        """워커 fork 후 실행"""
        print(f"Worker spawned (pid: {worker.pid})")
    
```

#### 13.5.2 성능 벤치마크 스크립트
```python
    #!/bin/bash
    # benchmark.sh - 성능 벤치마크 실행
    
    BASE_URL="http://localhost:8000"
    DURATION=60  # seconds
    CONCURRENCY=100
    
    echo "=== Agent Evaluator Performance Benchmark ==="
    echo "Base URL: $BASE_URL"
    echo "Duration: ${DURATION}s"
    echo "Concurrency: $CONCURRENCY"
    
    # 1. Health endpoint
    echo -e "\n--- Health Endpoint ---"
    ab -n 10000 -c $CONCURRENCY -t $DURATION "$BASE_URL/health" | grep -E "Requests per second|Time per request|Transfer rate"
    
    # 2. Metrics endpoint
    echo -e "\n--- Metrics Endpoint ---"
    ab -n 5000 -c $CONCURRENCY -t $DURATION "$BASE_URL/api/metrics" | grep -E "Requests per second|Time per request|Transfer rate"
    
    # 3. Complex evaluation endpoint
    echo -e "\n--- Evaluation Endpoint ---"
    ab -n 1000 -c 50 -t $DURATION -p payload.json -T application/json "$BASE_URL/api/evaluate" | grep -E "Requests per second|Time per request|Transfer rate"
    
    # 4. Locust load test (if available)
    if command -v locust &> /dev/null; then
        echo -e "\n--- Locust Load Test ---"
        locust -f locustfile.py --headless --users $CONCURRENCY --spawn-rate 10 --run-time ${DURATION}s --host $BASE_URL
    fi
    
    echo -e "\n=== Benchmark Completed ==="
    
```

#### 13.5.3 프로덕션 최적화 체크리스트

항목 | 설정 | 영향 | 확인 방법  
---|---|---|---  
✅ Gunicorn workers | (CPU * 2) + 1 | 처리량 2~3배 증가 | `ps aux | grep gunicorn`  
✅ Database pool | min=5, max=20 | DB 연결 대기 시간 감소 | APM 도구  
✅ Redis caching | TTL=3600s | 응답 시간 50% 감소 | `redis-cli INFO stats`  
✅ Nginx gzip | compression level 6 | 대역폭 70% 절약 | `curl -I --compressed`  
✅ Static files CDN | CloudFront | 정적 파일 로딩 80% 빠름 | 브라우저 Network 탭  
✅ Query optimization | Index 추가, N+1 제거 | 쿼리 시간 90% 감소 | `EXPLAIN ANALYZE`  
  
## 참고 문서

### 프로젝트 문서

  * [README](<README.html>) \- 프로젝트 개요
  * [Getting Started](<GETTING_STARTED.html>) \- 빠른 시작 가이드
  * [API Reference](<API_REFERENCE.html>) \- API 레퍼런스
  * [Metrics Guide](<METRICS_GUIDE.html>) \- 메트릭 가이드
  * [Agentic AI Metrics Guide](<AGENTIC_AI_METRICS_GUIDE.html>) \- Layer 2 메트릭
  * [Golden Dataset Guide](<GOLDEN_DATASET_GUIDE.html>) \- Golden Dataset 가이드
  * [Threshold Configuration Guide](<THRESHOLD_CONFIGURATION_GUIDE.html>) \- Threshold 설정
  * [Framework Integration](<FRAMEWORK_INTEGRATION.html>) \- Framework 통합
  * [Data Editor & Transparency Guide](<DATA_EDITOR_TRANSPARENCY_GUIDE.html>) \- 데이터 편집 및 투명성
  * [Zero Configuration Guide](<ZERO_CONFIGURATION_GUIDE.html>) \- Zero Configuration

### 외부 참고 자료

  * [FastAPI Documentation](<https://fastapi.tiangolo.com/>)
  * [Docker Documentation](<https://docs.docker.com/>)
  * [DeepEval Documentation](<https://docs.confident-ai.com/>)
  * [Ragas Documentation](<https://docs.ragas.io/>)

* * *

## 지원 및 문의

  * **Issues** : 버그 리포트 및 기능 요청
  * **Documentation** : docs/ 디렉토리의 상세 문서 참고
  * **Examples** : Evaluator_Examples/ 디렉토리의 예제 코드 참고

* * *

**최종 업데이트** : 2026-04-01
**버전** : v0.7.0
**프로젝트** : Agent Evaluator - AI Agent Performance Evaluation System
**문서 타입** : 배포 가이드 (Deployment Guide)
