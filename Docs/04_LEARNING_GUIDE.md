# 📖 종합 학습 가이드

개발자 & 품질관리자를 위한 완벽 학습서

v0.6.5 — 25개 메트릭 · 3-Layer · 4개 프레임워크

## 📊 1. Agent Evaluator 개요

### What is Agent Evaluator?

Agent Evaluator는 AI Agent의 성능을 다각도로 평가하고 모니터링하는 **종합 평가 프레임워크** 입니다. 기본 메트릭부터 Agentic AI 전문 메트릭, 그리고 고급 평가 지표까지 AI Agent의 품질을 정확하게 측정하고 개선점을 찾아낼 수 있습니다.

### 1.1 주요 특징

#### 🆓 Layer 1: Foundation Metrics

**완전 무료, API 키 불필요 (v0.6.5)**

  * **Foundation (6개):** TCR, Accuracy, Hallucination Detection, Quality, Latency, Token Economy

#### 🤖 Layer 2: Agentic + Security Metrics

**Multi-Agent & 보안 통합 평가 (v0.6.5)**

  * **Agentic (5개):** Tool Call Analysis, Retry/Correction, Tool Selection Accuracy, Agent Coordination, Workflow Execution
  * **Security (5개):** Input Sanitization, Output Leakage, Tool Authorization, Privilege Escalation, Tool Chain Attack Detection

#### 🔬 Layer 3: Advanced Metrics

**LLM 기반 고급 평가 (OpenAI API 필요)**

  * DeepEval (G-Eval, Toxicity, Bias)
  * Ragas (RAG 전용 평가)

### 1.2 프로젝트 통계

항목 | 수량 | 세부사항  
---|---|---  
**코드베이스** | 11개 파일 | 783KB, 23개 클래스, 99개 메서드  
**문서** | 14개 파일 | ~2MB (Docs/ 디렉토리 14개 가이드)  
**예제** | 5개 파일 | Evaluator_Examples/ 디렉토리 (품질/성능/에이전틱/보안/하이브리드 각 1개)  
**메트릭** | 25개 | Layer 1 (6개: Foundation) + Layer 2 (10개: 5 Agentic + 5 Security) + Layer 3 (9개: Hybrid)
**프레임워크 지원** | 4개 | LangChain, CrewAI, LangGraph, AutoGen  
  
### 1.3 사용 대상

#### 👨‍💻 개발자

  * AI Agent 성능 디버깅
  * 프레임워크 통합 및 자동 추적
  * 비용 최적화 (토큰 사용량 분석)
  * CI/CD 품질 게이트 구축

#### 🔍 품질관리자 (QA)

  * Golden Dataset 기반 자동 평가
  * Threshold 설정 및 검증
  * 회귀 테스트 (Regression Testing)
  * 성능 추세 분석

**💡 핵심 가치 제안:** Agent Evaluator는 개발 단계에서는 **무료 Layer 1+2 메트릭 (보안 포함)** 으로 빠른 반복 개발을 지원하고, 프로덕션 배포 전에는 **Golden Dataset + Threshold 검증** 으로 품질 게이트를 제공합니다. 

## 🏗️ 2. 시스템 아키텍처

### 2.1 전체 구조

graph TB subgraph UI["사용자 인터페이스 레이어"] Dashboard["🖥️ FastAPI Dashboard
\- Single Dashboard (Port 8765)
agent-eval dashboard
품질 / 성능 / 에이전틱 / 보안
(관점 기반 네비게이션)"] PythonAPI["🐍 Python API
\- PerformanceMonitor
\- Framework Integration
\- Golden Dataset 평가"] end subgraph Core["핵심 평가 엔진 (Core Evaluation Engine)"] AgentEval["📊 agent_evaluator.py
━━━━━━━━━━━━━━━━━━━━
▸ PerformanceMonitor
▸ Layer 1 Trackers (6개)
• TCR, Accuracy, Hallucination
Quality, Latency, Token Economy
▸ Layer 2 Trackers (10개)
• Agentic (5): Tool Call, Retry
Tool Selection, Coordination, Workflow
• Security (5): Input Sanitization
Output Leakage, Tool Auth
Privilege Escalation, Attack Detection"] HybridMon["🔬 hybrid_monitor.py  
45KB  
━━━━━━━━━━━━━━━━━━━━  
▸ Layer 3 통합  
• DeepEval  
• Ragas  
▸ Profile 관리  
• minimal, balanced  
• rag, full"] Framework["🔌 framework_integrations.py  
26KB, 8 classes  
━━━━━━━━━━━━━━━━━━━━  
▸ LangChain Callback  
▸ LangGraph Workflow  
▸ CrewAI Integration
▸ AutoGen Agent"] end subgraph DataMgmt["데이터 관리 레이어 (Data Management)"] Transparency["🔍 transparency_manager
━━━━━━━━━━━━━━━━━━━━
▸ 메트릭 이상치 탐지
▸ 성능 병목 식별
▸ Audit Log 추적"] end subgraph Storage["저장소 레이어 (Storage)"] GoldenDS["📚 results/golden_datasets/
• QA Pairs (JSON)
• expected_tools
• expected_agents
• expected_workflow_steps"] EvalResults["💾 results/
• *_evaluation.json
• *_report.html"] end Dashboard --> AgentEval PythonAPI --> AgentEval AgentEval --> HybridMon AgentEval --> Framework AgentEval --> Transparency Transparency --> GoldenDS AgentEval --> EvalResults style UI fill:#e0e7ff,stroke:#4f46e5,stroke-width:3px style Core fill:#dbeafe,stroke:#2563eb,stroke-width:3px style DataMgmt fill:#d1fae5,stroke:#10b981,stroke-width:3px style Storage fill:#fef3c7,stroke:#f59e0b,stroke-width:3px style Dashboard fill:#c7d2fe,stroke:#4f46e5,stroke-width:2px style PythonAPI fill:#c7d2fe,stroke:#4f46e5,stroke-width:2px style AgentEval fill:#93c5fd,stroke:#2563eb,stroke-width:2px style HybridMon fill:#93c5fd,stroke:#2563eb,stroke-width:2px style Framework fill:#93c5fd,stroke:#2563eb,stroke-width:2px style Transparency fill:#a7f3d0,stroke:#10b981,stroke-width:2px style GoldenDS fill:#fde68a,stroke:#f59e0b,stroke-width:2px style EvalResults fill:#fde68a,stroke:#f59e0b,stroke-width:2px

### 2.2 데이터 흐름

graph LR subgraph Phase1["Phase 1: 데이터 준비"] A1["📝 Golden Dataset  
작성"] A2["🎯 Threshold  
설정"] end subgraph Phase2["Phase 2: 구성 생성"] B["⚙️ Test Configuration  
생성 및 저장  
━━━━━━━━━━  
▸ 환경 설정  
▸ Dataset 연결  
▸ Threshold 포함"] end subgraph Phase3["Phase 3: 평가 실행"] C1["🤖 Agent 실행"] C2["📊 TaskResult  
생성"] C3["📈 Layer 1/2  
메트릭 기록"] end subgraph Phase4["Phase 4: 검증"] D["✅ Threshold 검증  
━━━━━━━━━━  
compare_with_thresholds()  
→ Pass/Fail 판정"] end subgraph Phase5["Phase 5: 분석"] E1["📊 Dashboard  
시각화"] E2["📝 리포트  
생성"] E3["💡 개선점  
도출"] end A1 --> B A2 --> B B --> C1 C1 --> C2 C2 --> C3 C3 --> D D --> E1 D --> E2 D --> E3 style Phase1 fill:#e0e7ff,stroke:#4f46e5,stroke-width:2px style Phase2 fill:#dbeafe,stroke:#2563eb,stroke-width:2px style Phase3 fill:#d1fae5,stroke:#10b981,stroke-width:2px style Phase4 fill:#fef3c7,stroke:#f59e0b,stroke-width:2px style Phase5 fill:#fee2e2,stroke:#ef4444,stroke-width:2px style A1 fill:#c7d2fe,stroke:#4f46e5 style A2 fill:#c7d2fe,stroke:#4f46e5 style B fill:#93c5fd,stroke:#2563eb style C1 fill:#a7f3d0,stroke:#10b981 style C2 fill:#a7f3d0,stroke:#10b981 style C3 fill:#a7f3d0,stroke:#10b981 style D fill:#fde68a,stroke:#f59e0b style E1 fill:#fecaca,stroke:#ef4444 style E2 fill:#fecaca,stroke:#ef4444 style E3 fill:#fecaca,stroke:#ef4444 

**💡 워크플로우 설명:**

  1. **Phase 1:** Dashboard 또는 Python API로 Golden Dataset과 Threshold 준비
  2. **Phase 2:** 환경별(dev/staging/production) Test Configuration 생성
  3. **Phase 3:** Agent 실행 → TaskResult 생성 → 메트릭 자동 기록
  4. **Phase 4:** 임계값 대비 자동 Pass/Fail 판정
  5. **Phase 5:** Dashboard 시각화 및 개선점 도출

### 2.3 핵심 컴포넌트

컴포넌트 | 역할 | 주요 기능
---|---|---
**core/agent_evaluator.py** | 메인 평가 엔진 | Layer 1+2 트래커 16개 + PerformanceMonitor
**core/hybrid_monitor.py** | Layer 3 통합 | DeepEval, Ragas, LangSmith 어댑터
**integrations/** | 프레임워크 통합 | LangChain, CrewAI, LangGraph, AutoGen 자동 추적
**serve/server.py** | FastAPI 대시보드 서버 | 관점 기반 시각화 (품질/성능/에이전틱/보안), Export
**utils/transparency_manager.py** | Test 투명성 관리 | 이상치 탐지, Traces, Annotations, Audit Log  
  
### 2.4 파일 시스템 구조

#### results/ 디렉토리 구조 (실행 시 자동 생성됨)
```
    results/
    ├── *_evaluation.json              # 평가 결과 데이터 (monitor.save_to_file() 생성)
    ├── *_report.html                  # HTML 리포트
    └── golden_datasets/               # Golden Dataset 파일
        ├── dataset_001.json
        └── ...
```

#### 주요 파일 형식

파일 | 용도 | 관리 방법
---|---|---
**results/*_evaluation.json** | 평가 결과, TaskResult, 메트릭 데이터 | monitor.save_to_file()로 저장
**results/*_report.html** | HTML 시각화 리포트 | monitor.save_to_file() 자동 생성
**results/golden_datasets/*.json** | Golden Dataset (QA 쌍, 도구 기대값) | 수동 작성 또는 API로 생성  
  
**💡 파일 관리 Best Practice:**

  * **evaluation_results/** 디렉토리는 첫 평가 실행 시 자동으로 생성됩니다
  * **versions/** 디렉토리는 자동 백업되므로 수동 관리 불필요
  * **audit_logs/** 는 규정 준수를 위해 정기적으로 아카이빙 권장
  * **test_configs/** 는 환경별로 관리하여 Dev/Staging/Prod 분리
  * 대용량 데이터는 주기적으로 압축 및 클라우드 백업 고려

## 📈 3. 3-Layer 메트릭 체계

### 3.1 Layer 1: Foundation Metrics (6개) - 무료

외부 의존성 없이 즉시 측정 가능한 기본 성능 지표입니다.

메트릭 | 설명 | 계산 방법 | 목표값
---|---|---|---
**TCR** | Task Completion Rate | (성공 작업 수 / 전체 작업 수) × 100 | ≥ 95%
**Accuracy** | 정확도 (의미론적 유사도) | 평균 accuracy_score | ≥ 90%
**Hallucination** | 환각 발생률 | 룰 기반 사실 일관성 검사 | < 1%
**Quality** | 응답 품질 점수 | 5차원 품질 평가 평균 | ≥ 4.0/5
**Latency** | 응답 시간 (P95) | 95 percentile execution_time | < 3s
**Token Economy** | 토큰 비용 분석 | 토큰 사용량 + 비용 추정 | 최소화

**✅ Layer 1의 장점:** 완전 무료, API 키 불필요, 빠른 실행 (외부 호출 없음)

### 3.2 Layer 2: Agentic + Security Metrics (10개) - 무료

#### 📊 Agentic Metrics (5개)

#### 🔄 Retry & Correction

**설명:** Agent의 재시도 및 자기 수정 동작 분석

**계산 방법:**

  * **Retry Rate:** 재시도 발생 비율
  * **Correction Success Rate:** 재시도 후 성공 비율
  * **Convergence Speed:** 목표 달성까지 평균 시도 횟수

**목표값:** Retry Success Rate ≥ 80%

#### 🎯 Tool Selection Accuracy

**설명:** Agent가 적절한 도구를 선택했는지 평가 (Golden Dataset 기반)

**계산 방법:**

  * **Precision:** 올바르게 선택한 도구 / 전체 선택한 도구
  * **Recall:** 올바르게 선택한 도구 / 기대되는 도구
  * **F1 Score:** 2 × (Precision × Recall) / (Precision + Recall)

**목표값:** ≥ 85% (F1 Score)

**사용 시나리오:**

  * LangChain Agent의 도구 선택 정확도 평가
  * Golden Dataset에 expected_tools 정의 필요

#### 🔧 Tool Call Efficiency

**설명:** Agent가 도구를 얼마나 효율적으로 사용하는지 측정 (성공률 및 유용성)

**계산 방법:**

  * **Success Rate:** (성공한 도구 호출 / 전체 도구 호출) × 100
  * **Usefulness Score:** 도구 호출이 최종 결과에 기여한 정도
  * **Overall Efficiency:** (Success Rate × 0.7 + Usefulness × 0.3)

**목표값:** ≥ 90%

**사용 시나리오:**

  * Agent의 도구 사용 효율성 평가
  * 불필요한 도구 호출 감지
  * 도구 실행 실패 패턴 분석

#### 🤝 Agent Coordination

**설명:** Multi-Agent 시스템에서 에이전트 간 협업 품질 측정

**계산 방법:**

  * **Success Rate (50%):** 성공적인 상호작용 비율
  * **Agent Diversity (30%):** 다양한 에이전트 활용도
  * **Interaction Balance (20%):** 균형잡힌 에이전트 사용

**점수 범위:** 0-10 척도

**목표값:** ≥ 8.0

**사용 시나리오:**

  * CrewAI의 Agent 간 협업 평가
  * AutoGen의 대화 흐름 분석

#### ⚙️ Workflow Execution

**설명:** 워크플로우의 각 단계 실행 성공률 측정

**계산 방법:**

  * **Step Success Rate:** (성공 단계 / 전체 단계) × 100
  * **Task Success Rate:** 전체 Task 성공 여부

**목표값:** ≥ 95%

**사용 시나리오:**

  * LangChain Chain의 각 단계 성공률
  * LangGraph의 노드별 실행 추적

#### 🔒 Security Metrics (5개)

보안 트래커는 기본값 `False` — `enable_security_metrics=True`로 활성화.

메트릭 | 설명 | 목표값
---|---|---
**Input Sanitization** | SQL Injection, Command Injection, Path Traversal, XSS, Prompt Injection 탐지 | 0 threats
**Output Leakage** | API 키, 비밀번호, 개인정보 등 민감 데이터 유출 검사 | 0 leaks
**Tool Authorization** | 허가된 도구만 호출했는지 검증 | 100%
**Privilege Escalation** | Agent의 권한 상승 시도 탐지 | 0 escalations
**Tool Chain Attack** | 연쇄 도구 호출을 통한 공격 패턴 탐지 | 0 attacks

**사용 시나리오:**

  * Multi-Agent 시스템 보안 감사
  * 입력/출력 데이터 보안 검증
  * 악의적인 프롬프트 인젝션 방어

**💡 Layer 2의 가치:** Multi-Agent 시스템과 복잡한 워크플로우의 품질을 정량적으로 측정하고, 보안 위협을 실시간으로 탐지합니다. Golden Dataset 기반 자동 평가 지원. 

### 3.3 Layer 3: Advanced Metrics - 유료 (OpenAI API)

#### DeepEval (5개 메트릭)

  * **G-Eval:** LLM 기반 품질 평가 (0-1)
  * **Hallucination:** AI 기반 환각 탐지
  * **Toxicity:** 유해성 점수 (0-1)
  * **Bias:** 편향 점수 (0-1)
  * **Answer Relevancy:** 답변 관련성

**비용:** ~$0.01-0.03/task

#### Ragas - RAG 전용 (4개 메트릭)

  * **Faithfulness:** 컨텍스트 충실도
  * **Context Precision:** 검색 정밀도
  * **Context Recall:** 검색 재현율
  * **Answer Similarity:** 답변 유사도

**비용:** ~$0.02-0.05/task

### 3.4 메트릭 선택 전략

단계 | 권장 메트릭 | 비용 | 목적  
---|---|---|---  
**개발 단계** | Layer 1 + 2 | 무료 | 빠른 반복, 기본 성능 확인  
**테스트 단계** | Layer 1 + 2 + Layer 3 샘플링 (10%) | 저비용 | 품질 검증, 회귀 테스트  
**프로덕션** | Layer 1 + 2 상시 + Layer 3 크리티컬만 | 중비용 | 실시간 모니터링, 이상 탐지  
  
## 🚀 4. 빠른 시작 (Quick Start)

### 4.1 설치

#### 기본 설치 (Layer 1 + 2)
```bash
    # Conda 환경 생성 (권장)
    conda create -n agent_evaluator python=3.11
    conda activate agent_evaluator
    
    # 기본 의존성 설치
    pip install agent-evaluator[serve]
```

#### 전체 설치 (Layer 1 + 2 + 3)
```bash
    # 기본 패키지 설치
    pip install agent-evaluator
    
    # 추가 프레임워크 설치 (필요 시)
    pip install crewai>=1.0.0 langgraph>=1.0.0
    pip install deepeval>=0.20.0 ragas>=0.4.0 "datasets>=4.0.0,<6.0.0"
    
    # .env 파일 생성 (Layer 3 사용 시)
    echo "OPENAI_API_KEY='your-api-key-here'" > .env
```

### 4.2 첫 번째 평가 (5분 완성) - 복사 붙여넣기 즉시 실행!

#### 완전한 실행 가능 예제

아래 코드를 `first_evaluation.py`로 저장하고 `python first_evaluation.py`로 실행하세요!

실행 가능 복사
```python
    #!/usr/bin/env python3
    """
    첫 번째 Agent 평가 - 완전 실행 가능 예제
    실행: python first_evaluation.py
    """
    
    from agent_evaluator import PerformanceMonitor, TaskResult, TaskType
    from datetime import datetime
    import time
    
    # 1. PerformanceMonitor 생성
    print("🚀 Agent Evaluator 시작...")
    monitor = PerformanceMonitor()
    
    # 2. 간단한 Agent 시뮬레이션 (실제로는 LLM 호출)
    def simple_agent(question: str) -> str:
        """시뮬레이션: 실제로는 LLM API 호출"""
        time.sleep(0.5)  # 실행 시간 시뮬레이션
        if "수도" in question:
            return "서울입니다"
        return "답변을 생성했습니다"
    
    # 3. Agent 실행 및 TaskResult 기록
    questions = [
        ("한국의 수도는 어디인가요?", "서울입니다"),
        ("프랑스의 수도는?", "파리입니다"),
        ("일본의 수도는?", "도쿄입니다")
    ]
    
    for i, (question, expected) in enumerate(questions, 1):
        print(f"\n📝 Task {i}: {question}")
    
        # Agent 실행
        start = time.time()
        response = simple_agent(question)
        exec_time = time.time() - start
    
        # TaskResult 생성 (간단한 방식)
        # 참고: 실제 프로덕션에서는 create_taskresult() 헬퍼 함수를 사용하는 것이 권장됩니다!
        # from agent_evaluator import create_taskresult
        accuracy = 1.0 if expected.replace(" ", "").lower() in response.replace(" ", "").lower() else 0.5
    
        task = TaskResult(
            task_id=f"task_{i:03d}",           # 고유 ID
            task_type=TaskType.QA.value,       # 작업 유형: qa
            success=True,                       # 성공 여부
            completion_score=1.0 if len(response) > 5 else 0.5,  # ✅ 동적 계산
            accuracy_score=accuracy,            # ✅ 동적 계산 (간단한 비교)
            execution_time=exec_time,           # 실행 시간 (초)
            tokens_used={                       # 토큰 사용량 (추정)
                "input": len(question) * 2,
                "output": len(response) * 2
            },
            tool_calls=[],                      # 사용한 도구 (없음)
            attempts=1,                         # 재시도 횟수
            errors=[],                          # 에러 목록 (없음)
            timestamp=datetime.now()            # 기록 시간
        )
    
        # 기록
        monitor.record_task(task)
        print(f"   ✅ 기록 완료 (실행시간: {exec_time:.3f}초, 정확도: {accuracy:.1f})")
    
    # 4. 레포트 생성 및 출력
    print("\n" + "="*60)
    print("📊 평가 결과 리포트")
    print("="*60)
    
    report = monitor.generate_report()
    
    print(f"\n✅ Task Completion Rate (TCR): {report['accuracy_metrics']['tcr']:.1f}%")
    print(f"✅ Overall Accuracy: {report['accuracy_metrics']['accuracy']:.1f}%")
    print(f"✅ Average Latency: {report['efficiency_metrics']['latency']['average']:.3f}초")
    print(f"✅ Total Tasks: {report['total_tasks']}개")
    
    print(f"\n💾 레포트 저장...")
    monitor.save_to_file("first_evaluation_report.json")
    print("✅ 저장 완료: first_evaluation_report.json")
    
    print("\n🎉 첫 번째 평가 완료!")
    
```

#### 예상 출력:
```python
    🚀 Agent Evaluator 시작...
    
    📝 Task 1: 한국의 수도는 어디인가요?
       ✅ 기록 완료 (실행시간: 0.502초)
    
    📝 Task 2: 프랑스의 수도는?
       ✅ 기록 완료 (실행시간: 0.501초)
    
    📝 Task 3: 일본의 수도는?
       ✅ 기록 완료 (실행시간: 0.500초)
    
    ============================================================
    📊 평가 결과 리포트
    ============================================================
    
    ✅ Task Completion Rate (TCR): 100.0%
    ✅ Overall Accuracy: 90.0%
    ✅ Average Latency: 0.501초
    ✅ Total Tasks: 3개
    
    💾 레포트 저장...
    ✅ 저장 완료: first_evaluation_report.json
    
    🎉 첫 번째 평가 완료!
```

#### 실습 체크리스트

  * □ PerformanceMonitor 생성 완료
  * □ TaskResult 생성 완료 (11개 필수 필드 확인)
  * □ record_task() 호출 완료
  * □ 레포트 생성 및 확인 완료
  * □ JSON 파일 저장 확인

#### 흔한 문제와 해결

ImportError: No module named 'agent_evaluator'

**원인:** agent_evaluator가 제대로 설치되지 않음

**해결:** pip로 agent-evaluator를 설치하세요
```python
    # agent-evaluator 설치 확인
    pip show agent-evaluator
    
    # 설치되지 않았다면
    pip install agent-evaluator
    
    # 최신 버전으로 업그레이드
    pip install --upgrade agent-evaluator
```

**⚠️ 참고:** v0.5.2부터는 PYTHONPATH 설정이 필요 없습니다. pip install로 패키지를 설치하면 어디서든 import 가능합니다.

TypeError: TaskResult() missing required argument

**원인:** 필수 필드 누락

**해결:** 11개 필수 필드를 모두 제공해야 함

task_id, task_type, success, completion_score, accuracy_score, execution_time, tokens_used, tool_calls, attempts, errors, timestamp

KeyError when accessing report['accuracy_metrics']

**원인:** generate_report() 반환 형식이 다름

**해결:** report가 딕셔너리인지 확인하고 올바른 키 사용
```python
    # 방법 1: 딕셔너리로 접근
    print(report['accuracy_metrics']['tcr'])
    
    # 방법 2: 속성으로 접근 (ReportResult 객체인 경우)
    print(report.accuracy_metrics.tcr)
```

### 4.3 프로그래밍 방식으로 평가 결과 확인
```python
    # 평가 리포트 생성 및 확인
    report = monitor.generate_report()
    
    # 메트릭 확인
    print(f"TCR: {report.accuracy_metrics.tcr}")
    print(f"평균 지연시간: {report.latency_metrics.mean}초")
    print(f"총 비용: ${report.cost_metrics.total_cost}")
    
    # JSON으로 저장
    import json
    with open('evaluation_results.json', 'w') as f:
        json.dump(report.to_dict(), f, indent=2)
```

**사용 가능한 주요 메트릭:**

  * 📊 **정확도 메트릭:** TCR (Task Completion Rate), Accuracy
  * 🎯 **품질 메트릭:** Quality Score, Hallucination Rate
  * ⚡ **성능 메트릭:** Latency (평균, 최소, 최대, 백분위)
  * 💰 **비용 메트릭:** Token 사용량, 총 비용
  * 🤖 **Agentic AI 메트릭:** Tool Selection, Agent Coordination, Workflow Execution (Layer 2)
  * 🔬 **고급 메트릭:** DeepEval, Ragas 평가 (Layer 3, 별도 설치 필요)

**FastAPI Dashboard (Port 8765):**

  * 📊 **통합 관리:** 임계값 설정, Golden Dataset, Test 준비, 이력 관리

**✅ 5분 만에 완료!** 이제 Agent의 성능을 실시간으로 모니터링하고, Dashboard에서 시각화할 수 있습니다. 

## 📝 5. TaskResult 데이터 준비 실전 가이드

**💡 이 섹션의 목적:** Agent Evaluator를 사용하려면 TaskResult 객체를 올바르게 생성해야 합니다. 이 가이드는 다양한 시나리오별로 TaskResult를 준비하는 완전한 실전 예제를 제공합니다. 

### 5.1 TaskResult 클래스 구조

#### 필수 필드 11개 (Layer 1)

필드명 | 타입 | 설명 | 예시  
---|---|---|---  
`task_id` | str | 작업 고유 ID | "task_001"  
`task_type` | str | 작업 유형 (qa, code_generation, summarization 등) | TaskType.QA.value  
`success` | bool | 작업 성공 여부 | True  
`completion_score` | float | 작업 완료도 (0.0~1.0) | 1.0  
`accuracy_score` | float | 응답 정확도 (0.0~1.0) | 0.85  
`execution_time` | float | 실행 시간 (초) | 1.234  
`tokens_used` | Dict | 토큰 사용량 (input, output, total) | {"input": 100, "output": 50}  
`tool_calls` | List[Dict] | 사용한 도구 목록 | [{"name": "search"}]  
`attempts` | int | 재시도 횟수 (1부터 시작) | 1  
`errors` | List[str] | 발생한 에러 목록 | []  
`timestamp` | datetime | 기록 시간 | datetime.now()  
  
#### 선택적 필드 (Layer 2 - Agentic AI)

필드명 | 타입 | 설명  
---|---|---  
`agents_involved` | List[str] | 참여한 Agent 목록 (Multi-Agent 시스템)  
`workflow_steps` | List[str] | 실행된 워크플로우 단계  
  
### 5.2 실제 값 계산 헬퍼 함수

#### 💡 평가 시스템의 핵심: 동적 값 계산

TaskResult의 필드들은 하드코딩이 아닌 **실제 계산 함수** 를 통해 동적으로 생성되어야 합니다. 아래 헬퍼 함수들을 프로젝트에 추가하여 사용하세요.

#### 완전한 헬퍼 함수 모음 (taskresult_helpers.py)

✅ 실행 가능 📋 복사
```python
    #!/usr/bin/env python3
    """
    TaskResult 필드 동적 계산 헬퍼 함수 모음
    파일명: taskresult_helpers.py
    """
    
    import re
    from difflib import SequenceMatcher
    from typing import Any, Dict, List, Tuple
    
    
    # ============================================================================
    # 1. completion_score 계산 (작업 완료도)
    # ============================================================================
    
    def calculate_completion_score(
        response: str,
        expected_min_length: int = 10,
        has_error: bool = False,
        ground_truth: str = None
    ) -> float:
        """
        작업 완료도 점수 계산 (0.0 ~ 1.0)
    
        Args:
            response: Agent의 응답 텍스트
            expected_min_length: 최소 기대 길이
            has_error: 에러 발생 여부
            ground_truth: 기대 답변 (선택적)
    
        Returns:
            float: 0.0 (실패) ~ 1.0 (완전 완료)
    
        Examples:
            >>> calculate_completion_score("서울입니다", expected_min_length=5)
            1.0
            >>> calculate_completion_score("서울", expected_min_length=10)
            0.5
            >>> calculate_completion_score("", has_error=True)
            0.0
        """
        # 1. 에러 발생 시 무조건 0.0
        if has_error:
            return 0.0
    
        # 2. 응답 없음
        if not response or not response.strip():
            return 0.0
    
        # 3. 길이 기반 평가
        response_length = len(response.strip())
    
        if response_length < expected_min_length:
            # 부분 완료: 길이 비율에 따라 0.3 ~ 0.7
            return max(0.3, min(0.7, response_length / expected_min_length))
    
        # 4. Ground truth와 비교 (있는 경우)
        if ground_truth:
            similarity = calculate_text_similarity(response, ground_truth)
            if similarity >= 0.8:
                return 1.0
            elif similarity >= 0.5:
                return 0.7
            else:
                return 0.5
    
        # 5. 기본: 최소 길이 이상이면 완료로 판정
        return 1.0
    
    
    # ============================================================================
    # 2. accuracy_score 계산 (정확도)
    # ============================================================================
    
    def calculate_accuracy_score(
        response: str,
        ground_truth: str,
        method: str = "combined"
    ) -> float:
        """
        정확도 점수 계산 - Agent Evaluator 방식
    
        4가지 유사도 메트릭 조합:
        - Token Overlap Ratio (40%)
        - Jaccard Similarity (30%)
        - Longest Common Subsequence (20%)
        - Character-level Similarity (10%)
    
        Args:
            response: Agent의 실제 응답
            ground_truth: 기대 답변
            method: "combined" (기본) | "simple" | "token_only"
    
        Returns:
            float: 0.0 (완전히 틀림) ~ 1.0 (완벽히 일치)
    
        Examples:
            >>> calculate_accuracy_score("서울입니다", "서울")
            0.85
            >>> calculate_accuracy_score("파리", "서울")
            0.0
        """
        if not response or not ground_truth:
            return 0.0
    
        # 정규화
        resp_norm = normalize_text(response)
        truth_norm = normalize_text(ground_truth)
    
        if method == "simple":
            # 간단한 포함 여부 체크
            if truth_norm in resp_norm:
                return 1.0
            elif any(word in resp_norm for word in truth_norm.split()[:3]):
                return 0.5
            else:
                return 0.0
    
        elif method == "token_only":
            # Token Overlap만 사용
            return _token_overlap_ratio(resp_norm, truth_norm)
    
        else:  # method == "combined" 
            # 1. Token Overlap Ratio (40%)
            token_score = _token_overlap_ratio(resp_norm, truth_norm)
    
            # 2. Jaccard Similarity (30%)
            jaccard_score = _jaccard_similarity(resp_norm, truth_norm)
    
            # 3. Longest Common Subsequence (20%)
            lcs_score = _lcs_similarity(resp_norm, truth_norm)
    
            # 4. Character-level Similarity (10%)
            char_score = _char_similarity(resp_norm, truth_norm)
    
            # 가중 평균
            combined_score = (
                token_score * 0.4 +
                jaccard_score * 0.3 +
                lcs_score * 0.2 +
                char_score * 0.1
            )
    
            return round(combined_score, 3)
    
    
    # ============================================================================
    # 3. tokens_used 추출 (LLM API 응답에서)
    # ============================================================================
    
    def extract_tokens_from_openai(openai_response) -> Dict[str, int]:
        """
        OpenAI API 응답에서 토큰 사용량 추출
    
        Args:
            openai_response: openai.ChatCompletion 객체
    
        Returns:
            dict: {"input": int, "output": int, "total": int}
    
        Example:
            >>> response = openai.chat.completions.create(...)
            >>> tokens = extract_tokens_from_openai(response)
            >>> print(tokens)
            {"input": 150, "output": 85, "total": 235}
        """
        try:
            return {
                "input": openai_response.usage.prompt_tokens,
                "output": openai_response.usage.completion_tokens,
                "total": openai_response.usage.total_tokens
            }
        except AttributeError:
            # usage 필드가 없는 경우
            return {"input": 0, "output": 0, "total": 0}
    
    
    def extract_tokens_from_langchain(llm_result) -> Dict[str, int]:
        """
        LangChain LLMResult에서 토큰 사용량 추출
    
        Args:
            llm_result: LangChain LLMResult 객체
    
        Returns:
            dict: {"input": int, "output": int, "total": int}
        """
        try:
            token_usage = llm_result.llm_output.get("token_usage", {})
            return {
                "input": token_usage.get("prompt_tokens", 0),
                "output": token_usage.get("completion_tokens", 0),
                "total": token_usage.get("total_tokens", 0)
            }
        except (AttributeError, KeyError):
            return {"input": 0, "output": 0, "total": 0}
    
    
    def estimate_tokens(text: str) -> int:
        """
        텍스트 길이로부터 토큰 수 추정 (API 호출 없이)
    
        대략적인 추정: 영어 4자 = 1토큰, 한글 2자 = 1토큰
    
        Args:
            text: 입력 텍스트
    
        Returns:
            int: 추정 토큰 수
        """
        # 한글과 영어 분리
        korean_chars = len(re.findall(r'[가-힣]', text))
        other_chars = len(text) - korean_chars
    
        # 추정: 한글 2자/토큰, 영어 4자/토큰
        estimated = (korean_chars // 2) + (other_chars // 4)
    
        return max(1, estimated)
    
    
    # ============================================================================
    # 4. tool_calls 추출 (Agent 실행에서)
    # ============================================================================
    
    def extract_tool_calls_from_langchain(agent_result) -> List[Dict[str, Any]]:
        """
        LangChain Agent 결과에서 tool_calls 추출
    
        Args:
            agent_result: AgentExecutor 실행 결과
    
        Returns:
            list: [{"name": str, "input": str, "output": str, "success": bool}]
        """
        tool_calls = []
    
        # intermediate_steps에서 tool 사용 정보 추출
        if hasattr(agent_result, 'intermediate_steps'):
            for action, observation in agent_result.intermediate_steps:
                tool_calls.append({
                    "name": action.tool,
                    "input": str(action.tool_input),
                    "output": str(observation),
                    "success": observation is not None
                })
    
        return tool_calls
    
    
    def extract_tool_calls_from_openai_functions(openai_response) -> List[Dict[str, Any]]:
        """
        OpenAI Function Calling에서 tool_calls 추출
    
        Args:
            openai_response: openai.ChatCompletion 객체
    
        Returns:
            list: [{"name": str, "input": str}]
        """
        tool_calls = []
    
        try:
            message = openai_response.choices[0].message
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "name": tc.function.name,
                        "input": tc.function.arguments
                    })
        except (AttributeError, IndexError):
            pass
    
        return tool_calls
    
    
    # ============================================================================
    # 보조 함수들 (내부 사용)
    # ============================================================================
    
    def normalize_text(text: str) -> str:
        """텍스트 정규화: 소문자, 공백 제거, 특수문자 제거"""
        text = text.lower()
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'[^\w\s]', '', text)
        return text
    
    
    def calculate_text_similarity(text1: str, text2: str) -> float:
        """SequenceMatcher를 사용한 기본 유사도"""
        return SequenceMatcher(None,
                              normalize_text(text1),
                              normalize_text(text2)).ratio()
    
    
    def _token_overlap_ratio(text1: str, text2: str) -> float:
        """Token Overlap Ratio 계산"""
        tokens1 = set(text1.split())
        tokens2 = set(text2.split())
    
        if not tokens1 or not tokens2:
            return 0.0
    
        intersection = tokens1 & tokens2
        return len(intersection) / len(tokens2)
    
    
    def _jaccard_similarity(text1: str, text2: str) -> float:
        """Jaccard Similarity 계산"""
        tokens1 = set(text1.split())
        tokens2 = set(text2.split())
    
        if not tokens1 and not tokens2:
            return 1.0
        if not tokens1 or not tokens2:
            return 0.0
    
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
    
        return len(intersection) / len(union)
    
    
    def _lcs_similarity(text1: str, text2: str) -> float:
        """Longest Common Subsequence Similarity"""
        def lcs_length(s1, s2):
            m, n = len(s1), len(s2)
            dp = [[0] * (n + 1) for _ in range(m + 1)]
    
            for i in range(1, m + 1):
                for j in range(1, n + 1):
                    if s1[i-1] == s2[j-1]:
                        dp[i][j] = dp[i-1][j-1] + 1
                    else:
                        dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    
            return dp[m][n]
    
        if not text1 or not text2:
            return 0.0
    
        lcs_len = lcs_length(text1, text2)
        return lcs_len / max(len(text1), len(text2))
    
    
    def _char_similarity(text1: str, text2: str) -> float:
        """Character-level Similarity"""
        return SequenceMatcher(None, text1, text2).ratio()
    
    
    # ============================================================================
    # 통합 TaskResult 생성 함수
    # ============================================================================
    
    def create_taskresult_from_execution(
        task_id: str,
        question: str,
        response: str,
        ground_truth: str,
        execution_time: float,
        openai_response = None,
        langchain_result = None,
        has_error: bool = False,
        error_message: str = None
    ):
        """
        Agent 실행 결과로부터 TaskResult 생성 (모든 필드 동적 계산)
    
        사용 예:
            task = create_taskresult_from_execution(
                task_id="task_001",
                question="한국의 수도는?",
                response="서울입니다",
                ground_truth="서울",
                execution_time=1.23,
                openai_response=openai_response
            )
        """
        from agent_evaluator import TaskResult, TaskType
        from datetime import datetime
    
        # 1. completion_score 동적 계산
        completion = calculate_completion_score(
            response=response,
            expected_min_length=10,
            has_error=has_error,
            ground_truth=ground_truth
        )
    
        # 2. accuracy_score 동적 계산 
        accuracy = calculate_accuracy_score(
            response=response,
            ground_truth=ground_truth,
            method="combined"
        )
    
        # 3. tokens_used 동적 추출
        if openai_response:
            tokens = extract_tokens_from_openai(openai_response)
        elif langchain_result:
            tokens = extract_tokens_from_langchain(langchain_result)
        else:
            # API 응답이 없으면 추정
            tokens = {
                "input": estimate_tokens(question),
                "output": estimate_tokens(response),
                "total": estimate_tokens(question) + estimate_tokens(response)
            }
    
        # 4. tool_calls 동적 추출
        tool_calls = []
        if openai_response:
            tool_calls = extract_tool_calls_from_openai_functions(openai_response)
        elif langchain_result:
            tool_calls = extract_tool_calls_from_langchain(langchain_result)
    
        # 5. TaskResult 생성
        return TaskResult(
            task_id=task_id,
            task_type=TaskType.QA.value,
            success=not has_error,
            completion_score=completion,      # ✅ 동적 계산
            accuracy_score=accuracy,          # ✅ 동적 계산
            execution_time=execution_time,    # ✅ 실제 측정
            tokens_used=tokens,               # ✅ 동적 추출
            tool_calls=tool_calls,            # ✅ 동적 추출
            attempts=1,
            errors=[error_message] if error_message else [],
            timestamp=datetime.now()
        )
```

### 5.3 Scenario 1: 기본 수동 평가 (헬퍼 함수 사용)

#### ✅ 동적 값 계산 예제

헬퍼 함수를 사용하여 모든 필드를 동적으로 계산합니다. **하드코딩된 값이 없습니다!**

✅ 실행 가능 📋 복사
```python
    from agent_evaluator import PerformanceMonitor, TaskType, create_taskresult
    import time

    monitor = PerformanceMonitor()

    # 1. Agent 실행
    question = "한국의 수도는 어디인가요?"
    ground_truth = "서울"

    start_time = time.time()
    response = "서울입니다"  # your_agent.run(question)
    execution_time = time.time() - start_time

    # 2. TaskResult 생성 (모든 필드 동적 계산!)
    task = create_taskresult(
        task_id="task_001",
        question=question,
        response=response,
        ground_truth=ground_truth,
        execution_time=execution_time
    )
    
    # 3. 자동 계산된 값 확인
    print(f"✅ Completion Score: {task.completion_score:.2f}")  # 0.0~1.0 동적 계산
    print(f"✅ Accuracy Score: {task.accuracy_score:.2f}")      # 4가지 메트릭 조합
    print(f"✅ Tokens Used: {task.tokens_used}")                # 길이로부터 추정
    
    # 4. 기록
    monitor.record_task(task)
    
    # 5. 결과 확인
    report = monitor.generate_report()
    print(f"\nTCR: {report['accuracy_metrics']['tcr']:.1f}%")
    print(f"Accuracy: {report['accuracy_metrics']['accuracy']:.1f}%")
```

### 5.4 Scenario 2: OpenAI API 실전 예제

#### ✅ OpenAI API 응답으로부터 TaskResult 자동 생성

OpenAI API 응답에서 토큰 사용량을 자동으로 추출하고, 헬퍼 함수로 모든 메트릭을 동적 계산합니다.

✅ 실행 가능 📋 복사
```python
    from agent_evaluator import PerformanceMonitor, create_taskresult
    from openai import OpenAI
    import time

    monitor = PerformanceMonitor()
    client = OpenAI()

    # 1. 평가할 질문과 정답
    question = "한국의 수도는 어디인가요?"
    ground_truth = "서울"

    # 2. OpenAI API 호출
    start = time.time()
    openai_response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": question}]
    )
    exec_time = time.time() - start

    # 3. 응답 추출
    response = openai_response.choices[0].message.content
    usage = openai_response.usage
    tokens = {"input": usage.prompt_tokens, "output": usage.completion_tokens,
              "total": usage.total_tokens}

    # 4. TaskResult 자동 생성
    task = create_taskresult(
        task_id="task_openai_001",
        question=question,
        response=response,
        ground_truth=ground_truth,
        execution_time=exec_time,
        tokens_used=tokens
    )

    # 5. 자동 계산 결과 확인
    print(f"✅ Completion Score: {task.completion_score:.2f}")
    print(f"✅ Accuracy Score: {task.accuracy_score:.2f}")
    print(f"✅ Tokens: {task.tokens_used}")

    monitor.record_task(task)

    # 6. 여러 질문 배치 평가 예제
    golden_dataset = [
        {"qa_id": "qa_001", "question": "Agent Evaluator의 주요 기능은?",
         "answer": "3-Layer 메트릭 시스템을 제공합니다"},
        {"qa_id": "qa_002", "question": "TCR은 무엇인가요?",
         "answer": "Task Completion Rate로 작업 완료율을 의미합니다"}
    ]

    for qa in golden_dataset:
        start = time.time()
        openai_response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": qa['question']}]
        )
        exec_time = time.time() - start

        response = openai_response.choices[0].message.content
        usage = openai_response.usage
        tokens = {"input": usage.prompt_tokens, "output": usage.completion_tokens,
                  "total": usage.total_tokens}

        # create_taskresult() 헬퍼로 TaskResult 생성
        task = create_taskresult(
            task_id=qa['qa_id'],
            question=qa['question'],
            response=response,
            ground_truth=qa['answer'],
            execution_time=exec_time,
            tokens_used=tokens
        )
    
        monitor.record_task(task)
        print(f"✅ {qa['qa_id']}: Accuracy={task.accuracy_score:.2f}, Tokens={task.tokens_used['total']}")
    
    # 전체 평가 결과
    report = monitor.generate_report()
    print(f"\n📊 전체 TCR: {report['accuracy_metrics']['tcr']:.1f}%")
    print(f"📊 전체 Accuracy: {report['accuracy_metrics']['accuracy']:.1f}%")
```

### 5.5 Scenario 3: LangChain Agent 실전 예제

#### ✅ LangChain Agent 결과로부터 TaskResult 자동 생성

LangChain Agent 실행 결과에서 tool_calls를 자동으로 추출하고, Layer 2 메트릭을 평가합니다.

✅ 실행 가능 📋 복사
```python
    from agent_evaluator import PerformanceMonitor, create_taskresult
    from langchain.agents import AgentExecutor
    import time

    monitor = PerformanceMonitor()

    # Golden Dataset with expected tools (Layer 2 평가용)
    qa_with_tools = {
        "qa_id": "qa_003",
        "question": "2024년 AI 트렌드를 조사하고 요약해주세요",
        "answer": "2024년 주요 AI 트렌드는 생성형 AI, 멀티모달 모델, 에이전트 시스템입니다",
        "expected_tools": ["web_search", "summarizer"]  # Layer 2
    }

    # 1. LangChain Agent 실행 (create_evaluated_langchain_agent 사용 권장)
    start = time.time()
    agent_result = your_langchain_agent.invoke(
        {"input": qa_with_tools['question']},
        config={"callbacks": []}  # 평가 콜백 여기에 추가
    )
    exec_time = time.time() - start

    # 2. 응답 추출
    response = agent_result.get("output", "")

    # 3. TaskResult 생성
    task = create_taskresult(
        task_id=qa_with_tools['qa_id'],
        question=qa_with_tools['question'],
        response=response,
        ground_truth=qa_with_tools['answer'],
        execution_time=exec_time
    )
    
    # 4. Layer 2 필드 수동 추가 (Multi-Agent 시스템용)
    task.agents_involved = ["researcher", "writer"]
    task.workflow_steps = ["research", "summarize", "write"]
    
    monitor.record_task(task)
    
    # 5. 자동 계산 결과 확인
    print(f"✅ Completion Score: {task.completion_score:.2f}")
    print(f"✅ Accuracy Score: {task.accuracy_score:.2f}")
    print(f"✅ Tool Calls: {[t['name'] for t in task.tool_calls]}")  # LangChain에서 추출
    print(f"✅ Tokens: {task.tokens_used}")
    
    # 6. Layer 2 평가 수행 (Tool Selection)
    monitor.tool_selection_tracker.evaluate_selection(
        task_id=task.task_id,
        expected_tools=qa_with_tools['expected_tools'],
        actual_tools=[t['name'] for t in task.tool_calls]
    )
    
    # 7. Layer 2 메트릭 확인
    tool_metrics = monitor.tool_selection_tracker.calculate_metrics()
    print(f"\n📊 Tool Selection F1 Score: {tool_metrics['f1_score']:.2f}")
    print(f"📊 Tool Selection Accuracy: {tool_metrics['accuracy']:.2f}")
```

#### 💡 LangChain 사용 시 팁

**tool_calls 자동 추출:** `extract_tool_calls_from_langchain()`은 `intermediate_steps`에서 도구 사용 정보를 자동으로 추출합니다.
```python
    # 수동 추출 방법 (헬퍼 함수 미사용 시)
    tool_calls = []
    if hasattr(agent_result, 'intermediate_steps'):
        for action, observation in agent_result.intermediate_steps:
            tool_calls.append({
                "name": action.tool,
                "input": str(action.tool_input),
                "output": str(observation),
                "success": observation is not None
            })
```

### 5.6 데이터 준비 체크리스트

#### TaskResult 생성 전 필수 체크

  * □ **task_id:** 고유한 ID 생성 (중복 방지)
  * □ **task_type:** TaskType enum 사용 (QA, CODE_GENERATION 등)
  * □ **success:** 실제 성공 여부 판단 (에러 발생 시 False)
  * □ **completion_score:** 0.0~1.0 범위, 작업 완료 정도
  * □ **accuracy_score:** 0.0~1.0 범위, 정확도 (Golden Dataset 기반)
  * □ **execution_time:** 실제 측정한 시간 (초 단위)
  * □ **tokens_used:** Dict 형식, input/output/total 포함
  * □ **tool_calls:** List[Dict], 각 Dict는 name, input 포함
  * □ **attempts:** 1부터 시작 (재시도 시 증가)
  * □ **errors:** 빈 리스트 [] 또는 에러 메시지 리스트
  * □ **timestamp:** datetime.now() 사용

### 5.7 실전 팁

#### Tip 1: completion_score vs accuracy_score

**completion_score:** 작업을 얼마나 완료했는가? (형식적 완성도)

  * 1.0: 완전한 답변 생성, 에러 없음
  * 0.5: 부분 답변, 일부 누락
  * 0.0: 답변 생성 실패

**accuracy_score:** 답변이 얼마나 정확한가? (내용적 정확성)

  * 1.0: 기대 답변과 완전히 일치
  * 0.8: 주요 내용 포함, 일부 차이
  * 0.5: 부분적으로 정확
  * 0.0: 완전히 틀림

#### Tip 2: accuracy_score 자동 계산 ✅

**헬퍼 함수를 사용하면 모든 메트릭이 자동으로 계산됩니다!**

✅ 실행 가능 📋 복사
```python
    # 방법 1: 헬퍼 함수 사용 (가장 권장) ⭐
    from agent_evaluator.helpers import (
        calculate_accuracy_score,
        calculate_completion_score
    )
    
    response = "한국의 수도는 서울입니다"
    ground_truth = "서울"
    
    #  4가지 메트릭 조합 (Token Overlap, Jaccard, LCS, Character)
    accuracy = calculate_accuracy_score(response, ground_truth, method="combined")
    print(f"Accuracy: {accuracy:.3f}")  # 0.850
    
    # 완료도 계산
    completion = calculate_completion_score(response, ground_truth=ground_truth)
    print(f"Completion: {completion:.2f}")  # 1.0
    
    # 방법 2: evaluate_with_golden_dataset() 사용
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    monitor.load_golden_dataset("data/golden_dataset.json")
    
    # 자동으로 accuracy_score 계산됨
    results = monitor.evaluate_with_golden_dataset(
        agent_function=your_agent.run,
        calculate_accuracy=True
    )
    
    # 방법 3: 간단한 유사도 계산 (헬퍼 함수의 "simple" 모드)
    accuracy_simple = calculate_accuracy_score(response, ground_truth, method="simple")
    print(f"Accuracy (simple): {accuracy_simple:.2f}")  # 1.0 (포함됨)
```

#### Tip 3: tool_calls 올바른 형식

tool_calls는 반드시 List[Dict] 형식이어야 하며, 각 Dict는 최소한 'name' 키를 포함해야 합니다:
```json
    # ✅ 올바른 형식
    tool_calls = [
        {"name": "web_search", "input": "AI trends"},
        {"name": "calculator", "input": "2+2"}
    ]
    
    # ❌ 잘못된 형식
    tool_calls = ["web_search", "calculator"]  # Dict가 아닌 문자열 리스트
    
    # ✅ 도구를 사용하지 않았다면
    tool_calls = []  # 빈 리스트
```

#### 흔한 문제와 해결

ValueError: completion_score must be between 0.0 and 1.0

**원인:** completion_score가 0.0~1.0 범위를 벗어남

**해결:** 값을 0.0~1.0으로 정규화
```python
    completion_score = max(0.0, min(1.0, raw_score))
```

TypeError: tokens_used must be a dictionary

**원인:** tokens_used가 Dict가 아님

**해결:** 최소한 input, output 키 포함
```python
    tokens_used = {"input": 100, "output": 50}
    # 또는
    tokens_used = {"input": 100, "output": 50, "total": 150}
```

AssertionError: tool_calls must be a list of dicts

**원인:** tool_calls가 올바른 형식이 아님

**해결:** List[Dict] 형식으로 변환, 각 Dict는 'name' 키 필수
```python
    # 문자열 리스트를 Dict 리스트로 변환
    tool_names = ["search", "calculator"]
    tool_calls = [{"name": name} for name in tool_names]
```

## 📚 6. Golden Dataset 가이드

### 6.1 Golden Dataset이란?

**Golden Dataset** 은 Agent 평가를 위한 **Ground Truth 데이터셋** 입니다. 질문(Question), 기대 답변(Answer), 컨텍스트(Context) 등을 포함하며, 자동 평가의 기준이 됩니다.

### 6.2 QAPair 구조
```json
    {
      "qa_id": "qa_001",
      "question": "Agent Evaluator의 주요 기능은?",
      "answer": "3-Layer 메트릭 시스템을 제공하며...",
      "context": "Agent Evaluator는 AI Agent 평가 프레임워크...",
      "ground_truth": "정확한 기대 답변",
    
      // Layer 2 Agentic AI 필드
      "expected_tools": ["search", "calculator"],
      "expected_agents": ["manager", "researcher", "writer"],
      "expected_workflow_steps": ["retrieval", "generation", "validation"],
    
      // 메타데이터
      "metadata": {
        "chunk_id": "chunk_1",
        "page_number": 1,
        "difficulty": "medium"
      }
    }
```

### 6.3 Golden Dataset 생성 방법

#### 방법 1: Dashboard에서 수동 작성

  1. Dashboard → "데이터 편집" 탭 이동
  2. "Golden Dataset" 섹션 선택
  3. 행 추가 버튼으로 QA Pair 입력
  4. 저장 버튼 클릭

#### 방법 2: PDF에서 자동 생성
```python
    from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator
    
    generator = KoreanRAGDatasetGenerator()
    
    # PDF에서 자동 생성
    dataset = generator.generate_dataset_from_pdf(
        pdf_path="document.pdf",
        output_path="golden_datasets/my_dataset.json",
        chunk_size=500,
        num_qa_pairs_per_chunk=2
    )
```

#### 방법 3: Python 코드로 작성
```python
    from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDataset, QAPair
    
    qa_pairs = [
        QAPair(
            qa_id="qa_001",
            question="질문",
            answer="답변",
            context="컨텍스트",
            ground_truth="정답",
            expected_tools=["search"],
            metadata={}
        )
    ]
    
    dataset = GoldenDataset(
        dataset_id="my_dataset",
        qa_pairs=qa_pairs,
        source_document="document.pdf"
    )
    
    dataset.save("golden_datasets/my_dataset.json")
```

### 6.4 Golden Dataset 기반 자동 평가

#### 수동 평가 (현재 지원)
```python
    monitor = PerformanceMonitor.from_test_config("test_config_...")
    
    # Golden Dataset 로드
    monitor.load_golden_dataset()
    
    # 각 QA에 대해 평가
    for qa in monitor.golden_datasets:
        # Agent 실행
        response = agent.run(qa['question'])
    
        # TaskResult 생성
        task = TaskResult(
            task_id=qa['qa_id'],
            expected_output=qa['answer'],
            actual_output=response,
            # ... 기타 필드
        )
    
        monitor.record_task(task)
    
        # Layer 2 메트릭 평가 (선택적)
        if 'expected_tools' in qa and qa['expected_tools']:
            monitor.tool_selection_tracker.evaluate_selection(
                task.task_id,
                qa['expected_tools'],
                task.tool_calls
            )
```

**💡 Best Practice:** Golden Dataset은 도메인별로 최소 20-50개의 QA Pair를 포함하는 것을 권장합니다. 다양한 난이도와 시나리오를 포함하여 포괄적인 평가가 가능합니다. 

## 🎯 7. Threshold 설정 가이드

### 7.1 Threshold란?

**Threshold (임계값)** 은 각 메트릭의 **허용 기준** 입니다. 평가 결과가 이 기준을 충족하면 **Pass** , 미달하면 **Fail** 로 판정됩니다. CI/CD 품질 게이트의 핵심 요소입니다.

### 7.2 환경별 권장 Threshold

메트릭 | Development | Staging | Production  
---|---|---|---  
**TCR** | ≥ 70% | ≥ 85% | ≥ 95%  
**Accuracy** | ≥ 65% | ≥ 80% | ≥ 90%  
**Quality** | ≥ 6.0 | ≥ 7.5 | ≥ 8.5  
**Hallucination** | ≤ 10% | ≤ 5% | ≤ 1%  
**Latency (P95)** | ≤ 5s | ≤ 4s | ≤ 3s  
**Tool Selection** | ≥ 60% | ≥ 75% | ≥ 85%  
**Agent Coordination** | ≥ 6.0 | ≥ 7.0 | ≥ 8.5  
**Workflow Execution** | ≥ 70% | ≥ 85% | ≥ 95%  
  
### 7.3 Threshold 설정 방법

#### 방법 1: Dashboard에서 설정

  1. Dashboard → "데이터 편집" 탭
  2. "Threshold Settings" 섹션
  3. 각 메트릭 슬라이더 조정
  4. 저장 버튼 클릭

#### 방법 2: Python 코드로 설정
```python
    monitor = PerformanceMonitor()
    
    # 환경별 Threshold
    if environment == "production":
        monitor.thresholds = {
            'tcr': 95.0,
            'accuracy': 90.0,
            'hallucination': 1.0,
            'latency': 3.0,
            'tool_selection_accuracy': 85.0,
            'agent_coordination': 8.5,
            'workflow_execution': 95.0
        }
    elif environment == "staging":
        monitor.thresholds = {
            'tcr': 85.0,
            'accuracy': 80.0,
            # ...
        }
    
```

### 7.4 Threshold 검증
```python
    # 평가 수행
    for task in tasks:
        monitor.record_task(task)
    
    # Threshold 비교
    comparison = monitor.compare_with_thresholds()
    
    # Pass/Fail 판정
    all_passed = all(
        result['status'] == 'pass'
        for result in comparison.values()
    )
    
    if all_passed:
        print("✅ 모든 메트릭 통과!")
        sys.exit(0)  # CI/CD 성공
    else:
        print("❌ 일부 메트릭 실패:")
        for metric, result in comparison.items():
            if result['status'] == 'fail':
                print(f"  - {metric}: {result['message']}")
        sys.exit(1)  # CI/CD 실패
```

### 7.5 도메인별 Threshold 튜닝

도메인 | 중점 메트릭 | 권장 조정  
---|---|---  
**고객 서비스 챗봇** | Hallucination, Quality | Hallucination ≤ 0.5%, Quality ≥ 9.0  
**의료 상담 AI** | Accuracy, Hallucination | Accuracy ≥ 95%, Hallucination ≤ 0.1%  
**법률 자문 AI** | Accuracy, Quality | Accuracy ≥ 98%, Quality ≥ 9.5  
**실시간 추천 시스템** | Latency, Tool Efficiency | Latency ≤ 1s, Tool Efficiency ≥ 95%  
**Multi-Agent 협업** | Agent Coordination, Workflow | Coordination ≥ 9.0, Workflow ≥ 98%  
  
**⚠️ 주의사항:** Threshold를 너무 엄격하게 설정하면 개발 속도가 저하될 수 있습니다. 환경별로 점진적으로 강화하는 전략을 권장합니다. 

## 🔌 8. 프레임워크 통합

### 🎉 고급 통합 클래스 + 보안 메트릭

**통합 클래스가 Layer 1/2/3 메트릭 + 보안 메트릭을 자동으로 추적합니다:**

#### ✨ CrewAIEvaluator

`from agent_evaluator.integrations import CrewAIEvaluator`

Agent Coordination, Workflow + Security 자동 추적

#### ✨ LangChainEvaluator

`from agent_evaluator.integrations import LangChainEvaluator`

Tool Selection, Workflow + Security 자동 추적

#### ✨ LangGraphEvaluator

`from agent_evaluator.integrations import LangGraphEvaluator`

노드별 Workflow Execution + Security 추적

#### ✨ AutoGenEvaluator

`from agent_evaluator.integrations import AutoGenEvaluator`

Agent 상호작용 + Security 자동 추적

**⚠️ 참고:** 기존 클래스 (`EvaluatedCrew`, `LangChainEvaluationCallback` 등)는 v4.0에서 제거 예정입니다. 새로운 클래스로 마이그레이션하세요.

자세한 내용: [API Reference](<API_REFERENCE.html#프레임워크-통합>) | [프레임워크 통합 가이드](<FRAMEWORK_INTEGRATION.html>)

### 8.1 지원 프레임워크

#### 🦜 LangChain

**지원 기능:**

  * Chain 실행 추적
  * Tool Selection 자동 평가
  * Workflow Step 추적

#### 🚢 CrewAI

**지원 기능:**

  * Agent Coordination 자동 추적
  * Task 실행 평가
  * Multi-Agent 협업 분석

#### 🕸️ LangGraph

**지원 기능:**

  * 노드별 실행 추적
  * Workflow Execution 자동 평가
  * 그래프 탐색 효율성 측정

#### 🤖 AutoGen

**지원 기능:**

  * Agent 대화 추적
  * 그룹 채팅 분석
  * 자율 협업 평가

### 8.2 LangChain 통합 예제

**권장:** `LangChainEvaluator` 클래스 사용 (보안 메트릭 자동 추적)

#### ✨ LangChainEvaluator 사용
```python
    from agent_evaluator.integrations import LangChainEvaluator
    from langchain.agents import initialize_agent
    
    # LangChain 에이전트 생성
    agent = initialize_agent(tools, llm)
    
    # 평가 래퍼 생성 (Layer 1/2 자동 추적)
    evaluator = LangChainEvaluator(
        agent,
        enable_layer2=True,
        verbose=True
    )
    
    # 실행 및 자동 평가
    result = evaluator.run(
        "What is 25 * 4?",
        ground_truth="100",
        expected_tools=["calculator"]
    )
    
    # 보고서 생성
    report = evaluator.generate_report()
    # ✅ Layer 1: TCR, Accuracy, Latency (Foundation)
    # ✅ Layer 2: Tool Selection, Workflow + Security (Input Sanitization, Output Leakage, Authorization, Privilege Escalation, Attack Detection)
```

#### ⚠️ 기존 방식 (v4.0에서 제거 예정)
```python
    from framework_integrations import LangChainEvaluationCallback
    from agent_evaluator import PerformanceMonitor
    
    # 기존 콜백 방식 (deprecated)
    callback = LangChainEvaluationCallback(monitor, ...)
    result = agent_executor.run("query", callbacks=[callback])
```

### 8.3 CrewAI 통합 예제

**권장:** `CrewAIEvaluator` 클래스 사용 (보안 메트릭 자동 추적)

#### ✨ CrewAIEvaluator 사용
```python
    from agent_evaluator.integrations import CrewAIEvaluator
    from crewai import Crew, Agent, Task
    
    # Crew 정의
    researcher = Agent(role="Researcher", ...)
    writer = Agent(role="Writer", ...)
    task1 = Task(description="Research topic", agent=researcher)
    task2 = Task(description="Write article", agent=writer)
    crew = Crew(agents=[researcher, writer], tasks=[task1, task2])
    
    # 평가 래퍼 생성 (Layer 1/2 자동 추적)
    evaluator = CrewAIEvaluator(
        crew,
        enable_layer2=True,  # Agent Coordination 자동 추적
        verbose=True
    )
    
    # 실행 및 자동 평가
    result = evaluator.kickoff(
        inputs={"topic": "AI Agents"},
        ground_truth="Expected output...",
        expected_workflow_steps=["research", "write"]
    )
    
    # 보고서 생성
    report = evaluator.generate_report()
    # ✅ Layer 1: TCR, Accuracy, Latency (Foundation)
    # ✅ Layer 2: Agent Coordination, Workflow + Security (Input Sanitization, Output Leakage, Authorization, Privilege Escalation, Attack Detection)
```

#### ⚠️ 기존 방식 (v4.0에서 제거 예정)
```python
    from framework_integrations import EvaluatedCrew
    
    # 기존 방식 (deprecated)
    evaluated_crew = EvaluatedCrew(crew, monitor, ...)
    result = evaluated_crew.kickoff(...)
```

### 8.4 LangGraph 통합 예제

**권장:** `LangGraphEvaluator` 클래스 사용 (보안 메트릭 자동 추적)

#### ✨ LangGraphEvaluator 사용
```python
    from agent_evaluator.integrations import LangGraphEvaluator
    
    # 평가 래퍼 생성
    evaluator = LangGraphEvaluator(enable_layer2=True)
    
    # 노드 추가 (자동으로 평가가 래핑됨)
    evaluator.add_node("retrieval", retrieval_function)
    evaluator.add_node("generation", generation_function)
    evaluator.add_node("validation", validation_function)
    
    # Edge 연결
    evaluator.add_edge("start", "retrieval")
    evaluator.add_edge("retrieval", "generation")
    evaluator.add_edge("generation", "validation")
    evaluator.add_edge("validation", "end")
    
    # 실행 및 자동 평가
    result = evaluator.run(
        initial_state={"messages": []},
        ground_truth="Expected...",
        expected_workflow_steps=["retrieval", "generation", "validation"]
    )
    
    # 보고서 생성
    report = evaluator.generate_report()
    # ✅ 각 노드의 실행 시간, 성공률 자동 추적
    # ✅ Workflow Execution Score + Security Metrics 자동 계산
```

#### ⚠️ 기존 방식 (v4.0에서 제거 예정)
```python
    from framework_integrations import LangGraphEvaluatedWorkflow
    
    # 기존 방식 (deprecated)
    workflow = LangGraphEvaluatedWorkflow(monitor, ...)
    result = workflow.compile_and_run(...)
```

### 8.5 AutoGen 통합 예제

#### ✨ 새로운 AutoGenEvaluator (보안 메트릭 자동 추적)
```python
    from agent_evaluator.integrations import AutoGenEvaluator
    from autogen import AssistantAgent, UserProxyAgent
    
    # AutoGen 에이전트 생성
    assistant = AssistantAgent(name="assistant", llm_config={...})
    
    # 평가 래퍼 생성
    evaluator = AutoGenEvaluator(
        assistant,
        enable_layer2=True  # Agent 상호작용 자동 추적
    )
    
    # evaluator.agent를 일반 에이전트처럼 사용
    user_proxy = UserProxyAgent(...)
    user_proxy.initiate_chat(evaluator.agent, message="Hello")
    
    # 보고서 생성
    report = evaluator.generate_report()
    # ✅ Agent Coordination + Security Metrics 자동 추적
    # ✅ 메시지 교환 분석 + 보안 위협 탐지
```

**✅ v0.6.0 통합의 장점:**

  * **완전 자동화:** Layer 1/2/3 메트릭 자동 추적
  * **동적 계산:** TCR, Accuracy 등 실시간 계산
  * **통합 보고서:** generate_report() 한 번으로 모든 메트릭 출력
  * **Zero Configuration:** 최소한의 설정으로 즉시 사용 가능

**마이그레이션 가이드:** [API Reference - Legacy Integrations](<API_REFERENCE.html#legacy-integrations>)

## 🖥️ 9. Dashboard 사용법

**💡 FastAPI Dashboard:** Agent Evaluator는 단일 통합 Dashboard를 제공합니다.
\- **FastAPI Dashboard (Port 8765):** 분석, 시각화, Test 투명성, 리포트 생성, Golden Dataset/Threshold 관리
\- 실행 방법: `agent-eval dashboard`

### 9.1 FastAPI Dashboard (Port 8765)

#### 📊 개요 (Overview)

전체 메트릭 요약, KPI 대시보드, 메트릭 비교

#### 🎯 핵심 메트릭 (Core Metrics)

**4개 서브탭:** Task Completion (TCR + Retry), Accuracy, Quality, Hallucination

#### ⚡ 성능 지표 (Performance)

**2개 서브탭:** Latency, Cost & Tokens

#### 🤖 Agentic AI 메트릭

**3개 서브탭:** Tool Selection Accuracy, Agent Coordination, Workflow Execution

#### 🔬 고급 평가 (Advanced)

**2개 서브탭:** DeepEval 메트릭, Ragas RAG 평가 (Layer 3)

#### 💡 인사이트 (Insights)

**3개 서브탭:** Alerts (임계값 기반 경고), Recommendations (개선 제안), Task Explorer (개별 Task 분석)

#### 🔍 Test 투명성

**4개 서브탭:** 메트릭 계산 과정 (Traces), 주석 관리 (Annotations), Audit Log, 상세 리포트

_참고: Python API의 5개 고급 분석 기능(이상치 탐지, 상관관계 등)은 10. 고급 기능 섹션 참고_

#### 📚 지표 설명 (Metrics Guide)

모든 25개 메트릭(Layer 1: 6개, Layer 2: 10개, Layer 3: 9개)의 용도, 산출식, 기준값을 펼침목록 형태로 제공

각 메트릭별 상세 설명, 계산 방법, 권장 임계값, 해석 가이드 포함

#### 📦 내보내기 & 평가 정보 (Export)

**2개 서브탭:** Reports (HTML 리포트), 평가 환경 & 설정 (시스템 정보, 임계값, 요금제)

### 9.2 데이터 관리 (FastAPI Dashboard 통합)

FastAPI Dashboard (Port 8765)는 데이터 편집 기능을 통합 제공합니다.

  * ⚙️ **임계값 설정:** 5개 메트릭 Threshold 편집 (TCR·Accuracy·Hallucination·P95·Cost), 환경별 프리셋
  * 📄 **Golden Dataset:** QA Pair 추가/수정/삭제, Layer 2 필드 편집
  * 📋 **Test 준비:** Test Configuration 생성, 환경 설정
  * 📊 **이력 관리:** 버전 백업, 복원, 변경 이력 추적

### 9.3 실시간 모니터링

메인 Dashboard는 `evaluation_results/performance_data.json` 파일을 로드하여 실시간으로 메트릭을 시각화합니다.

  1. Python 코드에서 평가 수행 및 저장
  2. Dashboard 새로고침 (F5)
  3. 최신 평가 결과 즉시 반영

### 9.4 주요 기능 상세

#### Golden Dataset 편집 (데이터 편집 Dashboard)

  * 기존 Dataset 로드 및 수정
  * 새로운 QA Pair 추가
  * Layer 2 필드 (expected_tools, expected_agents, expected_workflow_steps) 편집
  * 버전 백업 자동 생성 (evaluation_results/versions/)
  * JSON 형식으로 저장

#### Threshold 설정 (데이터 편집 Dashboard)

  * 5개 메트릭 임계값 슬라이더 조정 (TCR · Accuracy · Hallucination · P95 · Cost)
  * 환경별 프리셋 (Development, Staging, Production)
  * 변경 이력 자동 추적 (Audit Log)
  * JSON 파일로 저장 (thresholds.json)
  * Test Configuration에 자동 포함

#### Test Configuration 생성 (데이터 편집 Dashboard)

  1. "데이터 편집" 탭 → "📋 Test 준비" 서브탭
  2. Test 이름, 환경(Dev/Staging/Prod), Golden Dataset 선택
  3. Framework, Model Config 설정
  4. 생성 버튼 클릭

생성된 Config는 `evaluation_results/test_configs/test_config_YYYYMMDD_HHMMSS.json`에 저장되며, Golden Dataset 경로와 Threshold가 자동으로 포함됩니다.

**💡 Tip:** Dashboard는 Chrome, Edge, Firefox에서 최적화되어 있습니다. 대용량 데이터 시각화를 위해 최소 8GB RAM 권장. 

## ⚙️ 10. 완전한 평가 워크플로우

### 10.1 Phase 1: 데이터 준비

1

**Agent 함수 정의**

평가할 Agent 함수를 명확하게 정의합니다. 입력과 출력이 일관되어야 합니다.

2

**실행 시간 측정 로직 구현**

time.time()을 사용하여 Agent 실행 전후의 시간을 측정합니다.

3

**토큰 사용량 추적 설정**

LLM API 응답에서 tokens_used 정보를 추출하는 로직을 구현합니다.

4

**TaskResult 생성 템플릿 작성**

11개 필수 필드를 모두 포함하는 TaskResult 생성 코드를 작성합니다 (섹션 5 참고).

5

**Golden Dataset 작성**

Dashboard 또는 Python 코드로 Golden Dataset 생성. 도메인별 20-50개 QA Pair 권장.

6

**Threshold 설정**

환경(Dev/Staging/Prod)에 맞는 임계값 설정. 도메인 특성 고려.

7

**Test Configuration 생성**

Golden Dataset + Threshold를 포함하는 Test Config 생성 및 저장.

#### TaskResult 준비 단계별 완전 예제

실행 가능 복사
```python
    from agent_evaluator import PerformanceMonitor, TaskResult, TaskType
    from datetime import datetime
    import time
    
    # Step 1: Agent 함수 정의
    def my_agent(question: str) -> dict:
        """
        Agent 함수: 질문을 받아 답변과 메타데이터를 반환
        반환값: {"answer": str, "tokens": dict, "tools_used": list}
        """
        # 실제 LLM 호출 로직
        response = "서울입니다"
        tokens = {"input": 100, "output": 50}
        tools = []
        return {"answer": response, "tokens": tokens, "tools_used": tools}
    
    # Step 2: 실행 시간 측정 래퍼
    def run_agent_with_timing(agent_func, question: str) -> tuple:
        """Agent를 실행하고 시간을 측정"""
        start_time = time.time()
        result = agent_func(question)
        execution_time = time.time() - start_time
        return result, execution_time
    
    # Step 3: TaskResult 생성 헬퍼 함수
    def create_task_result(
        task_id: str,
        question: str,
        agent_result: dict,
        execution_time: float,
        expected_answer: str = None
    ) -> TaskResult:
        """Agent 결과를 TaskResult로 변환"""
    
        # 정확도 계산 (선택적)
        accuracy = 1.0
        if expected_answer:
            accuracy = 1.0 if expected_answer in agent_result['answer'] else 0.5
    
        # 완료도 판단
        completion = 1.0 if len(agent_result['answer']) > 10 else 0.5
    
        # tool_calls 형식 변환
        tool_calls = [{"name": tool} for tool in agent_result.get('tools_used', [])]
    
        return TaskResult(
            task_id=task_id,
            task_type=TaskType.QA.value,
            success=True,
            completion_score=completion,
            accuracy_score=accuracy,
            execution_time=execution_time,
            tokens_used=agent_result['tokens'],
            tool_calls=tool_calls,
            attempts=1,
            errors=[],
            timestamp=datetime.now()
        )
    
    # Step 4: 완전한 평가 워크플로우
    monitor = PerformanceMonitor()
    
    # Golden Dataset (단순 예시)
    questions = [
        {"qa_id": "qa_001", "question": "한국의 수도는?", "answer": "서울"},
        {"qa_id": "qa_002", "question": "프랑스의 수도는?", "answer": "파리"}
    ]
    
    # 평가 실행
    for qa in questions:
        # Agent 실행 및 시간 측정
        result, exec_time = run_agent_with_timing(my_agent, qa['question'])
    
        # TaskResult 생성
        task = create_task_result(
            task_id=qa['qa_id'],
            question=qa['question'],
            agent_result=result,
            execution_time=exec_time,
            expected_answer=qa['answer']
        )
    
        # 기록
        monitor.record_task(task)
        print(f"✅ {qa['qa_id']}: 완료")
    
    # Step 5: 결과 확인
    report = monitor.generate_report()
    print(f"\n📊 TCR: {report['accuracy_metrics']['tcr']:.1f}%")
    print(f"📊 Accuracy: {report['accuracy_metrics']['accuracy']:.1f}%")
```

#### Phase 1 체크리스트

  * □ Agent 함수 정의 및 테스트 완료
  * □ 시간 측정 로직 구현 완료
  * □ 토큰 추적 설정 완료
  * □ TaskResult 생성 헬퍼 함수 작성 완료
  * □ Golden Dataset 작성 완료 (20개 이상 권장)
  * □ Threshold 설정 완료
  * □ Test Configuration 생성 완료

### 10.2 Phase 2: 평가 실행
```python
    # Test Configuration에서 Monitor 생성
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor.from_test_config(
        "test_config_20251130_120000"
    )
    
    # ✅ 자동 설정됨:
    # - monitor.thresholds = {...}
    # - monitor.golden_dataset_path = "..."
    
    # Golden Dataset 로드
    monitor.load_golden_dataset()
    
    # 평가 수행
    for qa in monitor.golden_datasets:
        # Agent 실행
        start = time.time()
        response = agent.run(qa['question'])
        execution_time = time.time() - start
    
        # TaskResult 생성 및 기록 (헬퍼 함수 사용 권장)
        # from agent_evaluator import create_taskresult
        #
        # task = create_taskresult(
        #     task_id=qa['qa_id'],
        #     question=qa['question'],
        #     response=response,
        #     ground_truth=qa['answer'],
        #     execution_time=execution_time
        # )
    
        # 또는 수동으로 생성:
        from agent_evaluator.helpers import (
            calculate_completion_score,
            calculate_accuracy_score,
            estimate_tokens
        )
    
        task = TaskResult(
            task_id=qa['qa_id'],
            task_type=TaskType.QA.value,
            success=True,
            completion_score=calculate_completion_score(response, ground_truth=qa['answer']),  # ✅ 동적
            accuracy_score=calculate_accuracy_score(response, qa['answer']),  # ✅ 동적
            execution_time=execution_time,
            tokens_used={"input": estimate_tokens(qa['question']),  # ✅ 동적
                         "output": estimate_tokens(response)},
            tool_calls=[],  # extract_tools(response) 사용 가능
            attempts=1,
            errors=[],
            timestamp=datetime.now()
        )
    
        monitor.record_task(task)
    
        # Layer 2 평가 (선택적)
        if 'expected_tools' in qa and qa['expected_tools']:
            monitor.tool_selection_tracker.evaluate_selection(
                task.task_id,
                qa['expected_tools'],
                task.tool_calls
            )
    
    # 결과 저장
    monitor.save_to_file("evaluation_results/test_results.json")
```

### 10.3 Phase 3: Threshold 검증
```python
    # Threshold 비교
    comparison = monitor.compare_with_thresholds()
    
    # Pass/Fail 판정
    failed_metrics = []
    for metric, result in comparison.items():
        if result['status'] == 'fail':
            failed_metrics.append(metric)
            print(f"❌ {metric}: {result['message']}")
        else:
            print(f"✅ {metric}: {result['message']}")
    
    # 전체 상태
    if not failed_metrics:
        print("\n✅ 모든 메트릭 통과! 배포 가능")
        sys.exit(0)
    else:
        print(f"\n❌ {len(failed_metrics)}개 메트릭 실패. 개선 필요:")
        for m in failed_metrics:
            print(f"  - {m}")
        sys.exit(1)
```

### 10.4 Phase 4: 결과 분석

1

**Dashboard 확인**

FastAPI Dashboard로 결과 시각화 (agent-eval dashboard)

2

**이상치 분석**

Test Transparency Manager로 이상 징후, 병목 구간 식별

3

**개선 방안 도출**

Actionable Insights 기능으로 구체적인 개선점 제시

4

**리포트 생성**

Dashboard에서 PDF/HTML 리포트 다운로드 및 공유

### 10.5 CI/CD 통합

#### 품질 게이트 스크립트 예제
```python
    # scripts/quality_gate.py
    from agent_evaluator import PerformanceMonitor
    import sys
    import os
    
    # 환경 설정
    environment = os.getenv('ENV', 'development')
    
    # Test Configuration에서 Monitor 로드
    monitor = PerformanceMonitor.from_test_config(
        f"test_config_{environment}"
    )
    
    # Golden Dataset 기반 평가 수행
    monitor.load_golden_dataset()
    for qa in monitor.golden_datasets:
        # Agent 실행 및 평가
        # ... (실행 코드)
        pass
    
    # Threshold 검증
    comparison = monitor.compare_with_thresholds()
    
    # Pass/Fail 판정
    failed_metrics = [m for m, r in comparison.items() if r['status'] == 'fail']
    
    if not failed_metrics:
        print("✅ 모든 메트릭 통과! 배포 가능")
        sys.exit(0)
    else:
        print(f"❌ {len(failed_metrics)}개 메트릭 실패. 개선 필요")
        for m in failed_metrics:
            print(f"  - {m}: {comparison[m]['message']}")
        sys.exit(1)
```

**✅ 완전한 자동화:** 이 워크플로우를 사용하면 Golden Dataset 작성 → 평가 실행 → Threshold 검증 → CI/CD 통합까지 완전 자동화할 수 있습니다. 

## 🔬 11. 고급 기능

### 11.1 Test Transparency Manager - 5개 고급 분석 기능 (Python API)

**💡 Test Transparency Manager란?** 메트릭 계산 과정을 완전히 추적하고, 이상 징후를 자동으로 탐지하며, AI 기반 개선 방안을 제시하는 고급 분석 도구입니다.   
  
**사용 방법:**

  * **Python API:** 5개 고급 분석 기능 (이상치 탐지, 상관관계 분석, 성능 병목, 데이터 품질, 개선 방안) - 아래 섹션 참고
  * **FastAPI Dashboard (Port 8765):** 투명성 섹션 - 메타 투명성 기능 (Traces, Annotations, Audit Log, 상세 리포트)

**참고:** 메인 Dashboard의 "💡 Insights" 탭은 임계값 기반 Alerts 및 Recommendations를 제공합니다. Test Transparency Manager는 더 심층적인 통계 분석 및 AI 기반 인사이트를 제공합니다. 

#### 기능 1: 메트릭 이상치 탐지 (Anomaly Detection)

**설명:** Z-Score 기반 통계 분석으로 비정상적인 메트릭 값을 자동 탐지합니다.
```python
    from agent_evaluator.utils.transparency_manager import TestTransparencyManager

    transparency = TestTransparencyManager(output_dir="evaluation_results")
    
    # 메트릭 이상치 탐지
    anomalies = transparency.analyze_metric_anomalies(
        monitor,
        zscore_threshold=2.5  # 표준편차 2.5배 초과 시 이상치로 판정
    )
    
    print(f"발견된 이상치: {len(anomalies)}개")
    for anomaly in anomalies:
        print(f"  - {anomaly['metric']}: {anomaly['value']} (Z-Score: {anomaly['zscore']:.2f})")
        print(f"    평균: {anomaly['mean']:.2f}, 표준편차: {anomaly['std']:.2f}")
```

**활용:** 갑작스런 성능 저하, 비용 급증, 품질 하락을 조기에 발견하여 신속한 대응 가능

#### 기능 2: 메트릭 상관관계 분석 (Correlation Analysis)

**설명:** 메트릭 간 상호 영향을 분석하여 숨겨진 패턴을 발견합니다.
```python
    # 메트릭 상관관계 분석
    correlations = transparency.analyze_metric_correlations(monitor)
    
    print("강한 양의 상관관계 (함께 증가):")
    for corr in correlations['strong_positive']:
        print(f"  {corr['metric1']} ↔ {corr['metric2']}: {corr['correlation']:.2f}")
        print(f"    해석: {corr['interpretation']}")
    
    print("\n강한 음의 상관관계 (반비례):")
    for corr in correlations['strong_negative']:
        print(f"  {corr['metric1']} ↔ {corr['metric2']}: {corr['correlation']:.2f}")
        print(f"    해석: {corr['interpretation']}")
```

**활용:** 예) "Latency가 증가하면 Quality가 감소" → 응답 시간 최적화가 품질 개선에 직접 영향

#### 기능 3: 성능 병목 식별 (Performance Bottleneck Identification)

**설명:** Critical Path 분석으로 성능 저하의 주요 원인을 식별합니다.
```python
    # 성능 병목 식별
    bottlenecks = transparency.identify_performance_bottlenecks(monitor)
    
    print("Critical 병목 (즉시 해결 필요):")
    for b in bottlenecks['critical_bottlenecks']:
        print(f"  - {b['metric']}: {b['description']}")
        print(f"    심각도: {b['severity']}, 영향: {b['impact']}")
        print(f"    권장 조치: {b['recommendation']}")
    
    print("\nWarning 병목 (모니터링 필요):")
    for b in bottlenecks['warning_bottlenecks']:
        print(f"  - {b['metric']}: {b['description']}")
```

**활용:** 성능 최적화의 우선순위를 정하고, 가장 효과적인 개선 영역을 파악

#### 기능 4: 데이터 품질 검증 (Data Quality Validation)

**설명:** 평가 데이터의 무결성, 완전성, 일관성을 자동으로 검증합니다.
```python
    # 데이터 품질 검증
    quality_report = transparency.generate_data_quality_report(monitor)
    
    print(f"전체 데이터 품질 점수: {quality_report['overall_score']:.1f}/10")
    print(f"  - 완전성 (Completeness): {quality_report['completeness_score']:.1f}/10")
    print(f"  - 일관성 (Consistency): {quality_report['consistency_score']:.1f}/10")
    print(f"  - 정확성 (Accuracy): {quality_report['accuracy_score']:.1f}/10")
    
    if quality_report['issues']:
        print("\n발견된 문제:")
        for issue in quality_report['issues']:
            print(f"  - [{issue['severity']}] {issue['type']}: {issue['description']}")
            print(f"    해결 방법: {issue['solution']}")
```

**활용:** 평가 결과의 신뢰성을 보장하고, 데이터 입력 오류를 조기에 발견

#### 기능 5: 실행 가능한 개선 방안 (Actionable Insights)

**설명:** AI 기반 분석으로 구체적이고 실행 가능한 개선 방안을 우선순위와 함께 제시합니다.
```python
    # 실행 가능한 개선 방안
    insights = transparency.generate_actionable_insights(monitor)
    
    print("High Priority 개선 방안 (즉시 실행):")
    for insight in insights['high_priority']:
        print(f"  - {insight['title']}")
        print(f"    현재 상태: {insight['current_state']}")
        print(f"    권장 조치: {insight['recommendation']}")
        print(f"    예상 효과: {insight['expected_impact']}")
        print(f"    구현 난이도: {insight['difficulty']}")
    
    print("\nMedium Priority 개선 방안 (계획적 실행):")
    for insight in insights['medium_priority']:
        print(f"  - {insight['title']}: {insight['recommendation']}")
    
    print("\nLow Priority 개선 방안 (선택적 실행):")
    for insight in insights['low_priority']:
        print(f"  - {insight['title']}")
```

**활용:** 개발 로드맵 수립, 성능 개선 작업의 우선순위 결정, ROI 높은 최적화 식별

**✅ 5개 기능의 시너지:** 이 기능들을 함께 사용하면 "이상치 탐지 → 상관관계 분석 → 병목 식별 → 데이터 검증 → 개선 방안 도출"의 완전한 분석 워크플로우를 구축할 수 있습니다. 

### 11.2 메타 투명성 기능 (Traces, Annotations, Audit Log)

**💡 메타 투명성이란?** 메트릭 계산 과정을 단계별로 추적하고, 팀 간 커뮤니케이션을 위한 주석을 추가하며, 모든 시스템 이벤트를 감사 로그로 기록하는 기능입니다.   
  
**사용 위치:**

  * **FastAPI Dashboard (Port 8765):** 투명성 섹션 - GUI로 Traces, Annotations, Audit Log 조회
  * **Python API:** TestTransparencyManager - 프로그래밍 방식으로 메타 데이터 관리

#### 기능 1: 메트릭 추적 (Traces)

**설명:** 각 메트릭의 계산 과정을 단계별로 추적하여 투명성을 제공합니다.
```python
    # 메트릭 계산 시작
    trace_id = transparency.start_metric_calculation(
        metric_name="tcr",
        metric_type="basic",
        task_id="task_001"
    )
    
    # 단계별 추적
    transparency.log_calculation_step(
        trace_id,
        step_name="Load TaskResults",
        description="데이터베이스에서 TaskResult 로드",
        input_data={"task_count": 100},
        output_data={"loaded": 100},
        status="completed"
    )
    
    # 최종 결과
    transparency.end_metric_calculation(
        trace_id,
        final_result={"value": 95.5, "unit": "%"},
        explanation="95.5%의 작업이 성공적으로 완료됨"
    )
    
    # 추적 기록 조회
    traces = transparency.get_metric_traces(metric_name="tcr")
    for trace in traces:
        print(f"Trace {trace['trace_id']}: {trace['final_result']}")
```

**활용:** 메트릭 계산의 정확성 검증, 디버깅, 계산 로직 이해

#### 기능 2: 주석 및 코멘트 (Annotations)

**설명:** 메트릭, Task, Dataset에 주석을 추가하여 팀 간 커뮤니케이션을 개선합니다.
```python
    # 주석 추가
    annotation_id = transparency.add_annotation(
        target_type="metric",
        target_id="metric_tcr",
        annotation_type="issue",
        priority="high",
        title="TCR 급락 현상",
        content="금일 오전 10시 이후 TCR이 80%로 급락. 원인 조사 필요.",
        author="qa_manager"
    )
    
    # 답글 추가
    transparency.add_annotation_reply(
        annotation_id,
        author="developer",
        content="확인 결과 API 타임아웃 증가가 원인. 수정 중."
    )
    
    # 주석 조회
    annotations = transparency.get_annotations(
        target_type="metric",
        target_id="metric_tcr",
        status="open"
    )
    
    # 주석 상태 변경
    transparency.update_annotation_status(annotation_id, "resolved")
```

**활용:** 이슈 추적, 팀 협업, 문제 해결 과정 기록, 품질 관리

#### 기능 3: Audit Log (감사 로그)

**설명:** 모든 시스템 이벤트를 자동으로 기록하여 보안 감사 및 변경 추적이 가능합니다.
```python
    # Audit Log는 자동 생성됨
    # 예: Threshold 변경 시 자동 로그
    
    # Audit Log 조회
    logs = transparency.get_audit_logs(
        event_type="data_edit",
        user="admin",
        start_date="2025-11-30",
        end_date="2025-11-30"
    )
    
    for log in logs:
        print(f"{log['timestamp']}: {log['user']} - {log['action']}")
        print(f"  Target: {log['target_type']}/{log['target_id']}")
        print(f"  Details: {log['details']}")
```

**활용:** 규정 준수, 보안 감사, 변경 이력 추적, 문제 원인 분석

**⚠️ 메타 투명성 vs 고급 분석 기능 차이:**

  * **메타 투명성 (Traces, Annotations, Audit Log):** "어떻게 계산되었는가?" - 계산 과정 추적 및 기록
  * **고급 분석 기능 (10.1의 5개 기능):** "결과가 의미하는 바는?" - 통계 분석 및 AI 기반 인사이트

### 11.3 버전 관리 (Versioning)

Golden Dataset과 설정 파일은 git을 통해 버전 관리하는 것을 권장합니다.

```bash
    # results/golden_datasets/를 git으로 관리
    git add results/golden_datasets/
    git commit -m "feat: golden dataset v2 추가"

    # 이전 버전 복원
    git checkout HEAD~1 -- results/golden_datasets/my_dataset.json
```

**💡 고급 기능 종합 활용:**

  * **개발 단계:** 5개 고급 분석 기능으로 성능 문제 조기 발견 및 개선
  * **테스트 단계:** 메타 투명성으로 계산 과정 검증 및 팀 협업
  * **프로덕션:** Audit Log 및 버전 관리로 규정 준수 및 이력 추적

대규모 팀이나 엔터프라이즈 환경에서 특히 유용하며, 품질 관리 프로세스를 체계화하고 규정 준수를 지원합니다. 

## 🆘 12. 문제 해결 (Troubleshooting)

### 12.1 일반적인 문제

#### Q1: TCR이 예상보다 낮게 나옵니다

**원인:**

  * TaskResult의 `success` 필드가 False로 설정됨
  * completion_score가 1.0 미만

**해결:**
```python
    # TCR 계산 로직 확인
    tcr_data = monitor.tcr_tracker.calculate_tcr()
    print(f"Total: {tcr_data['total_tasks']}")
    print(f"Completed: {tcr_data['completed_tasks']}")
    print(f"Success: {tcr_data['successful_tasks']}")
    
    # 실패 작업 조회
    failed_tasks = [t for t in monitor.tasks if not t.success]
    for task in failed_tasks:
        print(f"Task {task.task_id}: {task.errors}")
```

#### Q2: Tool Selection Accuracy가 계산되지 않습니다

**원인:**

  * Golden Dataset에 expected_tools가 없음
  * evaluate_selection() 메서드를 호출하지 않음

**해결:**
```python
    # Golden Dataset 확인
    for qa in monitor.golden_datasets:
        if 'expected_tools' not in qa or not qa['expected_tools']:
            print(f"Warning: {qa['qa_id']} has no expected_tools")
    
    # 수동 평가 호출
    if 'expected_tools' in qa and qa['expected_tools']:
        monitor.tool_selection_tracker.evaluate_selection(
            task.task_id,
            qa['expected_tools'],
            task.tool_calls
        )
```

#### Q3: Dashboard가 로드되지 않습니다

**원인:**

  * performance_data.json 파일이 없음
  * 파일 형식이 잘못됨

**해결:**
```python
    # 데이터 파일 확인
    import os
    if not os.path.exists("evaluation_results/performance_data.json"):
        print("❌ performance_data.json이 없습니다.")
        print("   평가를 먼저 수행하고 save_to_file()을 호출하세요.")
    
    # 파일 형식 검증
    import json
    with open("evaluation_results/performance_data.json") as f:
        data = json.load(f)
        print(f"✅ 유효한 JSON. Tasks: {len(data.get('tasks', []))}")
```

### 12.2 성능 문제

증상 | 원인 | 해결 방법  
---|---|---  
Dashboard 로딩 느림 | 대용량 데이터 (1000+ tasks) | 샘플링 사용 또는 기간별 필터링  
메트릭 계산 느림 | Layer 3 고급 메트릭 사용 | Profile "minimal" 사용 또는 샘플링  
메모리 부족 | 너무 많은 TaskResult 메모리 보관 | 주기적으로 save_to_file() 및 메모리 정리  
  
### 12.3 디버깅 팁
```python
    # 디버그 모드로 리포트 생성
    report = monitor.generate_report(debug=True)
    
    # Layer 2 메트릭 상세 확인
    print("Tool Selection:")
    stats = monitor.tool_selection_tracker.get_accuracy_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("Agent Coordination:")
    score = monitor.agent_coordination_tracker.calculate_coordination_score()
    for key, value in score.items():
        print(f"  {key}: {value}")
    
    print("Workflow Execution:")
    workflow_stats = monitor.workflow_tracker.calculate_execution_success_rate()
    for key, value in workflow_stats.items():
        print(f"  {key}: {value}")
    
    # Transparency 분석
    from agent_evaluator.utils.transparency_manager import TestTransparencyManager
    transparency = TestTransparencyManager()
    
    # 데이터 품질 검증
    quality = transparency.generate_data_quality_report(monitor)
    print(f"Overall Quality Score: {quality['overall_score']:.1f}/10")
    print("Issues:")
    for issue in quality['issues']:
        print(f"  - {issue['type']}: {issue['description']}")
```

### 12.4 지원 및 문서

#### 📚 상세 문서

  * `docs/01_API.md` \- API 레퍼런스
  * `docs/03_AGENTIC_AI_METRICS_GUIDE.md` \- Layer 2 가이드
  * `docs/04_GOLDEN_DATASET_GUIDE.md` \- Dataset 가이드
  * `docs/05_THRESHOLD_CONFIGURATION_GUIDE.md` \- Threshold 가이드

#### 💡 예제 코드

  * `Evaluator_Examples/framework_with_layer2_example.py`
  * `Evaluator_Examples/threshold_validation_example.py`
  * `Evaluator_Examples/golden_dataset_evaluation_example.py`

© 2025 Agent Evaluator. All rights reserved.

**최종 업데이트** : 2026-03-27 | **버전** : Agent Evaluator v0.6.5 | **문서** : 종합 학습 가이드
