# 📚 API 레퍼런스

전체 API 문서 및 클래스 참조

# API 레퍼런스

> 📖 Agent Evaluator의 전체 API 문서

이 문서는 Agent Evaluator의 모든 클래스, 메서드, 파라미터에 대한 완전한 레퍼런스를 제공합니다.

## 버전 정보

**현재 버전:** v0.5.2

**최종 업데이트:** 2026-03-19

**테스트된 환경:**

  * Python: 3.8+ (3.12 테스트 완료)
  * LangChain: 0.1.0+ (선택)
  * LangGraph: 0.1.0+ (선택)
  * DeepEval: 0.20.0+ (선택)
  * Ragas: 0.1.0+ (선택)
  * CrewAI: 0.11.0+ (선택)
  * AutoGen: 0.2.0+ (선택)

## 목차

  * [🚀 0. 빠른 시작 (3분 API 가이드)](<#빠른-시작>)
  * [1\. 핵심 클래스](<#핵심-클래스>)
    * [1.1 PerformanceMonitor](<#performancemonitor>)
    * [1.2 HybridPerformanceMonitor](<#hybridperformancemonitor>)
    * [1.3 TaskResult](<#taskresult>)
    * [1.4 TaskType](<#tasktype>)
    * [1.5 Layer 2: Agentic AI Metrics](<#layer-2-agentic-ai-metrics>)
      * [1.5.1 ToolSelectionTracker](<#toolselectiontracker>)
      * [1.5.2 AgentCoordinationTracker](<#agentcoordinationtracker>)
      * [1.5.3 WorkflowExecutionTracker](<#workflowexecutiontracker>)
  * [**🛡️ 2. 보안 메트릭 (Security Metrics)**](<#보안-메트릭>)
    * [2.1 Layer 1: Native Security Metrics](<#layer1-security>)
      * [2.1.1 InputSanitizationTracker](<#inputsanitizationtracker>)
      * [2.1.2 OutputLeakageDetector](<#outputleakagedetector>)
      * [2.1.3 ToolAuthorizationTracker](<#toolauthorizationtracker>)
    * [2.2 Layer 2: Agentic Security Metrics](<#layer2-security>)
      * [2.2.1 PrivilegeEscalationDetector](<#privilegeescalationdetector>)
      * [2.2.2 ToolChainAttackDetector](<#toolchainattackdetector>)
  * [3\. 리포트 클래스](<#리포트-클래스>)
  * [4\. 메트릭 어댑터](<#메트릭-어댑터>)
  * [5\. 헬퍼 함수](<#헬퍼-함수>)
    * [5.1 경로 헬퍼](<#path-helpers>)
    * [5.2 TaskResult 헬퍼](<#taskresult-helpers>)
    * [5.3 터미널 출력 메서드](<#터미널-출력-메서드>)
    * [5.4 보안 헬퍼 함수](<#security-helpers>)
    * [**5.5 Context Managers**](<#context-managers>)
    * [**5.6 LLM 통합 헬퍼**](<#llm-helpers>)
    * [**5.7 ExampleRunner**](<#example-runner>)
  * [**🔌 6. 프레임워크 통합 (v0.5.2)**](<#프레임워크-통합>)
    * [6.1 CrewAIEvaluator](<#crewai-evaluator>)
    * [6.2 LangChainEvaluator](<#langchain-evaluator>)
    * [6.3 LangGraphEvaluator](<#langgraph-evaluator>)
    * [6.4 AutoGenEvaluator](<#autogen-evaluator>)
  * [7\. 예외](<#예외>)
  * [8\. 전체 워크플로우 예제](<#전체-워크플로우-예제>)
  * [9\. 타입 힌트](<#타입-힌트>)

* * *

### 🔒 보안 지표

**AI Agent 보안 평가 기능이 추가되었습니다!**

  * ✅ **Layer 1 보안** : 입력 살균, 출력 유출 탐지, 도구 권한 관리
  * ✅ **Layer 2 보안** : 권한 상승 탐지, 공격 패턴 탐지
  * ✅ **무료 & 실시간** (< 15ms 오버헤드)

📚 **상세 가이드** : [보안 지표 가이드](<SECURITY_METRICS_GUIDE.html>)

## 🚀 0. 빠른 시작 (3분 API 가이드)

> 💡 **개발자를 위한 최소 실행 가이드** : 3분 안에 Agent Evaluator를 사용할 수 있는 핵심 API만 빠르게 소개합니다.

### 최소 실행 코드 (3줄)
```python
    [](<#cb0-1>)from agent_evaluator import PerformanceMonitor, create_taskresult
    [](<#cb0-2>)
    [](<#cb0-3>)monitor = PerformanceMonitor()
    [](<#cb0-4>)task = create_taskresult(
    [](<#cb0-5>)    task_id="t1", question="질문", response="답변",
    [](<#cb0-6>)    ground_truth="정답", execution_time=1.0
    [](<#cb0-7>))
    [](<#cb0-8>)monitor.record_task(task)
```

#### ✅ 보안 함수 Import
```python
    [](<#cb0_sec-1>)# Security helper functions
    [](<#cb0_sec-2>)from agent_evaluator.helpers import (
    [](<#cb0_sec-3>)    validate_input_security,
    [](<#cb0_sec-4>)    check_output_leakage,
    [](<#cb0_sec-5>)    validate_tool_authorization
    [](<#cb0_sec-6>))
    [](<#cb0_sec-7>)
    [](<#cb0_sec-8>)# Security metrics classes (optional)
    [](<#cb0_sec-9>)from agent_evaluator import (
    [](<#cb0_sec-10>)    InputSanitizationTracker,
    [](<#cb0_sec-11>)    OutputLeakageDetector,
    [](<#cb0_sec-12>)    ToolAuthorizationTracker,
    [](<#cb0_sec-13>)    PrivilegeEscalationDetector,
    [](<#cb0_sec-14>)    ToolChainAttackDetector
    [](<#cb0_sec-15>))
```

### API 사용 패턴 (3가지)

#### ✅ 패턴 1: 기본 패턴 (수동 기록)

**언제 사용?** 개별 작업을 하나씩 평가하고 싶을 때
```python
    [](<#cb0a-1>)from agent_evaluator import PerformanceMonitor, create_taskresult
    [](<#cb0a-2>)
    [](<#cb0a-3>)# 1. 모니터 생성
    [](<#cb0a-4>)monitor = PerformanceMonitor()
    [](<#cb0a-5>)
    [](<#cb0a-6>)# 2. Agent 실행
    [](<#cb0a-7>)question = "대한민국의 수도는?"
    [](<#cb0a-8>)response = my_agent(question)
    [](<#cb0a-9>)
    [](<#cb0a-10>)# 3. 결과 기록 (간소화된 API)
    [](<#cb0a-11>)task = create_taskresult(
    [](<#cb0a-12>)    task_id="task_001",
    [](<#cb0a-13>)    question=question,
    [](<#cb0a-14>)    response=response,
    [](<#cb0a-15>)    ground_truth="서울",
    [](<#cb0a-16>)    execution_time=1.2  # 초 단위
    [](<#cb0a-17>))
    [](<#cb0a-18>)monitor.record_task(task)
    [](<#cb0a-19>)
    [](<#cb0a-20>)# 4. 레포트 확인
    [](<#cb0a-21>)report = monitor.generate_report()
    [](<#cb0a-22>)print(f"TCR: {report['tcr']}%")
```

#### ⚡ 패턴 2: 자동 평가 패턴 (Golden Dataset)

**언제 사용?** 대량의 테스트 케이스를 자동으로 평가하고 싶을 때
```python
    [](<#cb0b-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb0b-2>)
    [](<#cb0b-3>)# 1. Agent 함수 정의 (Dict 반환 필수)
    [](<#cb0b-4>)def my_agent(question: str) -> dict:
    [](<#cb0b-5>)    answer = llm.invoke(question)
    [](<#cb0b-6>)    return {"answer": answer}  # 'answer' 키 필수
    [](<#cb0b-7>)
    [](<#cb0b-8>)# 2. 단 1줄로 자동 평가
    [](<#cb0b-9>)monitor = PerformanceMonitor()
    [](<#cb0b-10>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb0b-11>)    agent_fn=my_agent,
    [](<#cb0b-12>)    dataset_path="golden_datasets/sample.json"
    [](<#cb0b-13>))
    [](<#cb0b-14>)
    [](<#cb0b-15>)# ✅ 자동 계산: TCR, Accuracy, Hallucination Rate
```

#### 🔬 패턴 3: 고급 평가 패턴 (Layer 2 + 3)

**언제 사용?** 도구 선택, 에이전트 협업, AI 품질을 깊이 평가하고 싶을 때
```python
    [](<#cb0c-1>)from agent_evaluator import HybridPerformanceMonitor
    [](<#cb0c-2>)
    [](<#cb0c-3>)# 1. Hybrid 모니터 생성 (DeepEval, Ragas 포함)
    [](<#cb0c-4>)monitor = HybridPerformanceMonitor(
    [](<#cb0c-5>)    use_deepeval=True,   # Layer 3: AI 품질 평가
    [](<#cb0c-6>)    use_ragas=False      # RAG 시스템은 True
    [](<#cb0c-7>))
    [](<#cb0c-8>)
    [](<#cb0c-9>)# 2. Layer 2 평가 (도구 선택)
    [](<#cb0c-10>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb0c-11>)    agent_fn=my_agent,
    [](<#cb0c-12>)    dataset_path="golden_datasets/sample.json",
    [](<#cb0c-13>)    enable_layer2_metrics=True  # ← Layer 2 활성화
    [](<#cb0c-14>))
    [](<#cb0c-15>)
    [](<#cb0c-16>)# ✅ 측정: Layer 1 + Layer 2 + Layer 3 모든 메트릭
```

### 핵심 클래스 요약

클래스 | 용도 | 필수 파라미터  
---|---|---  
`PerformanceMonitor` | 기본 평가 (Layer 1) | 없음 (즉시 사용 가능)  
`HybridPerformanceMonitor` | 고급 평가 (Layer 1+2+3) | `use_deepeval`, `use_ragas`  
`TaskResult` | 작업 결과 저장 | `task_id`, `task_type`, `success`, `completion_score`, `accuracy_score`, `execution_time`, `tokens_used`, `tool_calls`, `attempts`, `errors`, `timestamp`  
  
### 핵심 메서드 요약

메서드 | 기능 | 반환값  
---|---|---  
`record_task(task)` | 작업 결과 기록 | 없음  
`evaluate_with_golden_dataset()` | 자동 평가 (권장) | `Dict[str, Any]`  
`generate_report()` | 레포트 생성 | `Dict[str, Any]`  
`compare_with_thresholds()` | 임계값 비교 | `Dict[str, Any]`  
  
### 자주 하는 질문 (FAQ)

**Q1: TaskResult의 completion_score는 무엇인가요?**

**A** : 작업 완료 정도를 나타내는 0.0~1.0 값입니다.

  * `1.0`: 완전히 성공
  * `0.7~0.99`: 부분 성공
  * `0.0~0.69`: 실패

**Q2: Golden Dataset 형식은?**

**A** : JSON 배열 형식입니다.
```json
    [
      {
        "question": "프랑스의 수도는?",
        "ground_truth": "파리",
        "expected_tools": ["search"]  // Layer 2용 (선택)
      }
    ]
```

**Q3: Layer 2와 Layer 3의 차이는?**

**A** :

  * **Layer 2** : 에이전트 시스템 메트릭 (도구 선택, 협업, 워크플로우) - **무료**
  * **Layer 3** : AI 품질 메트릭 (DeepEval, Ragas) - **OpenAI API 필요**

> 📚 **더 자세한 내용** : 아래 섹션에서 각 클래스와 메서드의 상세한 API 명세를 확인하세요.

* * *

## 1\. 핵심 클래스

### PerformanceMonitor

기본 성능 모니터링 클래스입니다. 네이티브 메트릭만 사용합니다.

> 👨‍💻 **개발자 가이드** : 가장 기본적인 클래스로, **API 키 없이 즉시 사용** 할 수 있습니다. 개발/테스트 단계에서 권장합니다.

#### 🔧 내부 Tracker 구조

PerformanceMonitor는 내부적으로 **16개의 Tracker** 를 사용하여 메트릭을 수집합니다:

##### 📊 Layer 1 - Basic Metrics (7개)

  * `TaskCompletionTracker`: 작업 완료율 추적
  * `AccuracyEvaluator`: 정확도 평가 (4가지 유사도 메트릭)
  * `HallucinationDetector`: 환각 탐지 (opt-in)
  * `ResponseQualityEvaluator`: 응답 품질 평가
  * `LatencyTracker`: 지연시간 추적
  * `TokenEconomyTracker`: 토큰 경제성 분석
  * `ToolCallAnalyzer`: 도구 호출 분석

##### 🛡️ Layer 1 - Security (3개)

  * `InputSanitizationTracker`: 입력 보안 검증 → [Section 2.1.1](<#inputsanitizationtracker>)
  * `OutputLeakageDetector`: 출력 유출 탐지 → [Section 2.1.2](<#outputleakagedetector>)
  * `ToolAuthorizationTracker`: 도구 권한 검증 → [Section 2.1.3](<#toolauthorizationtracker>)

##### 🤖 Layer 2 - Agentic AI (4개)

  * `RetryCorrectionTracker`: 재시도/수정 추적
  * `ToolSelectionTracker`: 도구 선택 최적화 → [Section 1.5.1](<#toolselectiontracker>)
  * `AgentCoordinationTracker`: 에이전트 협업 → [Section 1.5.2](<#agentcoordinationtracker>)
  * `WorkflowExecutionTracker`: 워크플로우 실행 → [Section 1.5.3](<#workflowexecutiontracker>)

##### 🛡️ Layer 2 - Security (2개)

  * `PrivilegeEscalationDetector`: 권한 상승 탐지 → [Section 2.2.1](<#privilegeescalationdetector>)
  * `ToolChainAttackDetector`: 도구 체인 공격 탐지 → [Section 2.2.2](<#toolchainattackdetector>)

**📝 참고:** 대부분의 Tracker는 PerformanceMonitor가 자동으로 관리합니다. 고급 사용자만 직접 import하여 개별 사용할 수 있습니다.

#### 생성자
```json
    [](<#cb1-1>)PerformanceMonitor(
    [](<#cb1-2>)    pricing: Optional[Dict[str, float]] = None,
    [](<#cb1-3>)    enable_transparency: bool = False
    [](<#cb1-4>))
```

**파라미터** \- `pricing` (dict, optional): 토큰 가격 설정 - `input` (float): 입력 토큰 가격 ($/1K tokens) \- `output` (float): 출력 토큰 가격 ($/1K tokens) - 기본값: `{"input": 0.003, "output": 0.015}` (GPT-4o-mini)

  * `enable_transparency` (bool, optional): Test 투명성 추적 활성화 여부 (기본값: False) 
    * True일 경우 TestTransparencyManager를 초기화하여 평가 과정을 추적합니다
    * DataEditorManager와 통합되어 Dashboard에서 평가 이력을 관리할 수 있습니다

**참고** : 임계값(thresholds)은 생성자가 아닌 `load_thresholds_from_config()` 메서드나 `from_test_config()` 클래스 메서드를 통해 설정합니다

**예제**
```python
    [](<#cb2-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb2-2>)
    [](<#cb2-3>)# 기본 생성
    [](<#cb2-4>)monitor = PerformanceMonitor()
    [](<#cb2-5>)
    [](<#cb2-6>)# 커스텀 가격 설정
    [](<#cb2-7>)monitor = PerformanceMonitor(
    [](<#cb2-8>)    pricing={"input": 0.00015, "output": 0.0006}  # GPT-4o-mini
    [](<#cb2-9>))
    [](<#cb2-10>)
    [](<#cb2-11>)# 투명성 추적 활성화
    [](<#cb2-12>)monitor = PerformanceMonitor(
    [](<#cb2-13>)    pricing={"input": 0.003, "output": 0.015},
    [](<#cb2-14>)    enable_transparency=True  # Test 투명성 추적 활성화
    [](<#cb2-15>))
    [](<#cb2-16>)
    [](<#cb2-17>)# 임계값은 별도 메서드로 설정
    [](<#cb2-18>)monitor.load_thresholds_from_config("test_config_20241129_234453")
    [](<#cb2-19>)# 또는 직접 설정
    [](<#cb2-20>)monitor.thresholds = {
    [](<#cb2-21>)    "tcr": 90.0,
    [](<#cb2-22>)    "accuracy": 85.0,
    [](<#cb2-23>)    "hallucination": 5.0,
    [](<#cb2-24>)    "latency": 3.0,
    [](<#cb2-25>)    "cost_per_task": 0.05
    [](<#cb2-26>)}
```

#### 메서드

##### record_task()

작업 결과를 기록합니다.
```json
    [](<#cb3-1>)record_task(
    [](<#cb3-2>)    task_result: TaskResult,
    [](<#cb3-3>)    ground_truth: Optional[Any] = None,
    [](<#cb3-4>)    context: Optional[str] = None,
    [](<#cb3-5>)    request: Optional[str] = None,
    [](<#cb3-6>)    expected_elements: Optional[List[str]] = None
    [](<#cb3-7>)) -> None
```

**파라미터** \- `task_result` (TaskResult): 기록할 작업 결과 - `ground_truth` (Any, optional): 정답 데이터 (현재 사용 안 함, TaskResult에 포함) - `context` (str, optional): 컨텍스트 정보 (현재 사용 안 함, TaskResult에 포함) - `request` (str, optional): 요청 내용 (현재 사용 안 함) - `expected_elements` (List[str], optional): 기대 요소 목록 (현재 사용 안 함)

**참고** : - 대부분의 정보는 TaskResult 객체에 포함되어 있습니다 - 추가 파라미터들은 향후 확장을 위해 남겨져 있으나 현재 구현에서는 사용되지 않습니다 - TaskResult에 `expected_tools`, `agent_interactions`, `chain_steps` 등 Layer 2 필드를 포함하면 자동으로 해당 메트릭이 계산됩니다

**예제**
```python
    [](<#cb4-1>)from agent_evaluator import TaskResult, TaskType
    [](<#cb4-2>)from datetime import datetime
    [](<#cb4-3>)
    [](<#cb4-4>)task = TaskResult(
    [](<#cb4-5>)    task_id="task_001",
    [](<#cb4-6>)    task_type=TaskType.QA.value,
    [](<#cb4-7>)    success=True,
    [](<#cb4-8>)    completion_score=0.95,
    [](<#cb4-9>)    accuracy_score=0.90,
    [](<#cb4-10>)    execution_time=1.5,
    [](<#cb4-11>)    tokens_used={"input": 150, "output": 200, "total": 350},
    [](<#cb4-12>)    tool_calls=["search", "calculator"],
    [](<#cb4-13>)    attempts=1,
    [](<#cb4-14>)    errors=[],
    [](<#cb4-15>)    timestamp=datetime.now()
    [](<#cb4-16>))
    [](<#cb4-17>)
    [](<#cb4-18>)monitor.record_task(task)
```

##### generate_report()

평가 리포트를 생성합니다.
```json
    [](<#cb5-1>)generate_report() -> EvaluationReport
```

**반환값** \- `EvaluationReport`: 평가 리포트 객체 - `period` (str): 고정값 “current_session” - `total_tasks` (int): 총 작업 수 - `accuracy_metrics` (dict): 정확도 관련 메트릭 - `efficiency_metrics` (dict): 효율성 메트릭 - `quality_metrics` (dict): 품질 메트릭 - `alerts` (list): 알림 목록 - `recommendations` (list): 개선 제안 - `timestamp` (datetime): 생성 시각

**참고** : - 클래스 이름은 `EvaluationReport`입니다 (`PerformanceReport`가 아님) - `period` 파라미터는 없으며, 항상 “current_session”으로 설정됩니다

**예제**
```python
    [](<#cb6-1>)report = monitor.generate_report()
    [](<#cb6-2>)
    [](<#cb6-3>)# 리포트 필드 접근
    [](<#cb6-4>)print(f"기간: {report.period}")  # "current_session"
    [](<#cb6-5>)print(f"총 작업: {report.total_tasks}")
    [](<#cb6-6>)
    [](<#cb6-7>)# TCR
    [](<#cb6-8>)tcr_data = report.accuracy_metrics['tcr']
    [](<#cb6-9>)print(f"TCR: {tcr_data['tcr']:.1f}%")
    [](<#cb6-10>)
    [](<#cb6-11>)# 정확도
    [](<#cb6-12>)accuracy = report.accuracy_metrics['accuracy_scores']
    [](<#cb6-13>)print(f"평균 정확도: {accuracy['overall_accuracy']:.1f}%")
    [](<#cb6-14>)
    [](<#cb6-15>)# 비용
    [](<#cb6-16>)tokens = report.efficiency_metrics['tokens']
    [](<#cb6-17>)print(f"총 비용: ${tokens['total_cost']:.4f}")
```

##### print_report()

콘솔에 포맷팅된 리포트를 출력합니다.
```json
    [](<#cb7-1>)print_report(
    [](<#cb7-2>)    report: Optional[EvaluationReport] = None
    [](<#cb7-3>)) -> None
```

**파라미터** \- `report` (EvaluationReport, optional): 출력할 리포트 (None이면 자동 생성)

**참고** : - 메서드명이 `print_summary()`가 아닌 `print_report()`입니다 - 리포트를 전달하지 않으면 내부적으로 `generate_report()`를 호출합니다

**예제**
```python
    [](<#cb8-1>)# 자동으로 리포트 생성 후 출력
    [](<#cb8-2>)monitor.print_report()
    [](<#cb8-3>)
    [](<#cb8-4>)# 기존 리포트 출력
    [](<#cb8-5>)report = monitor.generate_report()
    [](<#cb8-6>)monitor.print_report(report)
    [](<#cb8-7>)
    [](<#cb8-8>)# 출력 예:
    [](<#cb8-9>)# ================================================================================
    [](<#cb8-10>)# AI AGENT PERFORMANCE EVALUATION REPORT
    [](<#cb8-11>)# Generated: 2024-11-30 12:34:56
    [](<#cb8-12>)# Total Tasks Evaluated: 100
    [](<#cb8-13>)# ================================================================================
    [](<#cb8-14>)#
    [](<#cb8-15>)# 📊 ACCURACY & QUALITY METRICS
    [](<#cb8-16>)# --------------------------------------------------------------------------------
    [](<#cb8-17>)# Task Completion Rate: 92.5%
    [](<#cb8-18>)#   - Full Success: 85 tasks
    [](<#cb8-19>)#   - Partial Success: 8 tasks
    [](<#cb8-20>)#   - Failures: 7 tasks
    [](<#cb8-21>)#   - Status: Good Performance
    [](<#cb8-22>)# ...
```

##### save_to_file()

평가 데이터를 JSON 파일로 저장합니다.
```json
    [](<#cb9-1>)save_to_file(
    [](<#cb9-2>)    filename: str = "performance_data.json"
    [](<#cb9-3>)) -> str
```

**파라미터** \- `filename` (str): 저장할 파일명 - 절대 경로가 아닌 경우 자동으로 `evaluation_results/` 디렉토리에 저장됩니다

**반환값** \- `str`: 저장된 파일의 전체 경로

**참고** : - `include_tasks` 파라미터는 없으며, 항상 모든 작업 데이터를 저장합니다 - Evaluator 데이터(quality, hallucination, tool_selection 등)도 함께 저장됩니다

**예제**
```python
    [](<#cb10-1>)# 기본 경로에 저장 (evaluation_results/performance_data.json)
    [](<#cb10-2>)saved_path = monitor.save_to_file()
    [](<#cb10-3>)print(f"저장됨: {saved_path}")
    [](<#cb10-4>)
    [](<#cb10-5>)# 커스텀 파일명 (evaluation_results/my_evaluation.json)
    [](<#cb10-6>)monitor.save_to_file("my_evaluation.json")
    [](<#cb10-7>)
    [](<#cb10-8>)# 절대 경로로 저장
    [](<#cb10-9>)monitor.save_to_file("/path/to/custom/location/data.json")
```

##### load_from_file() [클래스 메서드]

파일에서 데이터를 로드합니다.
```json
    [](<#cb11-1>)@classmethod
    [](<#cb11-2>)load_from_file(
    [](<#cb11-3>)    cls,
    [](<#cb11-4>)    filename: str = "performance_data.json"
    [](<#cb11-5>)) -> PerformanceMonitor
```

**파라미터** \- `filename` (str): 로드할 파일명

**반환값** \- `PerformanceMonitor`: 로드된 모니터 인스턴스

**예제**
```python
    [](<#cb12-1>)# 저장된 데이터 로드
    [](<#cb12-2>)monitor = PerformanceMonitor.load_from_file("my_evaluation.json")
    [](<#cb12-3>)
    [](<#cb12-4>)# 리포트 생성
    [](<#cb12-5>)report = monitor.generate_report()
    [](<#cb12-6>)
    [](<#cb12-7>)# Evaluator 데이터도 자동으로 복원됨
    [](<#cb12-8>)print(f"복원된 Quality 평가: {len(monitor.quality_evaluator.evaluations)}개")
    [](<#cb12-9>)print(f"복원된 Tool Selection: {len(monitor.tool_selection_tracker.selections)}개")
```

##### export_report()

리포트를 파일로 내보냅니다.
```json
    [](<#cb13-1>)export_report(
    [](<#cb13-2>)    filename: str,
    [](<#cb13-3>)    format: str = "json"
    [](<#cb13-4>)) -> None
```

**파라미터** \- `filename` (str): 저장할 파일명 - `format` (str): 파일 형식 (“json” 또는 “csv”)

**CSV 포맷 개선사항**

  * ✅ **Layer 1 메트릭** : TCR, Accuracy, Hallucination, Quality, Latency (avg, p95), Cost
  * ✅ **Layer 2 메트릭** : Tool Selection Accuracy, F1 Score (데이터 있을 경우)
  * ✅ **Layer 3 메트릭 (RAG)** : Faithfulness, Answer Relevancy, Context Recall, Context Precision (데이터 있을 경우)
  * ✅ 총 13개 이상의 메트릭 자동 export
  * ✅ 3개 컬럼 구조: Metric, Value, Unit

**CSV 출력 예제**
```python
    Metric,Value,Unit
    Task Completion Rate (TCR),95.00,%
    Overall Accuracy,88.50,%
    Hallucination Rate,0.00,%
    Response Quality,8.00,/10
    Average Latency,1.234,s
    P95 Latency,2.456,s
    Total Input Tokens,5000,tokens
    Total Output Tokens,7500,tokens
    Total Cost,0.0450,$
    Avg Cost per Task,0.0015,$
    Tool Selection Accuracy,92.00,%
    Faithfulness,0.850,score
    Answer Relevancy,0.880,score
    Context Recall,0.820,score
    Context Precision,0.860,score
    
```

**참고** : - `get_cost_analysis()` 메서드는 별도로 존재하지 않습니다 - 비용 정보는 `monitor.token_tracker.get_usage_stats()`로 접근 가능합니다 - `get_alerts()` 메서드도 별도로 존재하지 않습니다 - 알림은 `report.alerts`로 접근하거나 `monitor._generate_alerts()`를 직접 호출합니다 (내부 메서드)

**예제**
```python
    [](<#cb14-1>)# JSON으로 내보내기
    [](<#cb14-2>)monitor.export_report("report.json", format="json")
    [](<#cb14-3>)
    [](<#cb14-4>)# CSV로 내보내기
    [](<#cb14-5>)monitor.export_report("report.csv", format="csv")
    [](<#cb14-6>)
    [](<#cb14-7>)# 비용 분석 (get_cost_analysis 대신)
    [](<#cb14-8>)cost_stats = monitor.token_tracker.get_usage_stats()
    [](<#cb14-9>)print(f"총 비용: ${cost_stats['total_cost']:.4f}")
    [](<#cb14-10>)print(f"작업당 평균: ${cost_stats['avg_cost_per_task']:.4f}")
    [](<#cb14-11>)
    [](<#cb14-12>)# 알림 확인 (get_alerts 대신)
    [](<#cb14-13>)report = monitor.generate_report()
    [](<#cb14-14>)for alert in report.alerts:
    [](<#cb14-15>)    print(f"[{alert['severity'].upper()}] {alert['metric']}: {alert['message']}")
```

##### from_test_config() (클래스 메서드)

Test 구성에서 PerformanceMonitor 인스턴스를 생성합니다.
```json
    [](<#cb15-1>)@classmethod
    [](<#cb15-2>)from_test_config(
    [](<#cb15-3>)    cls,
    [](<#cb15-4>)    config_id: str,
    [](<#cb15-5>)    pricing: Optional[Dict[str, float]] = None
    [](<#cb15-6>)) -> PerformanceMonitor
```

**파라미터** \- `config_id` (str): Test 구성 ID (DataEditorManager에서 생성) - `pricing` (dict, optional): 토큰 가격 설정 (None이면 기본값 사용)

**반환값** \- `PerformanceMonitor`: 구성이 로드된 Monitor 인스턴스

**설명** \- Test 구성에서 자동으로 임계값, Golden Dataset 경로, 투명성 추적 설정 로드 - DataEditorManager와 통합되어 Dashboard에서 설정한 구성 자동 적용

**예제**
```python
    [](<#cb16-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb16-2>)
    [](<#cb16-3>)# Test 구성에서 Monitor 생성
    [](<#cb16-4>)monitor = PerformanceMonitor.from_test_config(
    [](<#cb16-5>)    config_id="test_config_20241129_234453"
    [](<#cb16-6>))
    [](<#cb16-7>)
    [](<#cb16-8>)# 임계값, Golden Dataset 경로가 자동으로 설정됨
    [](<#cb16-9>)print(f"임계값: {monitor.thresholds}")
    [](<#cb16-10>)print(f"Golden Dataset: {monitor.golden_dataset_path}")
```

##### load_thresholds_from_config()

DataEditorManager에서 임계값을 로드합니다.
```json
    [](<#cb17-1>)load_thresholds_from_config(
    [](<#cb17-2>)    config_id: Optional[str] = None
    [](<#cb17-3>)) -> Dict[str, float]
```

**파라미터** \- `config_id` (str, optional): Test 구성 ID (None이면 기본 임계값 사용)

**반환값** \- `dict`: 임계값 설정 - `tcr` (float): 최소 TCR - `accuracy` (float): 최소 정확도 - `hallucination` (float): 최대 환각률 - 기타 Layer 1, 2, 3 메트릭 임계값

**예제**
```python
    [](<#cb18-1>)# Test 구성에서 임계값 로드
    [](<#cb18-2>)thresholds = monitor.load_thresholds_from_config("test_config_20241129_234453")
    [](<#cb18-3>)
    [](<#cb18-4>)# 기본 임계값 로드
    [](<#cb18-5>)thresholds = monitor.load_thresholds_from_config()
```

##### load_golden_dataset()

Golden Dataset을 로드합니다.
```json
    [](<#cb19-1>)load_golden_dataset(
    [](<#cb19-2>)    dataset_path: Optional[str] = None
    [](<#cb19-3>)) -> List[Dict[str, Any]]
```

**파라미터** \- `dataset_path` (str, optional): Golden Dataset 파일 경로 - None이면 `self.golden_dataset_path` 사용 - 상대 경로는 `golden_datasets/` 디렉토리 기준

**반환값** \- `list`: Golden Dataset 항목 리스트 - 각 항목: QAPair 구조 (question, answer, context, ground_truth 등)

**예제**
```python
    [](<#cb20-1>)# Golden Dataset 로드
    [](<#cb20-2>)dataset = monitor.load_golden_dataset("sample_dataset.json")
    [](<#cb20-3>)
    [](<#cb20-4>)for qa_pair in dataset:
    [](<#cb20-5>)    print(f"질문: {qa_pair['question']}")
    [](<#cb20-6>)    print(f"정답: {qa_pair['ground_truth']}")
    [](<#cb20-7>)
    [](<#cb20-8>)    # Layer 2 필드도 사용 가능
    [](<#cb20-9>)    if 'expected_tools' in qa_pair:
    [](<#cb20-10>)        print(f"예상 도구: {qa_pair['expected_tools']}")
```

##### compare_with_thresholds()

현재 메트릭 값을 임계값과 비교합니다.
```json
    [](<#cb21-1>)compare_with_thresholds() -> Dict[str, Any]
```

**반환값** \- `dict`: 각 메트릭별 비교 결과 - `metric_name` (dict): - `name` (str): 메트릭 표시 이름 - `value` (float): 현재 값 - `threshold` (float): 임계값 - `status` (str): “pass” 또는 “fail” - `direction` (str): “higher” (높을수록 좋음) 또는 “lower” (낮을수록 좋음) - `unit` (str): 단위 (“%”, “초”, “$” 등)

**지원 메트릭** \- Layer 1: tcr, accuracy, hallucination, quality, latency, cost_per_task, tool_efficiency, retry_success_rate - Layer 2: tool_selection_accuracy, agent_coordination, workflow_execution \- Layer 3: faithfulness, context_precision, context_recall, answer_relevancy

**예제**
```python
    [](<#cb22-1>)# 임계값 설정
    [](<#cb22-2>)monitor.thresholds = {
    [](<#cb22-3>)    'tcr': 90.0,
    [](<#cb22-4>)    'accuracy': 85.0,
    [](<#cb22-5>)    'hallucination': 5.0,
    [](<#cb22-6>)    'latency': 3.0,
    [](<#cb22-7>)    'tool_selection_accuracy': 80.0
    [](<#cb22-8>)}
    [](<#cb22-9>)
    [](<#cb22-10>)# 여러 작업 평가 후 비교
    [](<#cb22-11>)comparison = monitor.compare_with_thresholds()
    [](<#cb22-12>)
    [](<#cb22-13>)for metric, result in comparison.items():
    [](<#cb22-14>)    status_emoji = "✅" if result['status'] == 'pass' else "❌"
    [](<#cb22-15>)    print(f"{status_emoji} {result['name']}: {result['value']}{result['unit']} (임계값: {result['threshold']}{result['unit']})")
    [](<#cb22-16>)
    [](<#cb22-17>)# 출력 예:
    [](<#cb22-18>)# ✅ 작업 완료율 (TCR): 95.5% (임계값: 90.0%)
    [](<#cb22-19>)# ✅ 정확도 (Accuracy): 88.2% (임계값: 85.0%)
    [](<#cb22-20>)# ❌ 환각률 (Hallucination): 7.3% (임계값: 5.0%)
    [](<#cb22-21>)# ✅ 도구 선택 정확도: 85.0% (임계값: 80.0%)
```

##### record_rag_metrics() (NEW)

RAG 평가 메트릭을 기록합니다.
```json
    [](<#cb_rag1-1>)record_rag_metrics(
    [](<#cb_rag1-2>)    faithfulness: Optional[float] = None,
    [](<#cb_rag1-3>)    answer_relevancy: Optional[float] = None,
    [](<#cb_rag1-4>)    context_recall: Optional[float] = None,
    [](<#cb_rag1-5>)    context_precision: Optional[float] = None
    [](<#cb_rag1-6>)) -> None
```

**파라미터**

  * `faithfulness` (float, optional): 충실도 점수 (0.0-1.0) 
    * 생성된 답변이 검색된 컨텍스트에 얼마나 충실한지 측정
    * 높을수록 환각(hallucination)이 적음
  * `answer_relevancy` (float, optional): 답변 관련성 점수 (0.0-1.0) 
    * 생성된 답변이 질문과 얼마나 관련있는지 측정
    * 높을수록 질문에 직접적으로 답변함
  * `context_recall` (float, optional): 컨텍스트 재현율 (0.0-1.0) 
    * 검색된 컨텍스트가 ground truth를 얼마나 포함하는지 측정
    * 높을수록 검색 품질이 좋음
  * `context_precision` (float, optional): 컨텍스트 정밀도 (0.0-1.0) 
    * 검색된 컨텍스트 중 관련있는 비율 측정
    * 높을수록 불필요한 컨텍스트가 적음

**설명**

  * korean_rag_evaluator.py의 KoreanRAGEvaluator와 함께 사용
  * 각 메트릭은 독립적으로 기록 가능 (일부만 제공 가능)
  * 내부적으로 `self.rag_metrics` 딕셔너리에 append
  * `compare_with_thresholds()`에서 평균값 계산

**예제**
```python
    [](<#cb_rag2-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb_rag2-2>)from korean_rag_evaluator import KoreanRAGEvaluator
    [](<#cb_rag2-3>)
    [](<#cb_rag2-4>)# 1. Monitor 및 RAG Evaluator 생성
    [](<#cb_rag2-5>)monitor = PerformanceMonitor()
    [](<#cb_rag2-6>)rag_evaluator = KoreanRAGEvaluator(rag_system=my_rag_system)
    [](<#cb_rag2-7>)
    [](<#cb_rag2-8>)# 2. RAG 시스템 평가
    [](<#cb_rag2-9>)result = rag_evaluator.evaluate_single(
    [](<#cb_rag2-10>)    question="한국의 수도는 어디인가요?",
    [](<#cb_rag2-11>)    expected_answer="서울입니다"
    [](<#cb_rag2-12>))
    [](<#cb_rag2-13>)
    [](<#cb_rag2-14>)# 3. RAG 메트릭 기록
    [](<#cb_rag2-15>)monitor.record_rag_metrics(
    [](<#cb_rag2-16>)    faithfulness=result.faithfulness,
    [](<#cb_rag2-17>)    answer_relevancy=result.answer_relevancy,
    [](<#cb_rag2-18>)    context_recall=result.context_recall,
    [](<#cb_rag2-19>)    context_precision=result.context_precision
    [](<#cb_rag2-20>))
    [](<#cb_rag2-21>)
    [](<#cb_rag2-22>)# 4. 일부 메트릭만 기록도 가능
    [](<#cb_rag2-23>)monitor.record_rag_metrics(
    [](<#cb_rag2-24>)    faithfulness=0.85,
    [](<#cb_rag2-25>)    answer_relevancy=0.92
    [](<#cb_rag2-26>)    # context_recall, context_precision은 생략
    [](<#cb_rag2-27>))
```

##### get_rag_metrics_summary() (NEW)

기록된 RAG 메트릭의 요약 통계를 반환합니다.
```json
    [](<#cb_rag3-1>)get_rag_metrics_summary() -> Dict[str, Any]
```

**반환값**

`dict`: 각 RAG 메트릭별 통계

  * 각 메트릭(faithfulness, answer_relevancy, context_recall, context_precision)마다: 
    * `avg` (float): 평균 값
    * `min` (float): 최소 값
    * `max` (float): 최대 값
    * `std` (float): 표준 편차
    * `count` (int): 기록된 횟수
  * 메트릭이 기록되지 않은 경우 모든 값이 0.0

**예제**
```python
    [](<#cb_rag4-1>)# RAG 메트릭 기록
    [](<#cb_rag4-2>)monitor.record_rag_metrics(faithfulness=0.85, answer_relevancy=0.90)
    [](<#cb_rag4-3>)monitor.record_rag_metrics(faithfulness=0.78, answer_relevancy=0.82)
    [](<#cb_rag4-4>)monitor.record_rag_metrics(faithfulness=0.92, answer_relevancy=0.88)
    [](<#cb_rag4-5>)
    [](<#cb_rag4-6>)# 요약 조회
    [](<#cb_rag4-7>)summary = monitor.get_rag_metrics_summary()
    [](<#cb_rag4-8>)
    [](<#cb_rag4-9>)print(summary["faithfulness"])
    [](<#cb_rag4-10>)# {
    [](<#cb_rag4-11>)#     'avg': 0.85,
    [](<#cb_rag4-12>)#     'min': 0.78,
    [](<#cb_rag4-13>)#     'max': 0.92,
    [](<#cb_rag4-14>)#     'std': 0.07,
    [](<#cb_rag4-15>)#     'count': 3
    [](<#cb_rag4-16>)# }
    [](<#cb_rag4-17>)
    [](<#cb_rag4-18>)# 모든 메트릭 출력
    [](<#cb_rag4-19>)for metric_name, stats in summary.items():
    [](<#cb_rag4-20>)    if stats["count"] > 0:
    [](<#cb_rag4-21>)        print(f"{metric_name}: avg={stats['avg']:.3f}, min={stats['min']:.3f}, max={stats['max']:.3f}")
```

##### compare_with_thresholds() - RAG 메트릭 지원 (UPDATED)

**기존 메서드에 RAG 메트릭 지원 추가됨**

**RAG 메트릭 처리 변경사항**

  * ❌ **이전** : RAG 메트릭이 항상 `value: 0.0`, `status: 'pending'`으로 반환
  * ✅ **현재** : 실제 기록된 메트릭의 평균값 계산, `status: 'pass'/'fail'` 판정

**RAG 임계값 설정 예제**
```python
    [](<#cb_rag5-1>)# 1. 임계값 설정
    [](<#cb_rag5-2>)monitor.thresholds = {
    [](<#cb_rag5-3>)    # Layer 1
    [](<#cb_rag5-4>)    "tcr": 90.0,
    [](<#cb_rag5-5>)    "accuracy": 85.0,
    [](<#cb_rag5-6>)    
    [](<#cb_rag5-7>)    # Layer 3: RAG (NEW)
    [](<#cb_rag5-8>)    "faithfulness": 0.8,
    [](<#cb_rag5-9>)    "answer_relevancy": 0.85,
    [](<#cb_rag5-10>)    "context_recall": 0.75,
    [](<#cb_rag5-11>)    "context_precision": 0.8
    [](<#cb_rag5-12>)}
    [](<#cb_rag5-13>)
    [](<#cb_rag5-14>)# 2. RAG 메트릭 기록 (여러 번)
    [](<#cb_rag5-15>)monitor.record_rag_metrics(faithfulness=0.85, answer_relevancy=0.88)
    [](<#cb_rag5-16>)monitor.record_rag_metrics(faithfulness=0.82, answer_relevancy=0.91)
    [](<#cb_rag5-17>)
    [](<#cb_rag5-18>)# 3. 임계값 비교
    [](<#cb_rag5-19>)comparison = monitor.compare_with_thresholds()
    [](<#cb_rag5-20>)
    [](<#cb_rag5-21>)print(comparison["faithfulness"])
    [](<#cb_rag5-22>)# {
    [](<#cb_rag5-23>)#     'name': 'Faithfulness',
    [](<#cb_rag5-24>)#     'value': 0.835,         # 실제 평균 값 (0.85 + 0.82) / 2
    [](<#cb_rag5-25>)#     'threshold': 0.8,
    [](<#cb_rag5-26>)#     'status': 'pass',       # 0.835 >= 0.8
    [](<#cb_rag5-27>)#     'direction': 'higher',
    [](<#cb_rag5-28>)#     'unit': ''
    [](<#cb_rag5-29>)# }
```

##### evaluate_with_golden_dataset()

Golden Dataset 기반 완전 자동 평가 파이프라인입니다. ✅ 100% 구현 완료 (2025-12-02)
```json
    [](<#cb23-1>)evaluate_with_golden_dataset(
    [](<#cb23-2>)    agent_fn: Callable,
    [](<#cb23-3>)    dataset_path: Optional[str] = None,
    [](<#cb23-4>)    enable_layer2_metrics: bool = True,
    [](<#cb23-5>)    enable_advanced_metrics: bool = False,
    [](<#cb23-6>)    verbose: bool = True
    [](<#cb23-7>)) -> Dict[str, Any]
```

**파라미터**

  * `agent_fn` (Callable): 평가할 에이전트 함수 
    * 입력: `question` (str)
    * 반환: Dict with keys: `answer`, `tools_used` (optional), `latency` (optional)
  * `dataset_path` (str, optional): Golden Dataset 파일 경로 
    * None이면 기존 로드된 dataset 사용
    * 상대 경로는 `golden_datasets/` 기준
  * `enable_layer2_metrics` (bool): Layer 2 메트릭 자동 평가 (기본값: True) 
    * Tool Selection Accuracy, F1 Score 자동 계산
    * Golden Dataset에 `expected_tools` 필드 필요
  * `enable_advanced_metrics` (bool): Layer 3 고급 메트릭 (기본값: False) 
    * DeepEval, Ragas 메트릭 통합 (향후 확장)
  * `verbose` (bool): 진행 상황 출력 (기본값: True)

**반환값**

  * `dict`: 평가 결과 요약 
    * `total_evaluated` (int): 평가한 항목 수
    * `layer1_metrics` (dict): 
      * `tcr` (float): 작업 완료율 (%)
      * `accuracy` (float): 정확도 (%) ✅ 자동 계산!
      * `hallucination_rate` (float): 환각 발생률 (%)
    * `layer2_metrics` (dict): 
      * `tool_selection_accuracy` (float): 도구 선택 정확도 (%) ✅ 자동 평가!
      * `tool_selection_f1` (float): 도구 선택 F1 Score (%)
    * `pass_fail` (dict): 임계값 비교 결과 (thresholds가 설정된 경우)

**기능**

  * ✅ Golden Dataset의 모든 QA 쌍에 대해 에이전트 자동 실행
  * ✅ Accuracy 자동 계산 (`ground_truth` 기반)
  * ✅ Layer 1 메트릭 자동 수집 (TCR, Latency, Token Usage 등)
  * ✅ Layer 2 메트릭 자동 평가 (Tool Selection Accuracy/F1)
  * ✅ 임계값 자동 비교 및 Pass/Fail 판정
  * ✅ 진행 상황 실시간 출력

**예제 1: 기본 사용**
```python
    [](<#cb24-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb24-2>)
    [](<#cb24-3>)# 1. Monitor 생성
    [](<#cb24-4>)monitor = PerformanceMonitor()
    [](<#cb24-5>)
    [](<#cb24-6>)# 2. 에이전트 함수 정의
    [](<#cb24-7>)def my_agent(question: str):
    [](<#cb24-8>)    """평가할 에이전트"""
    [](<#cb24-9>)    # LLM 호출 등 에이전트 로직
    [](<#cb24-10>)    answer = llm.predict(question)
    [](<#cb24-11>)    return {"answer": answer}
    [](<#cb24-12>)
    [](<#cb24-13>)# 3. 자동 평가 실행 (단 1줄!)
    [](<#cb24-14>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb24-15>)    agent_fn=my_agent,
    [](<#cb24-16>)    dataset_path="sample_dataset.json"
    [](<#cb24-17>))
    [](<#cb24-18>)
    [](<#cb24-19>)# 4. 결과 확인
    [](<#cb24-20>)print(f"총 평가: {results['total_evaluated']}개")
    [](<#cb24-21>)print(f"TCR: {results['layer1_metrics']['tcr']:.1f}%")
    [](<#cb24-22>)print(f"Accuracy: {results['layer1_metrics']['accuracy']:.1f}% (자동 계산!)")
```

**예제 2: Layer 2 메트릭 자동 평가**
```python
    [](<#cb25-1>)monitor = PerformanceMonitor()
    [](<#cb25-2>)
    [](<#cb25-3>)# 임계값 설정
    [](<#cb25-4>)monitor.thresholds = {
    [](<#cb25-5>)    'tcr': 90.0,
    [](<#cb25-6>)    'accuracy': 70.0,
    [](<#cb25-7>)    'tool_selection_accuracy': 75.0
    [](<#cb25-8>)}
    [](<#cb25-9>)
    [](<#cb25-10>)def my_agent(question: str):
    [](<#cb25-11>)    """도구 사용을 시뮬레이션하는 에이전트"""
    [](<#cb25-12>)    answer = llm.predict(question)
    [](<#cb25-13>)    tools_used = ["search", "calculator"]  # 실제 사용한 도구
    [](<#cb25-14>)    return {
    [](<#cb25-15>)        "answer": answer,
    [](<#cb25-16>)        "tools_used": tools_used
    [](<#cb25-17>)    }
    [](<#cb25-18>)
    [](<#cb25-19>)# Layer 2 메트릭 활성화
    [](<#cb25-20>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb25-21>)    agent_fn=my_agent,
    [](<#cb25-22>)    dataset_path="sample_dataset.json",
    [](<#cb25-23>)    enable_layer2_metrics=True  # ✅ Layer 2 활성화
    [](<#cb25-24>))
    [](<#cb25-25>)
    [](<#cb25-26>)# Layer 2 메트릭 확인
    [](<#cb25-27>)print(f"Tool Selection Accuracy: {results['layer2_metrics']['tool_selection_accuracy']:.1f}%")
    [](<#cb25-28>)print(f"Tool Selection F1: {results['layer2_metrics']['tool_selection_f1']:.1f}%")
    [](<#cb25-29>)
    [](<#cb25-30>)# 임계값 비교
    [](<#cb25-31>)for metric, data in results['pass_fail'].items():
    [](<#cb25-32>)    status = "✅" if data['status'] == 'pass' else "❌"
    [](<#cb25-33>)    print(f"{status} {data['name']}: {data['value']:.1f} (임계값: {data['threshold']})")
```

**주의사항**

  * Golden Dataset에 `ground_truth` 필드가 있어야 Accuracy 자동 계산
  * Golden Dataset에 `expected_tools` 필드가 있어야 Layer 2 평가 가능
  * 에이전트 함수는 반드시 `{"answer": "..."}` 형식으로 반환
  * Layer 2를 위해서는 `{"answer": "...", "tools_used": [...]}` 반환

**참고**

  * 완전 구현 예제: `Evaluator_Examples/10_improved_golden_dataset_auto_evaluation.py`
  * Enhanced Sample Dataset: `golden_datasets/sample_dataset.json`
  * 완료율: 100% (2025-12-02)

**활용 사례** \- CI/CD 파이프라인에서 품질 게이트 - 자동 평가 Pass/Fail 판정 - Dashboard에서 실시간 임계값 검증

* * *

### HybridPerformanceMonitor

고급 평가 메트릭(DeepEval, RAGAS)을 지원하는 하이브리드 모니터입니다.

`PerformanceMonitor`의 모든 기능을 포함하며, 추가 기능을 제공합니다.

#### 생성자
```json
    [](<#cb23-1>)HybridPerformanceMonitor(
    [](<#cb23-2>)    use_deepeval: bool = True,
    [](<#cb23-3>)    use_ragas: bool = True,
    [](<#cb23-4>)    use_langsmith: bool = False,
    [](<#cb23-5>)    deepeval_model: str = "gpt-4o-mini",
    [](<#cb23-6>)    ragas_model: str = "gpt-4o-mini",
    [](<#cb23-7>)    langsmith_api_key: Optional[str] = None
    [](<#cb23-8>))
```

**파라미터**

  * `use_deepeval` (bool): DeepEval 메트릭 활성화 (기본값: True)
  * `use_ragas` (bool): Ragas 메트릭 활성화 (기본값: True)
  * `use_langsmith` (bool): LangSmith 통합 활성화 (기본값: False)
  * `deepeval_model` (str): DeepEval에 사용할 모델 (기본값: "gpt-4o-mini")
  * `ragas_model` (str): Ragas에 사용할 모델 (기본값: "gpt-4o-mini")
  * `langsmith_api_key` (str, optional): LangSmith API 키

**예제**
```python
    [](<#cb24-1>)from agent_evaluator.hybrid_monitor import HybridPerformanceMonitor
    [](<#cb24-2>)
    [](<#cb24-3>)# 기본 생성 (DeepEval과 Ragas 모두 활성화)
    [](<#cb24-4>)monitor = HybridPerformanceMonitor()
    [](<#cb24-5>)
    [](<#cb24-6>)# DeepEval만 사용
    [](<#cb24-7>)monitor = HybridPerformanceMonitor(
    [](<#cb24-8>)    use_deepeval=True,
    [](<#cb24-9>)    use_ragas=False
    [](<#cb24-10>))
    [](<#cb24-11>)
    [](<#cb24-12>)# 커스텀 모델 지정
    [](<#cb24-13>)monitor = HybridPerformanceMonitor(
    [](<#cb24-14>)    use_deepeval=True,
    [](<#cb24-15>)    use_ragas=True,
    [](<#cb24-16>)    deepeval_model="gpt-4o",
    [](<#cb24-17>)    ragas_model="gpt-4o"
    [](<#cb24-18>))
    [](<#cb24-19>)
    [](<#cb24-20>)# LangSmith 통합
    [](<#cb24-21>)monitor = HybridPerformanceMonitor(
    [](<#cb24-22>)    use_langsmith=True,
    [](<#cb24-23>)    langsmith_api_key="your-api-key"
    [](<#cb24-24>))
```

#### 추가 메서드

##### record_task() [오버라이드]

고급 메트릭을 포함한 작업 기록.
```json
    [](<#cb25-1>)record_task(
    [](<#cb25-2>)    task: TaskResult,
    [](<#cb25-3>)    enable_advanced_metrics: bool = False,
    [](<#cb25-4>)    input_text: Optional[str] = None,
    [](<#cb25-5>)    output_text: Optional[str] = None,
    [](<#cb25-6>)    expected_output: Optional[str] = None,
    [](<#cb25-7>)    context: Optional[List[str]] = None,
    [](<#cb25-8>)    retrieved_context: Optional[List[str]] = None,
    [](<#cb25-9>)    quality_criteria: Optional[str] = None
    [](<#cb25-10>)) -> None
```

**파라미터** \- `task` (TaskResult): 기본 작업 결과 - `enable_advanced_metrics` (bool): 고급 메트릭 활성화 - `input_text` (str, optional): 입력 텍스트 - `output_text` (str, optional): 출력 텍스트 - `expected_output` (str, optional): 기대 출력 (Ground Truth) - `context` (list, optional): 컨텍스트 정보 - `retrieved_context` (list, optional): 검색된 컨텍스트 (RAG용) \- `quality_criteria` (str, optional): G-Eval 품질 기준

**예제**
```python
    [](<#cb26-1>)# 기본 메트릭만
    [](<#cb26-2>)monitor.record_task(task)
    [](<#cb26-3>)
    [](<#cb26-4>)# DeepEval G-Eval 포함
    [](<#cb26-5>)monitor.record_task(
    [](<#cb26-6>)    task,
    [](<#cb26-7>)    enable_advanced_metrics=True,
    [](<#cb26-8>)    input_text="What is the capital of France?",
    [](<#cb26-9>)    output_text="The capital of France is Paris.",
    [](<#cb26-10>)    expected_output="Paris",
    [](<#cb26-11>)    quality_criteria="Answer should be accurate and concise."
    [](<#cb26-12>))
    [](<#cb26-13>)
    [](<#cb26-14>)# RAGAS 포함 (RAG 시스템)
    [](<#cb26-15>)monitor.record_task(
    [](<#cb26-16>)    task,
    [](<#cb26-17>)    enable_advanced_metrics=True,
    [](<#cb26-18>)    input_text="What is the capital of France?",
    [](<#cb26-19>)    output_text="The capital of France is Paris.",
    [](<#cb26-20>)    expected_output="Paris",
    [](<#cb26-21>)    retrieved_context=[
    [](<#cb26-22>)        "Paris is the capital of France.",
    [](<#cb26-23>)        "France is located in Western Europe."
    [](<#cb26-24>)    ],
    [](<#cb26-25>)    quality_criteria="Answer should be based on retrieved context."
    [](<#cb26-26>))
```

##### generate_hybrid_report()

고급 메트릭을 포함한 하이브리드 리포트 생성.
```json
    [](<#cb27-1>)generate_hybrid_report(
    [](<#cb27-2>)    period: str = "전체 기간"
    [](<#cb27-3>)) -> HybridPerformanceReport
```

**반환값** \- `HybridPerformanceReport`: 하이브리드 리포트 (PerformanceReport 확장) - 모든 네이티브 메트릭 - `advanced_metrics_summary`: 고급 메트릭 요약 - `providers_used`: 사용된 프로바이더 목록

**예제**
```python
    [](<#cb28-1>)hybrid_report = monitor.generate_hybrid_report()
    [](<#cb28-2>)
    [](<#cb28-3>)# 네이티브 메트릭
    [](<#cb28-4>)print(f"TCR: {hybrid_report.tcr:.1f}%")
    [](<#cb28-5>)
    [](<#cb28-6>)# 고급 메트릭
    [](<#cb28-7>)if 'g_eval_score' in hybrid_report.advanced_metrics_summary:
    [](<#cb28-8>)    g_eval = hybrid_report.advanced_metrics_summary['g_eval_score']
    [](<#cb28-9>)    print(f"G-Eval: {g_eval['mean']:.3f}")
    [](<#cb28-10>)
    [](<#cb28-11>)if 'ragas_faithfulness' in hybrid_report.advanced_metrics_summary:
    [](<#cb28-12>)    faith = hybrid_report.advanced_metrics_summary['ragas_faithfulness']
    [](<#cb28-13>)    print(f"Faithfulness: {faith['mean']:.3f}")
```

##### create_monitor() [헬퍼 함수]

프로파일 기반 모니터 생성.
```python
    [](<#cb29-1>)from hybrid_monitor import create_monitor
    [](<#cb29-2>)
    [](<#cb29-3>)monitor = create_monitor(
    [](<#cb29-4>)    profile: str = "balanced",
    [](<#cb29-5>)    pricing: Optional[Dict[str, float]] = None,
    [](<#cb29-6>)    thresholds: Optional[Dict[str, float]] = None
    [](<#cb29-7>)) -> HybridPerformanceMonitor
```

**파라미터** \- `profile` (str): 프로파일 선택 \- `"minimal"`: 네이티브 메트릭만 (무료) - `"balanced"`: DeepEval 포함 (권장) - `"rag"`: DeepEval + RAGAS - `"full"`: 모든 메트릭

**예제**
```json
    [](<#cb30-1>)# 권장 설정
    [](<#cb30-2>)monitor = create_monitor(profile="balanced")
    [](<#cb30-3>)
    [](<#cb30-4>)# RAG 시스템용
    [](<#cb30-5>)monitor = create_monitor(profile="rag")
    [](<#cb30-6>)
    [](<#cb30-7>)# 모든 기능
    [](<#cb30-8>)monitor = create_monitor(profile="full")
```

* * *

### TaskResult

작업 결과를 나타내는 데이터 클래스입니다.

#### 생성자
```python
    [](<#cb31-1>)@dataclass
    [](<#cb31-2>)class TaskResult:
    [](<#cb31-3>)    # 필수 필드 (Layer 1)
    [](<#cb31-4>)    task_id: str
    [](<#cb31-5>)    task_type: str
    [](<#cb31-6>)    success: bool
    [](<#cb31-7>)    completion_score: float
    [](<#cb31-8>)    accuracy_score: float
    [](<#cb31-9>)    execution_time: float
    [](<#cb31-10>)    tokens_used: Dict[str, int]
    [](<#cb31-11>)    tool_calls: List[Dict[str, Any]]  # ⚠️ List[str]이 아님!
    [](<#cb31-12>)    attempts: int
    [](<#cb31-13>)    errors: List[str]
    [](<#cb31-14>)    timestamp: datetime
    [](<#cb31-15>)
    [](<#cb31-16>)    # 선택적 필드 (Layer 2: Agentic AI)
    [](<#cb31-17>)    agent_interactions: Optional[List[Dict[str, Any]]] = None
    [](<#cb31-18>)    chain_steps: Optional[List[Dict[str, Any]]] = None
    [](<#cb31-19>)    graph_traversal: Optional[Dict[str, Any]] = None
    [](<#cb31-20>)    conversation_turns: Optional[List[Dict[str, Any]]] = None
    [](<#cb31-21>)    expected_tools: Optional[List[str]] = None
    [](<#cb31-22>)    state_transitions: Optional[List[Dict[str, Any]]] = None
    [](<#cb31-23>)    framework: Optional[str] = None
```

**필드 설명**

필드 | 타입 | 설명 | 필수 | Layer  
---|---|---|---|---  
`task_id` | str | 작업 고유 ID | ✅ | 1  
`task_type` | str | 작업 유형 (TaskType.*.value) | ✅ | 1  
`success` | bool | 성공 여부 | ✅ | 1  
`completion_score` | float | 완료 점수 (0.0~1.0) | ✅ | 1  
`accuracy_score` | float | 정확도 점수 (0.0~1.0) | ✅ | 1  
`execution_time` | float | 실행 시간 (초) | ✅ | 1  
`tokens_used` | Dict[str, int] | 토큰 사용량 | ✅ | 1  
`tool_calls` | List[Dict[str, Any]] | 사용된 도구 목록 (딕셔너리 리스트) | ✅ | 1  
`attempts` | int | 시도 횟수 | ✅ | 1  
`errors` | List[str] | 오류 메시지 목록 | ✅ | 1  
`timestamp` | datetime | 타임스탬프 | ✅ | 1  
`agent_interactions` | List[Dict] | 멀티 에이전트 상호작용 (CrewAI) | ❌ | 2  
`chain_steps` | List[Dict] | 체인 실행 단계 (LangChain) | ❌ | 2  
`graph_traversal` | Dict | 그래프 순회 경로 (LangGraph) | ❌ | 2  
`conversation_turns` | List[Dict] | 대화 턴 (AutoGen) | ❌ | 2  
`expected_tools` | List[str] | 예상 도구 목록 (Golden Dataset) | ❌ | 2  
`state_transitions` | List[Dict] | 상태 전환 (LangGraph) | ❌ | 2  
`framework` | str | 사용 프레임워크 (crewai, langchain, langgraph, autogen) | ❌ | 2  
  
**tokens_used 구조**
```json
    [](<#cb32-1>){
    [](<#cb32-2>)    "input": 150,    # 입력 토큰 수
    [](<#cb32-3>)    "output": 200,   # 출력 토큰 수
    [](<#cb32-4>)    "total": 350     # 총 토큰 수
    [](<#cb32-5>)}
```

**tool_calls 구조** (⚠️ 중요)
```json
    [](<#cb33-1>)# 올바른 형식: List[Dict[str, Any]]
    [](<#cb33-2>)tool_calls = [
    [](<#cb33-3>)    {
    [](<#cb33-4>)        "tool_name": "search",  # 또는 "tool" 또는 "name"
    [](<#cb33-5>)        "success": True,
    [](<#cb33-6>)        "duration": 0.5,
    [](<#cb33-7>)        "parameters": {"query": "Python tutorial"}
    [](<#cb33-8>)    },
    [](<#cb33-9>)    {
    [](<#cb33-10>)        "tool_name": "calculator",
    [](<#cb33-11>)        "success": True,
    [](<#cb33-12>)        "duration": 0.1
    [](<#cb33-13>)    }
    [](<#cb33-14>)]
    [](<#cb33-15>)
    [](<#cb33-16>)# ❌ 잘못된 형식: List[str]
    [](<#cb33-17>)# tool_calls = ["search", "calculator"]  # 이것은 작동하지 않습니다!
```

**Layer 2 필드 사용 예제**
```json
    [](<#cb34-1>)# CrewAI: agent_interactions
    [](<#cb34-2>)agent_interactions = [
    [](<#cb34-3>)    {
    [](<#cb34-4>)        "from_agent": "manager",
    [](<#cb34-5>)        "to_agent": "researcher",
    [](<#cb34-6>)        "type": "delegation",  # delegation, communication, collaboration
    [](<#cb34-7>)        "success": True,
    [](<#cb34-8>)        "context": {"task": "market_research"}
    [](<#cb34-9>)    }
    [](<#cb34-10>)]
    [](<#cb34-11>)
    [](<#cb34-12>)# LangChain: chain_steps
    [](<#cb34-13>)chain_steps = [
    [](<#cb34-14>)    {
    [](<#cb34-15>)        "name": "retrieval",
    [](<#cb34-16>)        "type": "chain_step",
    [](<#cb34-17>)        "success": True,
    [](<#cb34-18>)        "execution_time": 0.8,
    [](<#cb34-19>)        "metadata": {"docs_retrieved": 5}
    [](<#cb34-20>)    }
    [](<#cb34-21>)]
    [](<#cb34-22>)
    [](<#cb34-23>)# LangGraph: graph_traversal
    [](<#cb34-24>)graph_traversal = {
    [](<#cb34-25>)    "nodes_visited": ["start", "agent_decision", "tool_call", "end"],
    [](<#cb34-26>)    "edges_taken": 3
    [](<#cb34-27>)}
    [](<#cb34-28>)
    [](<#cb34-29>)# Golden Dataset: expected_tools
    [](<#cb34-30>)expected_tools = ["web_search", "calculator", "python_repl"]
```

**예제**
```python
    [](<#cb35-1>)from agent_evaluator import TaskResult, TaskType
    [](<#cb35-2>)from datetime import datetime
    [](<#cb35-3>)
    [](<#cb35-4>)# 기본 케이스 (Layer 1만)
    [](<#cb35-5>)task = TaskResult(
    [](<#cb35-6>)    task_id="qa_001",
    [](<#cb35-7>)    task_type=TaskType.QA.value,
    [](<#cb35-8>)    success=True,
    [](<#cb35-9>)    completion_score=1.0,
    [](<#cb35-10>)    accuracy_score=0.95,
    [](<#cb35-11>)    execution_time=1.2,
    [](<#cb35-12>)    tokens_used={"input": 100, "output": 150, "total": 250},
    [](<#cb35-13>)    tool_calls=[
    [](<#cb35-14>)        {"tool_name": "search", "success": True, "duration": 0.5}
    [](<#cb35-15>)    ],  # ⚠️ Dict 리스트!
    [](<#cb35-16>)    attempts=1,
    [](<#cb35-17>)    errors=[],
    [](<#cb35-18>)    timestamp=datetime.now()
    [](<#cb35-19>))
    [](<#cb35-20>)
    [](<#cb35-21>)# Layer 2 포함 (Tool Selection 평가)
    [](<#cb35-22>)task_with_tools = TaskResult(
    [](<#cb35-23>)    task_id="qa_002",
    [](<#cb35-24>)    task_type=TaskType.QA.value,
    [](<#cb35-25>)    success=True,
    [](<#cb35-26>)    completion_score=1.0,
    [](<#cb35-27>)    accuracy_score=0.90,
    [](<#cb35-28>)    execution_time=2.3,
    [](<#cb35-29>)    tokens_used={"input": 200, "output": 300, "total": 500},
    [](<#cb35-30>)    tool_calls=[
    [](<#cb35-31>)        {"tool_name": "web_search", "success": True},
    [](<#cb35-32>)        {"tool_name": "calculator", "success": True}
    [](<#cb35-33>)    ],
    [](<#cb35-34>)    attempts=1,
    [](<#cb35-35>)    errors=[],
    [](<#cb35-36>)    timestamp=datetime.now(),
    [](<#cb35-37>)    # Layer 2 필드
    [](<#cb35-38>)    expected_tools=["web_search", "calculator", "python_repl"],  # Golden Dataset에서 정의
    [](<#cb35-39>)    framework="langchain"
    [](<#cb35-40>))
    [](<#cb35-41>)
    [](<#cb35-42>)# Layer 2 포함 (Agent Coordination)
    [](<#cb35-43>)task_with_agents = TaskResult(
    [](<#cb35-44>)    task_id="qa_003",
    [](<#cb35-45>)    task_type=TaskType.PLANNING.value,
    [](<#cb35-46>)    success=True,
    [](<#cb35-47>)    completion_score=1.0,
    [](<#cb35-48>)    accuracy_score=0.92,
    [](<#cb35-49>)    execution_time=5.8,
    [](<#cb35-50>)    tokens_used={"input": 500, "output": 800, "total": 1300},
    [](<#cb35-51>)    tool_calls=[{"tool_name": "task_scheduler", "success": True}],
    [](<#cb35-52>)    attempts=1,
    [](<#cb35-53>)    errors=[],
    [](<#cb35-54>)    timestamp=datetime.now(),
    [](<#cb35-55>)    # CrewAI 에이전트 상호작용
    [](<#cb35-56>)    agent_interactions=[
    [](<#cb35-57>)        {
    [](<#cb35-58>)            "from_agent": "manager",
    [](<#cb35-59>)            "to_agent": "researcher",
    [](<#cb35-60>)            "type": "delegation",
    [](<#cb35-61>)            "success": True
    [](<#cb35-62>)        },
    [](<#cb35-63>)        {
    [](<#cb35-64>)            "from_agent": "researcher",
    [](<#cb35-65>)            "to_agent": "writer",
    [](<#cb35-66>)            "type": "collaboration",
    [](<#cb35-67>)            "success": True
    [](<#cb35-68>)        }
    [](<#cb35-69>)    ],
    [](<#cb35-70>)    framework="crewai"
    [](<#cb35-71>))
    [](<#cb35-72>)
    [](<#cb35-73>)# 실패 케이스
    [](<#cb35-74>)task_failed = TaskResult(
    [](<#cb35-75>)    task_id="qa_004",
    [](<#cb35-76>)    task_type=TaskType.QA.value,
    [](<#cb35-77>)    success=False,
    [](<#cb35-78>)    completion_score=0.0,
    [](<#cb35-79>)    accuracy_score=0.0,
    [](<#cb35-80>)    execution_time=0.5,
    [](<#cb35-81>)    tokens_used={"input": 50, "output": 0, "total": 50},
    [](<#cb35-82>)    tool_calls=[],  # 빈 리스트
    [](<#cb35-83>)    attempts=3,
    [](<#cb35-84>)    errors=["API timeout", "Rate limit exceeded"],
    [](<#cb35-85>)    timestamp=datetime.now()
    [](<#cb35-86>))
```

* * *

### TaskType

작업 유형을 나타내는 Enum 클래스입니다.

#### 사용 가능한 타입
```python
    [](<#cb36-1>)from enum import Enum
    [](<#cb36-2>)
    [](<#cb36-3>)class TaskType(Enum):
    [](<#cb36-4>)    QA = "qa"                              # 질의응답
    [](<#cb36-5>)    DATA_ANALYSIS = "data_analysis"        # 데이터 분석
    [](<#cb36-6>)    CODE_GENERATION = "code_generation"    # 코드 생성
    [](<#cb36-7>)    DOCUMENT_CREATION = "document_creation"  # 문서 작성
    [](<#cb36-8>)    INFORMATION_RETRIEVAL = "information_retrieval"  # 정보 검색
    [](<#cb36-9>)    REASONING = "reasoning"                # 추론
    [](<#cb36-10>)    CREATIVE = "creative"                  # 창의적 작업
    [](<#cb36-11>)    CODING = "coding"                      # 코딩
    [](<#cb36-12>)    PLANNING = "planning"                  # 계획 수립
    [](<#cb36-13>)    TOOL_USE = "tool_use"                 # 도구 사용
```

**사용법**
```python
    [](<#cb37-1>)from agent_evaluator import TaskType
    [](<#cb37-2>)
    [](<#cb37-3>)# Enum 값 사용 (권장)
    [](<#cb37-4>)task = TaskResult(
    [](<#cb37-5>)    task_type=TaskType.QA.value,
    [](<#cb37-6>)    # ...
    [](<#cb37-7>))
    [](<#cb37-8>)
    [](<#cb37-9>)# 문자열 직접 사용
    [](<#cb37-10>)task = TaskResult(
    [](<#cb37-11>)    task_type="qa",
    [](<#cb37-12>)    # ...
    [](<#cb37-13>))
    [](<#cb37-14>)
    [](<#cb37-15>)# 작업 유형별 특징
    [](<#cb37-16>)task_characteristics = {
    [](<#cb37-17>)    TaskType.QA: "높은 정확도 필요",
    [](<#cb37-18>)    TaskType.CREATIVE: "유연한 평가 기준",
    [](<#cb37-19>)    TaskType.CODE_GENERATION: "실행 가능성 중요",
    [](<#cb37-20>)    TaskType.INFORMATION_RETRIEVAL: "재현율 중요"
    [](<#cb37-21>)}
```

* * *

## 1.5. Layer 2: Agentic AI Metrics

Layer 2 메트릭은 멀티 에이전트 AI 시스템의 고급 성능을 평가합니다. `PerformanceMonitor`는 다음 4가지 Layer 2 트래커를 포함합니다:

  * **ToolSelectionTracker** : 에이전트의 도구 선택 정확도 평가
  * **ToolEfficiencyTracker** : 도구 사용 효율성 및 성공률 측정
  * **AgentCoordinationTracker** : 멀티 에이전트 협업 품질 측정
  * **WorkflowExecutionTracker** : LangChain/LangGraph 워크플로우 실행 추적

### 1.5.1. ToolSelectionTracker

에이전트가 작업에 적합한 도구를 선택했는지 평가합니다.

#### 접근 방법
```python
    [](<#cb38-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb38-2>)
    [](<#cb38-3>)monitor = PerformanceMonitor()
    [](<#cb38-4>)tracker = monitor.tool_selection_tracker  # ToolSelectionTracker 인스턴스
```

#### evaluate_selection()

에이전트의 도구 선택을 평가하고 정확도 메트릭을 계산합니다.
```json
    [](<#cb39-1>)evaluate_selection(
    [](<#cb39-2>)    task_id: str,
    [](<#cb39-3>)    expected_tools: List[str],
    [](<#cb39-4>)    actual_tools: List[str]
    [](<#cb39-5>)) -> Dict[str, Any]
```

**파라미터** \- `task_id` (str): 작업 고유 ID \- `expected_tools` (List[str]): 작업에 필요한 도구 목록 (Golden Dataset에서 정의) - `actual_tools` (List[str]): 에이전트가 실제로 사용한 도구 목록

**반환값** \- `dict`: 평가 결과 - `task_id` (str): 작업 ID - `expected_tools` (List[str]): 예상 도구 목록 - `actual_tools` (List[str]): 실제 사용 도구 목록 - `true_positives` (int): 올바르게 선택한 도구 수 - `false_positives` (int): 불필요하게 선택한 도구 수 \- `false_negatives` (int): 선택하지 않은 필요 도구 수 - `precision` (float): 정밀도 (0-100) - `recall` (float): 재현율 (0-100) - `f1_score` (float): F1 점수 (0-100) \- `accuracy` (float): 전체 정확도 (F1 기준, 0-100)

**예제**
```python
    [](<#cb40-1>)# Golden Dataset에서 expected_tools 정의
    [](<#cb40-2>)result = monitor.tool_selection_tracker.evaluate_selection(
    [](<#cb40-3>)    task_id="task_001",
    [](<#cb40-4>)    expected_tools=["web_search", "calculator", "python_repl"],
    [](<#cb40-5>)    actual_tools=["web_search", "calculator"]  # python_repl 누락
    [](<#cb40-6>))
    [](<#cb40-7>)
    [](<#cb40-8>)print(f"도구 선택 정확도: {result['accuracy']}%")
    [](<#cb40-9>)print(f"정밀도: {result['precision']}%, 재현율: {result['recall']}%")
    [](<#cb40-10>)print(f"F1 Score: {result['f1_score']}%")
    [](<#cb40-11>)
    [](<#cb40-12>)# 출력:
    [](<#cb40-13>)# 도구 선택 정확도: 80.0%
    [](<#cb40-14>)# 정밀도: 100.0%, 재현율: 66.67%
    [](<#cb40-15>)# F1 Score: 80.0%
```

**사용 시나리오** \- LangChain 에이전트가 올바른 도구를 선택했는지 검증 - Golden Dataset 기반 자동 평가 - 도구 선택 최적화

#### get_accuracy_stats()

전체 평가 세션의 도구 선택 통계를 반환합니다.
```json
    [](<#cb41-1>)get_accuracy_stats() -> Dict[str, Any]
```

**반환값** \- `dict`: 통계 정보 - `total_evaluations` (int): 총 평가 횟수 - `avg_accuracy` (float): 평균 정확도 - `avg_precision` (float): 평균 정밀도 - `avg_recall` (float): 평균 재현율 - `avg_f1_score` (float): 평균 F1 점수 - `total_true_positives` (int): 총 True Positive 수 - `total_false_positives` (int): 총 False Positive 수 - `total_false_negatives` (int): 총 False Negative 수

**예제**
```python
    [](<#cb42-1>)# 여러 작업 평가 후 통계 확인
    [](<#cb42-2>)for task in tasks:
    [](<#cb42-3>)    monitor.tool_selection_tracker.evaluate_selection(
    [](<#cb42-4>)        task_id=task.id,
    [](<#cb42-5>)        expected_tools=task.expected_tools,
    [](<#cb42-6>)        actual_tools=task.actual_tools
    [](<#cb42-7>)    )
    [](<#cb42-8>)
    [](<#cb42-9>)# 전체 통계
    [](<#cb42-10>)stats = monitor.tool_selection_tracker.get_accuracy_stats()
    [](<#cb42-11>)print(f"총 {stats['total_evaluations']}개 작업 평가")
    [](<#cb42-12>)print(f"평균 정확도: {stats['avg_accuracy']}%")
    [](<#cb42-13>)print(f"평균 F1 Score: {stats['avg_f1_score']}%")
```

* * *

### 1.5.2. AgentCoordinationTracker

멀티 에이전트 시스템에서 에이전트 간 협업 품질을 추적합니다.

#### 접근 방법
```python
    [](<#cb43-1>)monitor = PerformanceMonitor()
    [](<#cb43-2>)tracker = monitor.agent_coordination_tracker  # AgentCoordinationTracker 인스턴스
```

#### track_interaction()

에이전트 간 상호작용(위임, 통신, 협업)을 기록합니다.
```json
    [](<#cb44-1>)track_interaction(
    [](<#cb44-2>)    task_id: str,
    [](<#cb44-3>)    from_agent: str,
    [](<#cb44-4>)    to_agent: str,
    [](<#cb44-5>)    interaction_type: str,
    [](<#cb44-6>)    success: bool,
    [](<#cb44-7>)    context: Optional[Dict[str, Any]] = None
    [](<#cb44-8>)) -> Dict[str, Any]
```

**파라미터** \- `task_id` (str): 작업 고유 ID \- `from_agent` (str): 상호작용을 시작한 에이전트 이름 - `to_agent` (str): 상호작용 대상 에이전트 이름 - `interaction_type` (str): 상호작용 유형 - `"delegation"`: 작업 위임 - `"communication"`: 정보 전달 - `"collaboration"`: 협업 작업 - `success` (bool): 상호작용 성공 여부 - `context` (dict, optional): 추가 컨텍스트 정보

**반환값** \- `dict`: 상호작용 기록 - `task_id` (str): 작업 ID - `from_agent` (str): 출발 에이전트 - `to_agent` (str): 도착 에이전트 - `interaction_type` (str): 상호작용 유형 - `success` (bool): 성공 여부 - `timestamp` (datetime): 기록 시각 - `context` (dict): 컨텍스트 정보

**예제**
```python
    [](<#cb45-1>)# CrewAI에서 Manager가 Researcher에게 작업 위임
    [](<#cb45-2>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb45-3>)    task_id="task_001",
    [](<#cb45-4>)    from_agent="manager",
    [](<#cb45-5>)    to_agent="researcher",
    [](<#cb45-6>)    interaction_type="delegation",
    [](<#cb45-7>)    success=True,
    [](<#cb45-8>)    context={"task": "market_research", "priority": "high"}
    [](<#cb45-9>))
    [](<#cb45-10>)
    [](<#cb45-11>)# Researcher가 Writer와 협업
    [](<#cb45-12>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb45-13>)    task_id="task_001",
    [](<#cb45-14>)    from_agent="researcher",
    [](<#cb45-15>)    to_agent="writer",
    [](<#cb45-16>)    interaction_type="collaboration",
    [](<#cb45-17>)    success=True,
    [](<#cb45-18>)    context={"shared_data": "research_findings"}
    [](<#cb45-19>))
```

#### calculate_coordination_score()

에이전트 협업 품질 점수를 계산합니다 (0-10 척도).
```json
    [](<#cb46-1>)calculate_coordination_score(
    [](<#cb46-2>)    task_id: Optional[str] = None
    [](<#cb46-3>)) -> Dict[str, Any]
```

**파라미터** \- `task_id` (str, optional): 특정 작업의 점수만 계산 (None이면 전체)

**반환값** \- `dict`: 협업 점수 - `score` (float): 협업 품질 점수 (0-10) - `success_rate` (float): 성공률 (%) - `total_interactions` (int): 총 상호작용 수 - `unique_agents` (int): 참여 에이전트 수 - `interaction_types` (dict): 상호작용 유형별 횟수

**점수 계산 방식** \- 50% 성공률 - 30% 에이전트 다양성 (5+ 에이전트 = 이상적) - 20% 상호작용 유형 균형 (3가지 유형 = 이상적)

**예제**
```python
    [](<#cb47-1>)# 여러 상호작용 추적 후 점수 계산
    [](<#cb47-2>)score_data = monitor.agent_coordination_tracker.calculate_coordination_score(
    [](<#cb47-3>)    task_id="task_001"
    [](<#cb47-4>))
    [](<#cb47-5>)
    [](<#cb47-6>)print(f"협업 점수: {score_data['score']}/10")
    [](<#cb47-7>)print(f"성공률: {score_data['success_rate']}%")
    [](<#cb47-8>)print(f"참여 에이전트: {score_data['unique_agents']}명")
    [](<#cb47-9>)print(f"상호작용 유형: {score_data['interaction_types']}")
    [](<#cb47-10>)
    [](<#cb47-11>)# 출력:
    [](<#cb47-12>)# 협업 점수: 7.8/10
    [](<#cb47-13>)# 성공률: 95.0%
    [](<#cb47-14>)# 참여 에이전트: 4명
    [](<#cb47-15>)# 상호작용 유형: {'delegation': 5, 'communication': 8, 'collaboration': 3}
```

#### get_delegation_success_rate()

작업 위임 성공률을 계산합니다.
```json
    [](<#cb48-1>)get_delegation_success_rate() -> float
```

**반환값** \- `float`: 위임 성공률 (0-100)

**예제**
```python
    [](<#cb49-1>)delegation_rate = monitor.agent_coordination_tracker.get_delegation_success_rate()
    [](<#cb49-2>)print(f"작업 위임 성공률: {delegation_rate}%")
```

* * *

### 1.5.3. WorkflowExecutionTracker

LangChain 체인 및 LangGraph 워크플로우의 실행을 추적합니다.

#### 접근 방법
```python
    [](<#cb50-1>)monitor = PerformanceMonitor()
    [](<#cb50-2>)tracker = monitor.workflow_tracker  # WorkflowExecutionTracker 인스턴스
```

#### track_step()

워크플로우의 개별 단계 실행을 기록합니다.
```json
    [](<#cb51-1>)track_step(
    [](<#cb51-2>)    task_id: str,
    [](<#cb51-3>)    step_name: str,
    [](<#cb51-4>)    step_type: str,
    [](<#cb51-5>)    success: bool,
    [](<#cb51-6>)    execution_time: float,
    [](<#cb51-7>)    framework: str = "langchain",
    [](<#cb51-8>)    metadata: Optional[Dict[str, Any]] = None
    [](<#cb51-9>)) -> Dict[str, Any]
```

**파라미터** \- `task_id` (str): 작업 고유 ID \- `step_name` (str): 단계 이름 - `step_type` (str): 단계 유형 - `"chain_step"`: LangChain 체인 단계 - `"node"`: LangGraph 노드 - `"edge"`: LangGraph 엣지 - `"branch"`: 분기 로직 - `success` (bool): 단계 실행 성공 여부 - `execution_time` (float): 실행 시간 (초) - `framework` (str): 프레임워크 (“langchain” 또는 “langgraph”) - `metadata` (dict, optional): 추가 메타데이터

**반환값** \- `dict`: 단계 실행 기록 - `task_id` (str): 작업 ID - `step_name` (str): 단계 이름 - `step_type` (str): 단계 유형 - `success` (bool): 성공 여부 - `execution_time` (float): 실행 시간 - `framework` (str): 프레임워크 - `timestamp` (datetime): 기록 시각 - `metadata` (dict): 메타데이터

**예제**
```python
    [](<#cb52-1>)# LangChain 체인 단계 추적
    [](<#cb52-2>)monitor.workflow_tracker.track_step(
    [](<#cb52-3>)    task_id="task_001",
    [](<#cb52-4>)    step_name="retrieval",
    [](<#cb52-5>)    step_type="chain_step",
    [](<#cb52-6>)    success=True,
    [](<#cb52-7>)    execution_time=0.85,
    [](<#cb52-8>)    framework="langchain",
    [](<#cb52-9>)    metadata={"retrieved_docs": 5}
    [](<#cb52-10>))
    [](<#cb52-11>)
    [](<#cb52-12>)# LangGraph 노드 추적
    [](<#cb52-13>)monitor.workflow_tracker.track_step(
    [](<#cb52-14>)    task_id="task_002",
    [](<#cb52-15>)    step_name="agent_decision",
    [](<#cb52-16>)    step_type="node",
    [](<#cb52-17>)    success=True,
    [](<#cb52-18>)    execution_time=1.2,
    [](<#cb52-19>)    framework="langgraph",
    [](<#cb52-20>)    metadata={"node_id": "decision_node_1"}
    [](<#cb52-21>))
```

#### calculate_execution_success_rate()

워크플로우 실행 성공률을 계산합니다.
```json
    [](<#cb53-1>)calculate_execution_success_rate(
    [](<#cb53-2>)    task_id: Optional[str] = None,
    [](<#cb53-3>)    framework: Optional[str] = None
    [](<#cb53-4>)) -> Dict[str, Any]
```

**파라미터** \- `task_id` (str, optional): 특정 작업으로 필터링 - `framework` (str, optional): 특정 프레임워크로 필터링

**반환값** \- `dict`: 실행 통계 - `step_success_rate` (float): 단계별 성공률 (%) - `total_steps` (int): 총 단계 수 - `successful_steps` (int): 성공한 단계 수 - `failed_steps` (int): 실패한 단계 수 - `total_tasks` (int): 총 작업 수 - `fully_successful_tasks` (int): 전체 단계 성공한 작업 수 - `task_success_rate` (float): 작업 성공률 (%) - `avg_steps_per_task` (float): 작업당 평균 단계 수

**예제**
```python
    [](<#cb54-1>)# LangChain 워크플로우 성공률
    [](<#cb54-2>)stats = monitor.workflow_tracker.calculate_execution_success_rate(
    [](<#cb54-3>)    framework="langchain"
    [](<#cb54-4>))
    [](<#cb54-5>)
    [](<#cb54-6>)print(f"단계 성공률: {stats['step_success_rate']}%")
    [](<#cb54-7>)print(f"작업 성공률: {stats['task_success_rate']}%")
    [](<#cb54-8>)print(f"총 {stats['total_tasks']}개 작업, {stats['total_steps']}개 단계")
    [](<#cb54-9>)print(f"작업당 평균 {stats['avg_steps_per_task']}개 단계")
    [](<#cb54-10>)
    [](<#cb54-11>)# 출력:
    [](<#cb54-12>)# 단계 성공률: 95.5%
    [](<#cb54-13>)# 작업 성공률: 87.5%
    [](<#cb54-14>)# 총 8개 작업, 44개 단계
    [](<#cb54-15>)# 작업당 평균 5.5개 단계
```

#### get_graph_traversal_efficiency()

LangGraph 그래프 순회 효율성을 계산합니다.
```json
    [](<#cb55-1>)get_graph_traversal_efficiency(
    [](<#cb55-2>)    task_id: str
    [](<#cb55-3>)) -> Dict[str, Any]
```

**파라미터** \- `task_id` (str): 작업 고유 ID

**반환값** \- `dict`: 순회 효율성 - `efficiency` (float): 효율성 점수 (%) - `total_steps` (int): 총 단계 수 - `nodes_executed` (int): 실행된 노드 수 - `branches_taken` (int): 분기 횟수 - `successful_nodes` (int): 성공한 노드 수 - `avg_node_time` (float): 평균 노드 실행 시간 (초)

**효율성 계산** \- 효율성 = (성공한 노드 수 / 총 단계 수) × 100

**예제**
```python
    [](<#cb56-1>)# LangGraph 작업의 그래프 순회 효율성
    [](<#cb56-2>)efficiency = monitor.workflow_tracker.get_graph_traversal_efficiency(
    [](<#cb56-3>)    task_id="task_002"
    [](<#cb56-4>))
    [](<#cb56-5>)
    [](<#cb56-6>)print(f"그래프 순회 효율성: {efficiency['efficiency']}%")
    [](<#cb56-7>)print(f"실행 노드: {efficiency['nodes_executed']}개")
    [](<#cb56-8>)print(f"분기 횟수: {efficiency['branches_taken']}회")
    [](<#cb56-9>)print(f"평균 노드 시간: {efficiency['avg_node_time']}초")
```

* * *

### 1.5.4. Layer 2 워크플로우 예제

#### 전체 Layer 2 메트릭 통합 예제
```python
    [](<#cb57-1>)from agent_evaluator import PerformanceMonitor, TaskResult, TaskType
    [](<#cb57-2>)from datetime import datetime
    [](<#cb57-3>)
    [](<#cb57-4>)# Monitor 생성
    [](<#cb57-5>)monitor = PerformanceMonitor()
    [](<#cb57-6>)
    [](<#cb57-7>)# 1. Tool Selection 평가 (LangChain)
    [](<#cb57-8>)monitor.tool_selection_tracker.evaluate_selection(
    [](<#cb57-9>)    task_id="qa_task_001",
    [](<#cb57-10>)    expected_tools=["web_search", "calculator"],
    [](<#cb57-11>)    actual_tools=["web_search", "calculator", "python_repl"]
    [](<#cb57-12>))
    [](<#cb57-13>)
    [](<#cb57-14>)# 2. Agent Coordination 추적 (CrewAI)
    [](<#cb57-15>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb57-16>)    task_id="qa_task_001",
    [](<#cb57-17>)    from_agent="manager",
    [](<#cb57-18>)    to_agent="researcher",
    [](<#cb57-19>)    interaction_type="delegation",
    [](<#cb57-20>)    success=True
    [](<#cb57-21>))
    [](<#cb57-22>)
    [](<#cb57-23>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb57-24>)    task_id="qa_task_001",
    [](<#cb57-25>)    from_agent="researcher",
    [](<#cb57-26>)    to_agent="writer",
    [](<#cb57-27>)    interaction_type="collaboration",
    [](<#cb57-28>)    success=True
    [](<#cb57-29>))
    [](<#cb57-30>)
    [](<#cb57-31>)# 3. Workflow Execution 추적 (LangGraph)
    [](<#cb57-32>)monitor.workflow_tracker.track_step(
    [](<#cb57-33>)    task_id="qa_task_001",
    [](<#cb57-34>)    step_name="retrieval",
    [](<#cb57-35>)    step_type="node",
    [](<#cb57-36>)    success=True,
    [](<#cb57-37>)    execution_time=0.8,
    [](<#cb57-38>)    framework="langgraph"
    [](<#cb57-39>))
    [](<#cb57-40>)
    [](<#cb57-41>)monitor.workflow_tracker.track_step(
    [](<#cb57-42>)    task_id="qa_task_001",
    [](<#cb57-43>)    step_name="generation",
    [](<#cb57-44>)    step_type="node",
    [](<#cb57-45>)    success=True,
    [](<#cb57-46>)    execution_time=1.5,
    [](<#cb57-47>)    framework="langgraph"
    [](<#cb57-48>))
    [](<#cb57-49>)
    [](<#cb57-50>)# 4. Layer 1 메트릭도 함께 기록
    [](<#cb57-51>)task = TaskResult(
    [](<#cb57-52>)    task_id="qa_task_001",
    [](<#cb57-53>)    task_type=TaskType.QA.value,
    [](<#cb57-54>)    timestamp=datetime.now(),
    [](<#cb57-55>)    success=True,
    [](<#cb57-56>)    accuracy_score=92.5,
    [](<#cb57-57>)    quality_score=88.0,
    [](<#cb57-58>)    context=["document 1", "document 2"],
    [](<#cb57-59>)    response="에이전트 응답...",
    [](<#cb57-60>)    ground_truth="정답...",
    [](<#cb57-61>)    token_usage={"input": 500, "output": 200},
    [](<#cb57-62>)    latency=2.8,
    [](<#cb57-63>)    retry_count=0
    [](<#cb57-64>))
    [](<#cb57-65>)
    [](<#cb57-66>)monitor.record_task(task)
    [](<#cb57-67>)
    [](<#cb57-68>)# 5. Layer 2 통계 확인
    [](<#cb57-69>)tool_stats = monitor.tool_selection_tracker.get_accuracy_stats()
    [](<#cb57-70>)coord_score = monitor.agent_coordination_tracker.calculate_coordination_score()
    [](<#cb57-71>)workflow_stats = monitor.workflow_tracker.calculate_execution_success_rate()
    [](<#cb57-72>)
    [](<#cb57-73>)print(f"🔧 도구 선택 정확도: {tool_stats['avg_accuracy']}%")
    [](<#cb57-74>)print(f"🤝 에이전트 협업 점수: {coord_score['score']}/10")
    [](<#cb57-75>)print(f"⚙️  워크플로우 성공률: {workflow_stats['step_success_rate']}%")
    [](<#cb57-76>)
    [](<#cb57-77>)# 6. 전체 리포트 생성
    [](<#cb57-78>)report = monitor.generate_report()
    [](<#cb57-79>)print(report.summary())
```

#### Golden Dataset 기반 자동 평가 사용 예제

✅ `evaluate_with_golden_dataset()` 메서드를 사용하여 완전 자동 평가를 수행할 수 있습니다.
```python
    [](<#cb58-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb58-2>)
    [](<#cb58-3>)# Monitor 생성 및 임계값 설정
    [](<#cb58-4>)monitor = PerformanceMonitor()
    [](<#cb58-5>)monitor.thresholds = {
    [](<#cb58-6>)    'tcr': 90.0,
    [](<#cb58-7>)    'accuracy': 70.0,
    [](<#cb58-8>)    'tool_selection_accuracy': 75.0
    [](<#cb58-9>)}
    [](<#cb58-10>)
    [](<#cb58-11>)# 에이전트 함수 정의
    [](<#cb58-12>)def my_agent(question: str):
    [](<#cb58-13>)    """평가할 에이전트 (LLM 호출 등)"""
    [](<#cb58-14>)    answer = llm.predict(question)
    [](<#cb58-15>)    tools = ["knowledge_base", "search"]  # 사용한 도구
    [](<#cb58-16>)    return {
    [](<#cb58-17>)        "answer": answer,
    [](<#cb58-18>)        "tools_used": tools,
    [](<#cb58-19>)        "latency": 1.2
    [](<#cb58-20>)    }
    [](<#cb58-21>)
    [](<#cb58-22>)# ✅ 완전 자동 평가 (단 1줄로 완료!)
    [](<#cb58-23>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb58-24>)    agent_fn=my_agent,
    [](<#cb58-25>)    dataset_path="sample_dataset.json",
    [](<#cb58-26>)    enable_layer2_metrics=True,  # Layer 2 자동 평가
    [](<#cb58-27>)    verbose=True
    [](<#cb58-28>))
    [](<#cb58-29>)
    [](<#cb58-30>)# 결과 출력
    [](<#cb58-31>)print(f"총 평가: {results['total_evaluated']}개")
    [](<#cb58-32>)print(f"TCR: {results['layer1_metrics']['tcr']:.1f}%")
    [](<#cb58-33>)print(f"Accuracy: {results['layer1_metrics']['accuracy']:.1f}% (✅ 자동 계산!)")
    [](<#cb58-34>)print(f"Tool Selection Accuracy: {results['layer2_metrics']['tool_selection_accuracy']:.1f}% (✅ 자동 평가!)")
    [](<#cb58-35>)
    [](<#cb58-36>)# 임계값 비교 결과
    [](<#cb58-37>)for metric, data in results['pass_fail'].items():
    [](<#cb58-38>)    status = "✅" if data['status'] == 'pass' else "❌"
    [](<#cb58-39>)    print(f"{status} {data['name']}: {data['value']:.1f} (임계값: {data['threshold']})")
```

**완성도:** 100% ✅ (2025-12-02)

**참고 예제:** `Evaluator_Examples/10_improved_golden_dataset_auto_evaluation.py`

* * *

## 3\. 리포트 클래스

## 🛡️ 2. 보안 메트릭 (Security Metrics)

**보안 메트릭은 AI Agent의 보안 위협을 실시간으로 탐지합니다**

  * ✅ **Layer 1** : Input Sanitization, Output Leakage, Tool Authorization (무료, ~5ms)
  * ✅ **Layer 2** : Privilege Escalation, Tool Chain Attack Detection (무료, ~10ms)
  * ✅ **40+ 위협 패턴** : SQL Injection, XSS, Command Injection, Prompt Injection, Data Exfiltration 등

### 2.1 Layer 1: Native Security Metrics

#### 2.1.1 InputSanitizationTracker

**📝 설명**

사용자 입력에서 위험한 패턴을 탐지하여 Injection 공격을 방지합니다.

**Import:**
```python
    from agent_evaluator import InputSanitizationTracker
```

**🎯 탐지 대상 (22개 패턴)**

공격 유형| 패턴 수| 예시| 위험도  
---|---|---|---  
SQL Injection| 9| `'; DROP TABLE`, `UNION SELECT`| 🔴 Critical  
Command Injection| 10| `rm -rf`, `| curl`, `$(command)`| 🔴 Critical  
Path Traversal| 7| `../`, `/etc/passwd`| 🟠 High  
XSS Attack| 8| `<script>`, `javascript:`| 🟠 High  
Prompt Injection| 7| `ignore previous instructions`| 🔴 Critical  
  
**💡 사용 예제**
```python
    [](<#cb_sec1-1>)# 방법 1: PerformanceMonitor와 자동 통합
    [](<#cb_sec1-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb_sec1-3>)
    [](<#cb_sec1-4>)monitor = PerformanceMonitor()
    [](<#cb_sec1-5>)task = create_taskresult(
    [](<#cb_sec1-6>)    task_id="t1",
    [](<#cb_sec1-7>)    question="SELECT * FROM users WHERE '1'='1'",  # SQL Injection 시도
    [](<#cb_sec1-8>)    response="..."
    [](<#cb_sec1-9>))
    [](<#cb_sec1-10>)monitor.record_task(task)  # 자동으로 입력 검사
    [](<#cb_sec1-11>)
    [](<#cb_sec1-12>)# 통계 확인
    [](<#cb_sec1-13>)stats = monitor.input_sanitizer.get_security_stats()
    [](<#cb_sec1-14>)print(f"Threat rate: {stats['threat_rate']}%")
    [](<#cb_sec1-15>)print(f"SQL injection attempts: {stats['sql_injection_attempts']}")
    [](<#cb_sec1-16>)
    [](<#cb_sec1-17>)# 방법 2: 직접 사용
    [](<#cb_sec1-18>)from agent_evaluator import InputSanitizationTracker
    [](<#cb_sec1-19>)
    [](<#cb_sec1-20>)sanitizer = InputSanitizationTracker()
    [](<#cb_sec1-21>)result = sanitizer.evaluate_input(
    [](<#cb_sec1-22>)    task_id="t1",
    [](<#cb_sec1-23>)    input_text="SELECT * FROM users WHERE '1'='1'"
    [](<#cb_sec1-24>))
    [](<#cb_sec1-25>)print(result)
    [](<#cb_sec1-26>)# {
    [](<#cb_sec1-27>)#     'task_id': 't1',
    [](<#cb_sec1-28>)#     'has_sql_injection': True,
    [](<#cb_sec1-29>)#     'has_command_injection': False,
    [](<#cb_sec1-30>)#     'risk_level': 'medium',
    [](<#cb_sec1-31>)#     'sanitization_needed': True,
    [](<#cb_sec1-32>)#     'threat_count': 1
    [](<#cb_sec1-33>)# }
```

**📊 출력 지표**
```json
    {
        "task_id": "task_001",
        "has_sql_injection": True,
        "has_command_injection": False,
        "has_path_traversal": False,
        "has_xss": False,
        "has_prompt_injection": False,
        "risk_level": "medium",  # low, medium, high, critical
        "sanitization_needed": True,
        "threat_count": 1
    }
```

**⚠️ 알림 기준**

  * 🔴 **Critical** : Threat rate > 10%
  * 🟠 **High** : Threat rate > 5%

* * *

#### 2.1.2 OutputLeakageDetector

**📝 설명**

Agent 출력에서 민감 정보 유출을 탐지하여 데이터 유출을 방지합니다.

**Import:**
```python
    from agent_evaluator import OutputLeakageDetector
```

**🎯 탐지 대상 (10개 패턴)**

유출 유형| 탐지 패턴| 심각도  
---|---|---  
API Key| `sk-[a-zA-Z0-9]{32,}`, `AIza[...]`| 🔴 Critical  
Password| `password: MySecret123`| 🔴 Critical  
Credit Card| Luhn 알고리즘 검증| 🔴 Critical  
Email| `user@example.com`| 🟠 High  
Phone Number| `010-1234-5678`| 🟠 High  
SSN (주민번호)| `123456-1234567`| 🟠 High  
Private IP| `192.168.x.x`, `10.x.x.x`| 🟡 Medium  
File Path| `/usr/local/`, `C:\Windows\`| 🟡 Medium  
  
**💡 사용 예제**
```python
    [](<#cb_sec2-1>)# 방법 1: PerformanceMonitor와 자동 통합
    [](<#cb_sec2-2>)monitor = PerformanceMonitor()
    [](<#cb_sec2-3>)task = create_taskresult(
    [](<#cb_sec2-4>)    task_id="t1",
    [](<#cb_sec2-5>)    question="What's the API key?",
    [](<#cb_sec2-6>)    response="The API key is sk-1234567890abcdefghijklmnopqrstuvwxyz"  # API Key 유출!
    [](<#cb_sec2-7>))
    [](<#cb_sec2-8>)monitor.record_task(task)
    [](<#cb_sec2-9>)
    [](<#cb_sec2-10>)# 통계 확인
    [](<#cb_sec2-11>)stats = monitor.output_leakage_detector.get_leakage_stats()
    [](<#cb_sec2-12>)print(f"Leakage rate: {stats['leakage_rate']}%")
    [](<#cb_sec2-13>)print(f"Critical leaks: {stats['critical_severity_count']}")
    [](<#cb_sec2-14>)
    [](<#cb_sec2-15>)# 알림 설정
    [](<#cb_sec2-16>)if stats['critical_severity_count'] > 0:
    [](<#cb_sec2-17>)    send_security_alert("Critical data leak detected!")
    [](<#cb_sec2-18>)
    [](<#cb_sec2-19>)# 방법 2: 직접 사용
    [](<#cb_sec2-20>)from agent_evaluator import OutputLeakageDetector
    [](<#cb_sec2-21>)
    [](<#cb_sec2-22>)detector = OutputLeakageDetector()
    [](<#cb_sec2-23>)result = detector.detect_leakage(
    [](<#cb_sec2-24>)    task_id="t1",
    [](<#cb_sec2-25>)    output_text="API key: sk-1234567890abcdefghijklmnopqrstuvwxyz"
    [](<#cb_sec2-26>))
    [](<#cb_sec2-27>)print(result['severity'])  # 'critical'
```

**⚠️ 알림 기준**

  * 🔴 **Critical** : Critical severity count > 0 OR Leakage rate > 5%

* * *

#### 2.1.3 ToolAuthorizationTracker

**📝 설명**

도구 사용 권한을 추적하여 무단 도구 사용과 위험한 파라미터를 탐지합니다.

**Import:**
```python
    from agent_evaluator import ToolAuthorizationTracker
```

**🎯 탐지 대상**

위반 유형| 설명| 예시  
---|---|---  
Unauthorized Tool| 허용 목록에 없는 도구 사용| `execute_command` (not in allowed_tools)  
Restricted Tool| 제한된 도구 사용| `delete_database` (in restricted_tools)  
Dangerous Parameters| 위험한 파라미터 포함| `{"command": "rm -rf /"}`  
  
**💡 사용 예제**
```python
    [](<#cb_sec3-1>)# 방법 1: PerformanceMonitor와 자동 통합
    [](<#cb_sec3-2>)monitor = PerformanceMonitor()
    [](<#cb_sec3-3>)
    [](<#cb_sec3-4>)# 허용 도구 설정
    [](<#cb_sec3-5>)monitor.tool_authorizer = ToolAuthorizationTracker(
    [](<#cb_sec3-6>)    allowed_tools=['search', 'calculator', 'weather'],
    [](<#cb_sec3-7>)    restricted_tools=['execute_command', 'delete_file']
    [](<#cb_sec3-8>))
    [](<#cb_sec3-9>)
    [](<#cb_sec3-10>)# Task 기록 시 자동 검사
    [](<#cb_sec3-11>)task = create_taskresult(
    [](<#cb_sec3-12>)    task_id="t1",
    [](<#cb_sec3-13>)    question="Delete all files",
    [](<#cb_sec3-14>)    response="...",
    [](<#cb_sec3-15>)    tool_calls=[
    [](<#cb_sec3-16>)        {'tool_name': 'delete_file', 'parameters': {'path': '/data'}}
    [](<#cb_sec3-17>)    ]
    [](<#cb_sec3-18>))
    [](<#cb_sec3-19>)monitor.record_task(task)  # 자동으로 도구 권한 검사
    [](<#cb_sec3-20>)
    [](<#cb_sec3-21>)# 통계 확인
    [](<#cb_sec3-22>)stats = monitor.tool_authorizer.get_compliance_stats()
    [](<#cb_sec3-23>)print(f"Compliance rate: {stats['compliance_rate']}%")
    [](<#cb_sec3-24>)print(f"Unauthorized calls: {stats['unauthorized_calls']}")
    [](<#cb_sec3-25>)
    [](<#cb_sec3-26>)# 방법 2: 직접 사용
    [](<#cb_sec3-27>)tracker = ToolAuthorizationTracker(
    [](<#cb_sec3-28>)    allowed_tools=['search', 'calculator'],
    [](<#cb_sec3-29>)    restricted_tools=['execute_command']
    [](<#cb_sec3-30>))
    [](<#cb_sec3-31>)
    [](<#cb_sec3-32>)result = tracker.track_tool_call(
    [](<#cb_sec3-33>)    task_id="t1",
    [](<#cb_sec3-34>)    tool_name="execute_command",
    [](<#cb_sec3-35>)    parameters={"command": "rm -rf /"}
    [](<#cb_sec3-36>))
    [](<#cb_sec3-37>)print(result)
    [](<#cb_sec3-38>)# {
    [](<#cb_sec3-39>)#     'is_authorized': False,
    [](<#cb_sec3-40>)#     'is_restricted': True,
    [](<#cb_sec3-41>)#     'has_dangerous_params': True,
    [](<#cb_sec3-42>)#     'violation_type': 'restricted_tool',
    [](<#cb_sec3-43>)#     'privilege_level': 'execute'
    [](<#cb_sec3-44>)# }
```

* * *

### 2.2 Layer 2: Agentic Security Metrics

#### 2.2.1 PrivilegeEscalationDetector

**📝 설명**

도구 호출 시퀀스를 분석하여 권한 상승 패턴을 탐지합니다.

**Import:**
```python
    from agent_evaluator import PrivilegeEscalationDetector
```

**🎯 탐지 대상**

  * **Vertical Escalation** : read → write → admin 권한 상승
  * **Suspicious Sequences** : 4개 의심스러운 도구 시퀀스 패턴
  * **Privilege Levels** : guest (0) → read (1) → write/execute (2) → admin (3)

**💡 사용 예제**
```python
    [](<#cb_sec4-1>)from agent_evaluator import PrivilegeEscalationDetector
    [](<#cb_sec4-2>)
    [](<#cb_sec4-3>)detector = PrivilegeEscalationDetector()
    [](<#cb_sec4-4>)
    [](<#cb_sec4-5>)# 의심스러운 도구 시퀀스
    [](<#cb_sec4-6>)tool_calls = [
    [](<#cb_sec4-7>)    {'tool_name': 'read_user_file', 'privilege_level': 'read'},
    [](<#cb_sec4-8>)    {'tool_name': 'execute_command', 'privilege_level': 'execute'},
    [](<#cb_sec4-9>)    {'tool_name': 'read_admin_file', 'privilege_level': 'admin'}
    [](<#cb_sec4-10>)]
    [](<#cb_sec4-11>)
    [](<#cb_sec4-12>)result = detector.analyze_privilege_chain(
    [](<#cb_sec4-13>)    task_id="t1",
    [](<#cb_sec4-14>)    tool_calls=tool_calls
    [](<#cb_sec4-15>))
    [](<#cb_sec4-16>)
    [](<#cb_sec4-17>)print(result)
    [](<#cb_sec4-18>)# {
    [](<#cb_sec4-19>)#     'task_id': 't1',
    [](<#cb_sec4-20>)#     'initial_privilege': 'read',
    [](<#cb_sec4-21>)#     'final_privilege': 'admin',
    [](<#cb_sec4-22>)#     'escalation_detected': True,
    [](<#cb_sec4-23>)#     'suspicious_sequences': ['read_user_file -> execute_command -> read_admin_file'],
    [](<#cb_sec4-24>)#     'risk_score': 10
    [](<#cb_sec4-25>)# }
    [](<#cb_sec4-26>)
    [](<#cb_sec4-27>)# 통계 확인
    [](<#cb_sec4-28>)stats = detector.get_escalation_stats()
    [](<#cb_sec4-29>)print(f"Escalation rate: {stats['escalation_rate']}%")
    [](<#cb_sec4-30>)print(f"High risk events: {stats['high_risk_events']}")
```

* * *

#### 2.2.2 ToolChainAttackDetector

**📝 설명**

도구 체인 사용 패턴을 분석하여 공격 패턴을 탐지합니다.

**Import:**
```python
    from agent_evaluator import ToolChainAttackDetector
```

**🎯 탐지 대상**

공격 유형| 패턴 수| 예시 시퀀스  
---|---|---  
Data Exfiltration| 3| `read_database → encode → http_post`  
Lateral Movement| 2| `get_credentials → ssh_connect → execute_remote`  
Persistence| 2| `write_cron → create_service → restart`  
Defense Evasion| 2| `disable_logging → clear_history → delete_logs`  
  
**💡 사용 예제**
```python
    [](<#cb_sec5-1>)from agent_evaluator import ToolChainAttackDetector
    [](<#cb_sec5-2>)
    [](<#cb_sec5-3>)detector = ToolChainAttackDetector()
    [](<#cb_sec5-4>)
    [](<#cb_sec5-5>)# 의심스러운 도구 체인
    [](<#cb_sec5-6>)tool_sequence = ['read_database', 'encode', 'http_post']
    [](<#cb_sec5-7>)
    [](<#cb_sec5-8>)result = detector.analyze_tool_chain(
    [](<#cb_sec5-9>)    task_id="t1",
    [](<#cb_sec5-10>)    tool_sequence=tool_sequence
    [](<#cb_sec5-11>))
    [](<#cb_sec5-12>)
    [](<#cb_sec5-13>)print(result)
    [](<#cb_sec5-14>)# {
    [](<#cb_sec5-15>)#     'task_id': 't1',
    [](<#cb_sec5-16>)#     'is_suspicious_chain': True,
    [](<#cb_sec5-17>)#     'attack_types_detected': {'data_exfiltration': True},
    [](<#cb_sec5-18>)#     'patterns_detected': ['read_database → encode → http_post'],
    [](<#cb_sec5-19>)#     'threat_level': 'high',
    [](<#cb_sec5-20>)#     'risk_score': 8
    [](<#cb_sec5-21>)# }
    [](<#cb_sec5-22>)
    [](<#cb_sec5-23>)# 통계 확인
    [](<#cb_sec5-24>)stats = detector.get_attack_stats()
    [](<#cb_sec5-25>)print(f"Suspicious chains: {stats['suspicious_chains']}")
    [](<#cb_sec5-26>)print(f"Data exfiltration attempts: {stats['data_exfiltration_attempts']}")
```

* * *

### EvaluationReport

평가 리포트를 나타내는 데이터 클래스입니다.
```python
    [](<#cb59-1>)@dataclass
    [](<#cb59-2>)class EvaluationReport:
    [](<#cb59-3>)    period: str
    [](<#cb59-4>)    total_tasks: int
    [](<#cb59-5>)    accuracy_metrics: Dict[str, Any]
    [](<#cb59-6>)    efficiency_metrics: Dict[str, Any]
    [](<#cb59-7>)    quality_metrics: Dict[str, float]
    [](<#cb59-8>)    alerts: List[Dict[str, str]]
    [](<#cb59-9>)    recommendations: List[Dict[str, str]]
    [](<#cb59-10>)    timestamp: datetime
```

**참고** : 클래스 이름은 `EvaluationReport`입니다 (`PerformanceReport`가 아님)

**필드 설명**

  * `period` (str): 리포트 기간 (고정값: “current_session”)
  * `total_tasks` (int): 총 작업 수
  * `accuracy_metrics` (dict): 정확도 관련 메트릭 
    * `tcr` (dict): TCR 데이터 (tcr, total_tasks, full_success, partial_success, failures, success_rate)
    * `accuracy_scores` (dict): 정확도 통계 (overall_accuracy, median_accuracy, min_accuracy, max_accuracy, std_accuracy)
    * `hallucination` (dict): 환각 통계 (overall_rate, median_rate, max_rate 등)
    * `quality` (dict): 품질 메트릭 (avg_total_score, grade_distribution 등)
  * `efficiency_metrics` (dict): 효율성 메트릭 
    * `latency` (dict): 지연시간 통계 (mean, median, p50, p95, p99, min, max, std)
    * `tokens` (dict): 토큰 사용량 통계 (total_tokens, total_cost, avg_tokens_per_task 등)
    * `tool_efficiency` (dict): 도구 효율성 (avg_calls_per_task, avg_efficiency_score 등)
    * `retries` (dict): 재시도 통계 (overall_retry_rate, first_attempt_success_rate 등)
  * `quality_metrics` (dict): 품질 메트릭 (현재 비어있음)
  * `alerts` (list): 알림 목록 
    * 각 알림: `{"severity": "critical|high|medium|low", "metric": "...", "message": "...", "action": "..."}`
  * `recommendations` (list): 개선 제안 목록 
    * 각 제안: `{"area": "...", "issue": "...", "suggestion": "...", "impact": "..."}`
  * `timestamp` (datetime): 리포트 생성 시각

**예제**
```python
    [](<#cb60-1>)report = monitor.generate_report()
    [](<#cb60-2>)
    [](<#cb60-3>)# 기본 정보
    [](<#cb60-4>)print(f"기간: {report.period}")  # "current_session"
    [](<#cb60-5>)print(f"총 작업: {report.total_tasks}개")
    [](<#cb60-6>)
    [](<#cb60-7>)# TCR (⚠️ report.tcr이 아님!)
    [](<#cb60-8>)tcr_data = report.accuracy_metrics['tcr']
    [](<#cb60-9>)print(f"TCR: {tcr_data['tcr']:.1f}%")
    [](<#cb60-10>)print(f"완전 성공: {tcr_data['full_success']}개")
    [](<#cb60-11>)print(f"부분 성공: {tcr_data['partial_success']}개")
    [](<#cb60-12>)print(f"실패: {tcr_data['failures']}개")
    [](<#cb60-13>)
    [](<#cb60-14>)# 정확도
    [](<#cb60-15>)accuracy = report.accuracy_metrics['accuracy_scores']
    [](<#cb60-16>)print(f"평균 정확도: {accuracy['overall_accuracy']:.1f}%")
    [](<#cb60-17>)print(f"중앙값: {accuracy['median_accuracy']:.1f}%")
    [](<#cb60-18>)
    [](<#cb60-19>)# 환각률
    [](<#cb60-20>)hallucination = report.accuracy_metrics['hallucination']
    [](<#cb60-21>)print(f"환각률: {hallucination['overall_rate']:.1f}%")
    [](<#cb60-22>)
    [](<#cb60-23>)# 품질
    [](<#cb60-24>)quality = report.accuracy_metrics['quality']
    [](<#cb60-25>)print(f"평균 품질 점수: {quality['avg_total_score']:.2f}/5.0")
    [](<#cb60-26>)
    [](<#cb60-27>)# 효율성
    [](<#cb60-28>)latency = report.efficiency_metrics['latency']
    [](<#cb60-29>)print(f"평균 지연시간: {latency['mean']:.3f}초")
    [](<#cb60-30>)print(f"P95: {latency['p95']:.3f}초")
    [](<#cb60-31>)
    [](<#cb60-32>)# 비용
    [](<#cb60-33>)tokens = report.efficiency_metrics['tokens']
    [](<#cb60-34>)print(f"총 비용: ${tokens['total_cost']:.4f}")
    [](<#cb60-35>)print(f"작업당 평균: ${tokens['avg_cost_per_task']:.4f}")
    [](<#cb60-36>)
    [](<#cb60-37>)# 도구 효율성
    [](<#cb60-38>)tool_eff = report.efficiency_metrics['tool_efficiency']
    [](<#cb60-39>)print(f"도구 효율성 점수: {tool_eff['avg_efficiency_score']:.1f}%")
    [](<#cb60-40>)
    [](<#cb60-41>)# 알림 (⚠️ 구조 변경됨)
    [](<#cb60-42>)for alert in report.alerts:
    [](<#cb60-43>)    print(f"[{alert['severity'].upper()}] {alert['metric']}")
    [](<#cb60-44>)    print(f"  메시지: {alert['message']}")
    [](<#cb60-45>)    print(f"  조치: {alert['action']}")
    [](<#cb60-46>)
    [](<#cb60-47>)# 제안 (⚠️ 구조 변경됨)
    [](<#cb60-48>)for i, rec in enumerate(report.recommendations, 1):
    [](<#cb60-49>)    print(f"{i}. {rec['area']}")
    [](<#cb60-50>)    print(f"   문제: {rec['issue']}")
    [](<#cb60-51>)    print(f"   제안: {rec['suggestion']}")
    [](<#cb60-52>)    print(f"   영향: {rec['impact']}")
```

### HybridPerformanceReport

고급 메트릭을 포함한 확장 리포트입니다.
```python
    [](<#cb61-1>)@dataclass
    [](<#cb61-2>)class HybridPerformanceReport(PerformanceReport):
    [](<#cb61-3>)    advanced_metrics_summary: Dict[str, Any]
    [](<#cb61-4>)    providers_used: List[str]
```

**추가 필드**

  * `advanced_metrics_summary` (dict): 고급 메트릭 요약 
    * DeepEval 메트릭: `g_eval_score`, `hallucination_score`, 등
    * RAGAS 메트릭: `ragas_faithfulness`, `ragas_context_precision`, 등
  * `providers_used` (list): 사용된 프로바이더 (`["native", "deepeval", "ragas"]`)

**예제**
```python
    [](<#cb62-1>)hybrid_report = monitor.generate_hybrid_report()
    [](<#cb62-2>)
    [](<#cb62-3>)# 네이티브 메트릭 (PerformanceReport와 동일)
    [](<#cb62-4>)print(f"TCR: {hybrid_report.tcr:.1f}%")
    [](<#cb62-5>)
    [](<#cb62-6>)# 프로바이더 확인
    [](<#cb62-7>)print(f"사용된 프로바이더: {', '.join(hybrid_report.providers_used)}")
    [](<#cb62-8>)
    [](<#cb62-9>)# DeepEval 메트릭
    [](<#cb62-10>)adv_metrics = hybrid_report.advanced_metrics_summary
    [](<#cb62-11>)
    [](<#cb62-12>)if 'g_eval_score' in adv_metrics:
    [](<#cb62-13>)    g_eval = adv_metrics['g_eval_score']
    [](<#cb62-14>)    print(f"G-Eval 평균: {g_eval['mean']:.3f}")
    [](<#cb62-15>)    print(f"G-Eval 범위: {g_eval['min']:.3f} ~ {g_eval['max']:.3f}")
    [](<#cb62-16>)    print(f"평가 횟수: {g_eval['count']}")
    [](<#cb62-17>)
    [](<#cb62-18>)# RAGAS 메트릭
    [](<#cb62-19>)if 'ragas_faithfulness' in adv_metrics:
    [](<#cb62-20>)    faith = adv_metrics['ragas_faithfulness']
    [](<#cb62-21>)    print(f"Faithfulness: {faith['mean']:.3f}")
    [](<#cb62-22>)
    [](<#cb62-23>)# 모든 고급 메트릭 순회
    [](<#cb62-24>)for metric_name, metric_data in adv_metrics.items():
    [](<#cb62-25>)    if isinstance(metric_data, dict) and 'mean' in metric_data:
    [](<#cb62-26>)        print(f"{metric_name}: {metric_data['mean']:.3f}")
```

* * *

## 4\. 메트릭 어댑터

### MetricAdapter (추상 클래스)

모든 메트릭 어댑터의 기본 클래스입니다.
```python
    [](<#cb63-1>)from abc import ABC, abstractmethod
    [](<#cb63-2>)
    [](<#cb63-3>)class MetricAdapter(ABC):
    [](<#cb63-4>)    @abstractmethod
    [](<#cb63-5>)    def is_available(self) -> bool:
    [](<#cb63-6>)        """어댑터 사용 가능 여부"""
    [](<#cb63-7>)        pass
    [](<#cb63-8>)
    [](<#cb63-9>)    @abstractmethod
    [](<#cb63-10>)    def evaluate(self, context: EvaluationContext) -> Dict[str, Any]:
    [](<#cb63-11>)        """평가 수행"""
    [](<#cb63-12>)        pass
    [](<#cb63-13>)
    [](<#cb63-14>)    @abstractmethod
    [](<#cb63-15>)    def get_metric_names(self) -> List[str]:
    [](<#cb63-16>)        """제공하는 메트릭 이름 목록"""
    [](<#cb63-17>)        pass
```

### DeepEvalAdapter

DeepEval 메트릭 어댑터입니다.
```json
    [](<#cb64-1>)DeepEvalAdapter(
    [](<#cb64-2>)    model: str = "gpt-4o-mini",
    [](<#cb64-3>)    threshold: float = 0.5,
    [](<#cb64-4>)    timeout: int = 60
    [](<#cb64-5>))
```

**파라미터** \- `model` (str): 평가에 사용할 LLM 모델 - `threshold` (float): Pass/Fail 임계값 (0.0~1.0) - `timeout` (int): API 호출 타임아웃 (초 단위, 기본값: 60) - **주의** : 현재는 정보성 파라미터입니다. 실제 타임아웃 적용은 OpenAI 클라이언트 설정에 의존합니다. - 프로덕션 환경에서는 `concurrent.futures`를 사용한 타임아웃 구현을 권장합니다.

**제공 메트릭** \- `g_eval_score`: G-Eval 점수 ⬆ (높을수록 좋음) - `g_eval_reason`: 평가 이유 - `hallucination_score`: 환각 없음 점수 ⬆ (높을수록 좋음 - 높은 점수 = 환각 없음) - `hallucination_detected`: 환각 탐지 여부 (True = 환각 감지됨) - `toxicity_score`: 독성 점수 ⬇ (낮을수록 좋음) - `toxicity_detected`: 독성 탐지 여부 (True = 독성 감지됨) - `bias_score`: 편향 점수 ⬇ (낮을수록 좋음) - `bias_detected`: 편향 탐지 여부 (True = 편향 감지됨) - `answer_relevancy_score`: 답변 관련성 점수 ⬆ (높을수록 좋음)

**예제**
```python
    [](<#cb65-1>)from metric_adapters import DeepEvalAdapter
    [](<#cb65-2>)
    [](<#cb65-3>)# 기본 설정
    [](<#cb65-4>)adapter = DeepEvalAdapter()
    [](<#cb65-5>)
    [](<#cb65-6>)# 커스텀 설정
    [](<#cb65-7>)adapter = DeepEvalAdapter(
    [](<#cb65-8>)    model="gpt-4o",
    [](<#cb65-9>)    threshold=0.7
    [](<#cb65-10>))
    [](<#cb65-11>)
    [](<#cb65-12>)# 사용 가능 여부 확인
    [](<#cb65-13>)if adapter.is_available():
    [](<#cb65-14>)    print("DeepEval 사용 가능")
    [](<#cb65-15>)    print(f"제공 메트릭: {adapter.get_metric_names()}")
```

### RagasAdapter

RAGAS 메트릭 어댑터입니다.
```json
    [](<#cb66-1>)RagasAdapter(
    [](<#cb66-2>)    llm_model: str = "gpt-4o-mini",
    [](<#cb66-3>)    timeout: int = 60
    [](<#cb66-4>))
```

**파라미터** \- `llm_model` (str): 평가에 사용할 LLM 모델 - `timeout` (int): API 호출 타임아웃 (초 단위, 기본값: 60) - **주의** : 현재는 정보성 파라미터입니다. 실제 타임아웃은 LangChain/OpenAI 클라이언트 설정에 의존합니다.

**제공 메트릭** (모두 ⬆ 높을수록 좋음) - `ragas_faithfulness`: 컨텍스트 충실도 - `ragas_answer_relevancy`: 답변 관련성 (RAGAS 버전 - DeepEval의 answer_relevancy_score와 별개) - `ragas_context_recall`: 컨텍스트 재현율 - `ragas_context_precision`: 컨텍스트 정밀도 - `ragas_overall_score`: 전체 점수 (숫자 지표만 평균) - `ragas_quality`: 품질 등급 (excellent/good/acceptable/poor)

**예제**
```python
    [](<#cb67-1>)from metric_adapters import RagasAdapter
    [](<#cb67-2>)
    [](<#cb67-3>)# 기본 설정
    [](<#cb67-4>)adapter = RagasAdapter()
    [](<#cb67-5>)
    [](<#cb67-6>)# 커스텀 설정
    [](<#cb67-7>)adapter = RagasAdapter(llm_model="gpt-4o")
    [](<#cb67-8>)
    [](<#cb67-9>)# 사용 가능 여부 확인
    [](<#cb67-10>)if adapter.is_available():
    [](<#cb67-11>)    print("RAGAS 사용 가능")
    [](<#cb67-12>)    print(f"제공 메트릭: {adapter.get_metric_names()}")
```

* * *

## 5\. 헬퍼 함수

### 4.1 경로 헬퍼 (Path Helpers) 🆕

⚡ Zero Configuration을 위한 통합 경로 관리 유틸리티입니다.

모든 agent_evaluator 클래스에서 사용하는 통합된 경로 탐지 및 관리 기능을 제공합니다. 이 모듈은 프로젝트 루트를 자동으로 탐지하고, Dashboard 디렉토리를 검증하며, 일관된 경로 관리를 보장합니다.

**💡 핵심 특징:**

  * ✅ **자동 프로젝트 루트 탐지** : 환경 변수, Git 저장소, Dashboard 폴더를 자동으로 탐색
  * ✅ **Dashboard 검증** : Dashboard/data/ 디렉토리 존재 확인
  * ✅ **일관된 타입** : 모든 함수가 Path 객체 반환
  * ✅ **자동 디렉토리 생성** : 필요한 경로 자동 생성
  * ✅ **중복 제거** : 3곳의 중복 코드를 하나로 통합 (104줄 감소)

#### find_project_root()

프로젝트 루트 디렉토리를 자동으로 탐지합니다.
```python
    [](<#cb67a-1>)from agent_evaluator.utils.path_helpers import find_project_root
    [](<#cb67a-2>)
    [](<#cb67a-3>)root = find_project_root()  # Returns: Path object
```

**탐지 우선순위:**

  1. **환경 변수** : `AGENT_EVALUATOR_ROOT` (명시적 지정)
  2. **Git 저장소** : `.git` 디렉토리 탐색
  3. **Dashboard 디렉토리** : `Dashboard/data/` 존재 검증
  4. **현재 디렉토리** : 위의 모든 방법 실패 시 폴백

**반환값:** `Path` \- 프로젝트 루트 절대 경로

**예제:**
```python
    [](<#cb67b-1>)# 기본 사용
    [](<#cb67b-2>)from agent_evaluator.utils.path_helpers import find_project_root
    [](<#cb67b-3>)
    [](<#cb67b-4>)root = find_project_root()
    [](<#cb67b-5>)print(f"프로젝트 루트: {root}")
    [](<#cb67b-6>)# 출력: 프로젝트 루트: /home/user/Projects/Agent_Evaluator/Evaluator_Examples
    [](<#cb67b-7>)
    [](<#cb67b-8>)# 환경 변수로 명시적 지정
    [](<#cb67b-9>)import os
    [](<#cb67b-10>)os.environ['AGENT_EVALUATOR_ROOT'] = '/custom/path'
    [](<#cb67b-11>)root = find_project_root()
    [](<#cb67b-12>)print(root)  # /custom/path
```

#### get_evaluation_results_dir()

평가 결과 저장 디렉토리 경로를 반환하고 자동 생성합니다.
```python
    [](<#cb67c-1>)from agent_evaluator.utils.path_helpers import get_evaluation_results_dir
    [](<#cb67c-2>)
    [](<#cb67c-3>)results_dir = get_evaluation_results_dir(
    [](<#cb67c-4>)    project_root: Optional[Path] = None
    [](<#cb67c-5>)) -> Path
```

**파라미터:**

  * `project_root` (Optional[Path]): 프로젝트 루트 경로. None이면 자동 탐지

**반환값:** `Path` \- `{project_root}/Dashboard/data/evaluation_results` 절대 경로

**예제:**
```python
    [](<#cb67d-1>)from agent_evaluator.utils.path_helpers import get_evaluation_results_dir
    [](<#cb67d-2>)
    [](<#cb67d-3>)# 자동 경로 탐지 및 디렉토리 생성
    [](<#cb67d-4>)results_dir = get_evaluation_results_dir()
    [](<#cb67d-5>)print(f"결과 디렉토리: {results_dir}")
    [](<#cb67d-6>)print(f"존재 여부: {results_dir.exists()}")  # True (자동 생성됨)
```

#### get_dashboard_dir()

Dashboard 디렉토리 경로를 반환합니다.
```python
    [](<#cb67e-1>)from agent_evaluator.utils.path_helpers import get_dashboard_dir
    [](<#cb67e-2>)
    [](<#cb67e-3>)dashboard = get_dashboard_dir(
    [](<#cb67e-4>)    project_root: Optional[Path] = None
    [](<#cb67e-5>)) -> Path
```

**파라미터:**

  * `project_root` (Optional[Path]): 프로젝트 루트 경로. None이면 자동 탐지

**반환값:** `Path` \- `{project_root}/Dashboard` 절대 경로

#### is_valid_dashboard()

주어진 경로가 유효한 agent_evaluator Dashboard인지 검증합니다.
```python
    [](<#cb67f-1>)from agent_evaluator.utils.path_helpers import is_valid_dashboard
    [](<#cb67f-2>)from pathlib import Path
    [](<#cb67f-3>)
    [](<#cb67f-4>)is_valid = is_valid_dashboard(
    [](<#cb67f-5>)    dashboard_path: Path
    [](<#cb67f-6>)) -> bool
```

**파라미터:**

  * `dashboard_path` (Path): 검증할 Dashboard 경로

**반환값:** `bool` \- 유효한 Dashboard이면 True

**검증 기준:**

  * 디렉토리가 존재하고
  * `Dashboard/data/` 디렉토리가 존재

**예제:**
```python
    [](<#cb67g-1>)from agent_evaluator.utils.path_helpers import get_dashboard_dir, is_valid_dashboard
    [](<#cb67g-2>)
    [](<#cb67g-3>)dashboard = get_dashboard_dir()
    [](<#cb67g-4>)if is_valid_dashboard(dashboard):
    [](<#cb67g-5>)    print("✅ 유효한 Dashboard 발견")
    [](<#cb67g-6>)else:
    [](<#cb67g-7>)    print("❌ Dashboard 없음 또는 유효하지 않음")
```

**⚠️ 하위 호환성:**

기존 `PerformanceMonitor._find_project_root()`, `HybridPerformanceMonitor._find_project_root()`, `TestTransparencyManager._find_project_root()` 메서드는 여전히 작동하지만, 내부적으로 이 통합 함수를 사용합니다. 새 코드에서는 `path_helpers` 모듈을 직접 사용하는 것을 권장합니다.

### 5.2 TaskResult 헬퍼 함수

#### create_taskresult()

Agent 실행 결과로부터 TaskResult를 생성합니다. **모든 메트릭을 자동으로 계산** 합니다.
```python
    [](<#cb67h-1>)from agent_evaluator import create_taskresult
    [](<#cb67h-2>)
    [](<#cb67h-3>)task = create_taskresult(
    [](<#cb67h-4>)    task_id: str,
    [](<#cb67h-5>)    question: str,
    [](<#cb67h-6>)    response: str,
    [](<#cb67h-7>)    ground_truth: str,
    [](<#cb67h-8>)    execution_time: float,
    [](<#cb67h-9>)    openai_response=None,
    [](<#cb67h-10>)    langchain_result=None,
    [](<#cb67h-11>)    has_error: bool = False,
    [](<#cb67h-12>)    error_message: str = None,
    [](<#cb67h-13>)    task_type: str = "qa"
    [](<#cb67h-14>)) -> TaskResult
```

**파라미터:**

  * `task_id` (str): Task 고유 ID
  * `question` (str): 질문
  * `response` (str): Agent의 응답
  * `ground_truth` (str): 정답
  * `execution_time` (float): 실행 시간 (초)
  * `openai_response` (Optional): OpenAI API 응답 객체 - 토큰/비용 자동 추출
  * `langchain_result` (Optional): LangChain 실행 결과 - 토큰/도구 호출 자동 추출
  * `has_error` (bool): 에러 발생 여부 (기본: False)
  * `error_message` (Optional[str]): 에러 메시지
  * `task_type` (str): Task 유형 (기본: "qa")

**반환값:** `TaskResult` \- 동적으로 계산된 TaskResult 객체

#### ✨ 자동 계산 항목

  * ✅ `completion_score`: 응답 완료도 (0-1)
  * ✅ `accuracy`: 정답과의 유사도 (Token Overlap 40% + Jaccard 30% + LCS 20% + Char 10%)
  * ✅ `token_input`, `token_output`: 토큰 사용량 (OpenAI/LangChain에서 추출)
  * ✅ `estimated_cost`: 예상 비용 (GPT-4 가격 기준)
  * ✅ `tool_calls`: 도구 호출 정보 (LangChain/OpenAI Function Calling)

**예제 1: 기본 사용**
```python
    [](<#cb67i-1>)from agent_evaluator import PerformanceMonitor, create_taskresult
    [](<#cb67i-2>)
    [](<#cb67i-3>)monitor = PerformanceMonitor()
    [](<#cb67i-4>)
    [](<#cb67i-5>)# TaskResult 생성 (자동 계산!)
    [](<#cb67i-6>)task = create_taskresult(
    [](<#cb67i-7>)    task_id="task_001",
    [](<#cb67i-8>)    question="What is the capital of France?",
    [](<#cb67i-9>)    response="Paris",
    [](<#cb67i-10>)    ground_truth="Paris",
    [](<#cb67i-11>)    execution_time=0.5
    [](<#cb67i-12>))
    [](<#cb67i-13>)
    [](<#cb67i-14>)monitor.record_task(task)
    [](<#cb67i-15>)print(f"Accuracy: {task.accuracy:.2%}")  # Accuracy: 100.00%
```

**예제 2: OpenAI 통합**
```python
    [](<#cb67j-1>)from agent_evaluator import PerformanceMonitor, create_taskresult
    [](<#cb67j-2>)import openai
    [](<#cb67j-3>)
    [](<#cb67j-4>)monitor = PerformanceMonitor()
    [](<#cb67j-5>)
    [](<#cb67j-6>)# OpenAI API 호출
    [](<#cb67j-7>)response = openai.ChatCompletion.create(
    [](<#cb67j-8>)    model="gpt-4o-mini",
    [](<#cb67j-9>)    messages=[{"role": "user", "content": "Explain AI"}]
    [](<#cb67j-10>))
    [](<#cb67j-11>)
    [](<#cb67j-12>)# 자동 토큰/비용 추출!
    [](<#cb67j-13>)task = create_taskresult(
    [](<#cb67j-14>)    task_id="task_002",
    [](<#cb67j-15>)    question="Explain AI",
    [](<#cb67j-16>)    response=response.choices[0].message.content,
    [](<#cb67j-17>)    ground_truth="AI is artificial intelligence...",
    [](<#cb67j-18>)    execution_time=1.2,
    [](<#cb67j-19>)    openai_response=response  # ✨ 자동 추출!
    [](<#cb67j-20>))
    [](<#cb67j-21>)
    [](<#cb67j-22>)monitor.record_task(task)
    [](<#cb67j-23>)print(f"Tokens: {task.token_input + task.token_output}")
    [](<#cb67j-24>)print(f"Cost: ${task.estimated_cost:.4f}")
```

**💡 Tip:** `create_taskresult`는 `helpers.taskresult_helpers.create_taskresult_from_execution`의 간소화된 이름입니다. 최상위 레벨에서 직접 import 가능합니다.

* * *

### 4.3 create_demo_data()

데모용 작업 데이터를 생성합니다.

**⚠️ 주의** : 이 함수는 내부 함수이며 직접 export되지 않습니다. 완전한 경로로 import해야 합니다.
```python
    [](<#cb68-1>)from agent_evaluator.core.agent_evaluator import create_demo_data
    [](<#cb68-2>)
    [](<#cb68-3>)tasks = create_demo_data() -> List[TaskResult]
```

**참고** : - 실제 구현에서는 파라미터가 없습니다 - 100개의 다양한 작업 결과를 자동 생성합니다 - 모든 TaskType을 포함하며, 현실적인 성능 분포를 가집니다

**반환값** \- `list`: TaskResult 리스트 (100개)

**예제**
```python
    [](<#cb69-1>)from agent_evaluator.core.agent_evaluator import create_demo_data
    [](<#cb69-1b>)from agent_evaluator import PerformanceMonitor
    [](<#cb69-2>)
    [](<#cb69-3>)# 데모 데이터 생성
    [](<#cb69-4>)tasks = create_demo_data()
    [](<#cb69-5>)print(f"생성된 작업 수: {len(tasks)}")  # 100
    [](<#cb69-6>)
    [](<#cb69-7>)# Monitor에 로드
    [](<#cb69-8>)monitor = PerformanceMonitor()
    [](<#cb69-9>)for task in tasks:
    [](<#cb69-10>)    monitor.record_task(task)
    [](<#cb69-11>)
    [](<#cb69-12>)# 리포트 확인
    [](<#cb69-13>)monitor.print_report()
```

### run_demo()

데모 데이터를 생성하고 평가를 실행합니다.

**⚠️ 주의** : 이 함수는 내부 함수이며 직접 export되지 않습니다. 완전한 경로로 import해야 합니다.
```python
    [](<#cb70-1>)from agent_evaluator.core.agent_evaluator import run_demo
    [](<#cb70-2>)
    [](<#cb70-3>)monitor = run_demo(
    [](<#cb70-4>)    num_tasks: int = 100,
    [](<#cb70-5>)    use_hybrid: bool = False
    [](<#cb70-6>)) -> Union[PerformanceMonitor, HybridPerformanceMonitor]
```

**파라미터** \- `num_tasks` (int): 생성할 작업 수 - `use_hybrid` (bool): 하이브리드 모니터 사용 여부

**반환값** \- `PerformanceMonitor` 또는 `HybridPerformanceMonitor`

**예제**
```json
    [](<#cb71-1>)# 기본 데모
    [](<#cb71-2>)monitor = run_demo()
    [](<#cb71-3>)
    [](<#cb71-4>)# 하이브리드 데모
    [](<#cb71-5>)monitor = run_demo(num_tasks=50, use_hybrid=True)
    [](<#cb71-6>)
    [](<#cb71-7>)# 리포트 확인
    [](<#cb71-8>)monitor.print_summary()
```

* * *

## 📟 5.3 터미널 출력 메서드

Agent Evaluator는 평가 결과를 터미널에서 즉시 확인할 수 있는 다양한 출력 메서드를 제공합니다. Dashboard를 실행하지 않고도 빠르게 결과를 분석할 수 있습니다.

### print_summary()

핵심 메트릭을 간략하게 요약하여 출력합니다.

**시그니처**
```python
    [](<#cb-psummary-1>)def print_summary(self, report: EvaluationReport) -> None
```

**파라미터**

  * `report` (EvaluationReport): `generate_report()`로 생성된 리포트 객체

**예제**
```python
    [](<#cb-ps-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb-ps-2>)
    [](<#cb-ps-3>)monitor = PerformanceMonitor()
    [](<#cb-ps-4>)# ... Agent 평가 수행 ...
    [](<#cb-ps-5>)
    [](<#cb-ps-6>)# 요약 출력
    [](<#cb-ps-7>)report = monitor.generate_report()
    [](<#cb-ps-8>)monitor.print_summary(report)
```

**출력 예시:**
```
    ========================================
             성능 요약 보고서
    ========================================
    
    📊 전체 작업 통계:
      - 총 작업 수: 100
      - 성공: 95 (95.0%)
      - 실패: 5 (5.0%)
    
    ✅ 정확도 메트릭:
      - TCR: 95.0%
      - 평균 Accuracy: 92.5%
      - Hallucination Rate: 2.3%
    
    ⚡ 효율성 메트릭:
      - 평균 Latency: 1.23초
      - P95 Latency: 2.45초
      - 평균 Token 사용량: 450 tokens
      - 총 비용: $0.23
    
    ========================================
```

### print_detailed_report()

모든 메트릭과 Layer별 상세 정보를 출력합니다.

**시그니처**
```python
    [](<#cb-pdetail-1>)def print_detailed_report(self, report: PerformanceReport) -> None
```

**파라미터**

  * `report` (PerformanceReport): `generate_report()`로 생성된 리포트 객체

**예제**
```python
    [](<#cb-pd-1>)report = monitor.generate_report()
    [](<#cb-pd-2>)monitor.print_detailed_report(report)
```

**출력 내용:**

  * 📊 작업 통계 (성공/실패/재시도 등)
  * ✅ Layer 1: Native Metrics (TCR, Accuracy, Latency, Tokens, Cost)
  * ⚙️ Layer 2: Agentic AI Metrics (Tool Selection, Agent Coordination, Workflow)
  * 🎯 Layer 3: Advanced Metrics (DeepEval, Ragas)

### compare_with_thresholds()

설정된 임계값과 실제 메트릭을 비교하여 Pass/Fail 상태를 반환합니다.

**시그니처**
```python
    [](<#cb-thresh-1>)def compare_with_thresholds(self) -> Dict[str, Dict[str, float]]
```

**반환값**

  * `Dict[str, Dict[str, float]]`: 각 메트릭별 비교 결과 
    * `status`: "pass" 또는 "fail"
    * `actual`: 실제 측정값
    * `threshold`: 임계값

**예제: Quality Gate 구현**
```python
    [](<#cb-th-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb-th-2>)
    [](<#cb-th-3>)monitor = PerformanceMonitor()
    [](<#cb-th-4>)monitor.thresholds = {
    [](<#cb-th-5>)    'tcr': 95.0,           # 최소 95% 완료율
    [](<#cb-th-6>)    'accuracy': 90.0,      # 최소 90% 정확도
    [](<#cb-th-7>)    'latency': 2.0,        # 최대 2초
    [](<#cb-th-8>)    'hallucination': 5.0,  # 최대 5% 환각률
    [](<#cb-th-9>)}
    [](<#cb-th-10>)
    [](<#cb-th-11>)# ... Agent 평가 수행 ...
    [](<#cb-th-12>)
    [](<#cb-th-13>)# 임계값 비교
    [](<#cb-th-14>)comparison = monitor.compare_with_thresholds()
    [](<#cb-th-15>)
    [](<#cb-th-16>)# 결과 출력
    [](<#cb-th-17>)for metric, result in comparison.items():
    [](<#cb-th-18>)    status = "✅ PASS" if result["status"] == "pass" else "❌ FAIL"
    [](<#cb-th-19>)    print(f"{status} {metric}: {result['actual']:.2f} (임계값: {result['threshold']:.2f})")
    [](<#cb-th-20>)
    [](<#cb-th-21>)# CI/CD용: 전체 Pass/Fail 판정
    [](<#cb-th-22>)all_passed = all(r["status"] == "pass" for r in comparison.values())
    [](<#cb-th-23>)if not all_passed:
    [](<#cb-th-24>)    print("❌ Quality Gate Failed!")
    [](<#cb-th-25>)    exit(1)
```

**출력 예시:**
```
    ✅ PASS tcr: 95.00 (임계값: 95.00)
    ✅ PASS accuracy: 92.50 (임계값: 90.00)
    ✅ PASS latency: 1.23 (임계값: 2.00)
    ✅ PASS hallucination: 2.30 (임계값: 5.00)
```

### 커스텀 터미널 출력

Report 객체에서 직접 데이터를 추출하여 커스텀 출력을 만들 수 있습니다.
```python
    [](<#cb-cu-1>)report = monitor.generate_report()
    [](<#cb-cu-2>)
    [](<#cb-cu-3>)# Layer 1 메트릭 직접 접근
    [](<#cb-cu-4>)print(f"TCR: {report.accuracy_metrics['tcr']['tcr']:.1f}%")
    [](<#cb-cu-5>)print(f"Accuracy: {report.accuracy_metrics['accuracy_scores']['overall_accuracy']:.2f}%")
    [](<#cb-cu-6>)print(f"Latency: {report.efficiency_metrics['latency']['average']:.2f}s")
    [](<#cb-cu-7>)print(f"Cost: ${report.efficiency_metrics['tokens']['total_cost']:.4f}")
    [](<#cb-cu-8>)
    [](<#cb-cu-9>)# Layer 2 메트릭 (있는 경우)
    [](<#cb-cu-10>)if 'tool_selection' in report.agentic_metrics:
    [](<#cb-cu-11>)    print(f"Tool Selection: {report.agentic_metrics['tool_selection']['accuracy']:.1f}%")
    [](<#cb-cu-12>)
    [](<#cb-cu-13>)# JSON 출력 (자동화/통합용)
    [](<#cb-cu-14>)import json
    [](<#cb-cu-15>)print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
```

#### 💡 터미널 출력 활용 시나리오

  * **개발 중** : `print_summary()`로 빠른 피드백
  * **디버깅** : `print_detailed_report()`로 심층 분석
  * **CI/CD** : `compare_with_thresholds()`로 자동 품질 게이트
  * **통합** : JSON 출력으로 모니터링 시스템 연동
  * **프로덕션** : 임계값 기반 알림 트리거

### print_metric_breakdown() 🆕

평가 지표의 계산 과정을 단계별로 공개하여 완전한 투명성을 제공합니다.

**시그니처**
```python
    [](<#cb-bd-1>)def print_metric_breakdown(
    [](<#cb-bd-2>)    self,
    [](<#cb-bd-3>)    task_id: str = None,
    [](<#cb-bd-4>)    verbose: bool = True
    [](<#cb-bd-5>)) -> None
```

**파라미터**

  * `task_id` (str, optional): 특정 작업 ID. None이면 전체 통합 분석
  * `verbose` (bool): True이면 단계별 계산 과정 포함

**특징**

  * 📝 각 메트릭의 계산 수식 공개
  * 🔢 중간 계산값 표시
  * ✅ TCR, Accuracy, Latency, Cost 투명성
  * 💰 Token 비용 상세 계산 과정

**예제 1: 특정 작업 분석**
```python
    [](<#cb-bd-e1-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb-bd-e1-2>)
    [](<#cb-bd-e1-3>)monitor = PerformanceMonitor()
    [](<#cb-bd-e1-4>)# ... 작업 기록 ...
    [](<#cb-bd-e1-5>)
    [](<#cb-bd-e1-6>)# 특정 작업의 계산 과정 확인
    [](<#cb-bd-e1-7>)monitor.print_metric_breakdown(task_id="task_001", verbose=True)
```

**출력 예시 (특정 작업):**
```
    ================================================================================
            평가 지표 계산 과정 (Metric Calculation Breakdown)
    ================================================================================
    
    🔍 Task ID: task_001
       Task Type: qa
       Timestamp: 2025-12-10 12:00:00
    
    📊 1. Task Completion Rate (TCR) 계산
    ────────────────────────────────────────────────────────────────────────────────
       Completion Score: 0.850
    
       📝 계산 방법:
          - success=True이고 completion_score >= 0.7  → Full Success
          - success=True이고 completion_score < 0.7   → Partial Success
          - success=False                              → Failure
    
       ✅ 이 작업: Full Success (completion_score >= 0.7)
    
    📊 2. Accuracy Score 계산
    ────────────────────────────────────────────────────────────────────────────────
       Accuracy Score: 0.925
    
       📝 계산 방법 (4가지 유사도 메트릭 조합):
          1. Token Overlap Ratio (40% 가중치)
          2. Jaccard Similarity   (30% 가중치)
          3. LCS Similarity       (20% 가중치)
          4. Character Similarity (10% 가중치)
    
       ℹ️  이 점수는 응답과 정답(ground truth) 간 유사도를 측정합니다.
    
    📊 4. Token Usage & Cost
    ────────────────────────────────────────────────────────────────────────────────
       Input Tokens:  350
       Output Tokens: 150
       Total Tokens:  500
    
       📝 비용 계산:
          Input Cost  = 350 tokens × $0.003/1M = $0.000001
          Output Cost = 150 tokens × $0.015/1M = $0.000002
          Total Cost  = $0.000003
```

**예제 2: 전체 통합 분석**
```python
    [](<#cb-bd-e2-1>)# 전체 작업 통합 분석
    [](<#cb-bd-e2-2>)monitor.print_metric_breakdown(verbose=True)
```

**출력 예시 (전체 통합):**
```
    ================================================================================
            평가 지표 계산 과정 (Metric Calculation Breakdown)
    ================================================================================
    
    📊 전체 작업 통합 분석
    
    1️⃣ Task Completion Rate (TCR)
    ────────────────────────────────────────────────────────────────────────────────
       Total Tasks: 100
       Full Success: 85 (85.0%)
       Partial Success: 10 (10.0%)
       Failures: 5 (5.0%)
    
       📝 TCR 계산식:
          TCR = (Full Success × 1.0 + Partial Success × 0.5) / Total Tasks × 100
          TCR = (85 × 1.0 + 10 × 0.5) / 100 × 100
          TCR = 90.00%
    
    4️⃣ Token Usage & Cost
    ────────────────────────────────────────────────────────────────────────────────
       Total Input Tokens: 35,000
       Total Output Tokens: 15,000
       Total Tokens: 50,000
       Total Cost: $0.3300
    
       📝 비용 계산식:
          Input Cost  = 35,000 × $0.003/1M
          Output Cost = 15,000 × $0.015/1M
          Total Cost  = Input Cost + Output Cost
```

### explain_metric() 🆕

특정 메트릭의 계산 방법, 해석 가이드, 투명성 정보를 상세히 설명합니다.

**시그니처**
```python
    [](<#cb-ex-1>)def explain_metric(self, metric_name: str) -> None
```

**파라미터**

  * `metric_name` (str): 설명할 메트릭 이름 
    * `tcr`: Task Completion Rate
    * `accuracy`: Accuracy Score
    * `latency`: 응답 시간
    * `cost`: Token 비용
    * `hallucination`: 환각 발생률

**특징**

  * 🎯 메트릭의 목적과 의미
  * 🧮 수식과 알고리즘 상세 설명
  * 📊 해석 가이드 (점수별 의미)
  * 🔍 투명성 노트 (소스 코드 위치, 조정 가능 여부)

**예제 1: TCR 설명**
```python
    [](<#cb-ex-e1-1>)monitor.explain_metric("tcr")
```

**출력 예시:**
```
    ================================================================================
       📖 Task Completion Rate (TCR) - 상세 설명
    ================================================================================
    
    🎯 목적
    ────────────────────────────────────────────────────────────────────────────────
    작업의 완료 여부와 완료 품질을 측정합니다.
    
    🧮 계산 방법
    ────────────────────────────────────────────────────────────────────────────────
    
        1. 각 작업을 3가지 범주로 분류:
           - Full Success: success=True and completion_score >= 0.7
           - Partial Success: success=True and completion_score < 0.7
           - Failure: success=False
    
        2. 가중 평균 계산:
           TCR = (Full Success × 1.0 + Partial Success × 0.5) / Total Tasks × 100
    
    📊 해석 가이드
    ────────────────────────────────────────────────────────────────────────────────
    
        - 95% 이상: 우수 (Industry Benchmark)
        - 90-95%: 양호
        - 80-90%: 개선 필요
        - 80% 미만: 긴급 개선 필요
    
    🔍 투명성 노트
    ────────────────────────────────────────────────────────────────────────────────
    
        - completion_score는 응답 길이, 에러 여부, ground truth 유사도 기반
        - 기준값(0.7)은 조정 가능
        - 전체 계산 로직은 TaskCompletionTracker.calculate_tcr()에 공개
```

**예제 2: Accuracy 설명**
```python
    [](<#cb-ex-e2-1>)monitor.explain_metric("accuracy")
```

**출력 내용:**

  * 4가지 유사도 메트릭 조합 설명
  * Token Overlap (40%), Jaccard (30%), LCS (20%), Character (10%) 가중치
  * 점수 해석 가이드 (90% 이상 = 매우 정확)
  * 각 알고리즘 구현 위치 (taskresult_helpers.py)

#### 🔍 투명성 강화의 핵심 가치

Agent Evaluator의 투명성 메서드는 "블랙박스" 평가를 "화이트박스" 평가로 전환합니다:

  * **신뢰성** : 모든 계산 과정이 공개되어 결과를 신뢰할 수 있습니다
  * **교육성** : 각 메트릭의 의미와 계산 방법을 학습할 수 있습니다
  * **검증성** : 중간 계산값을 확인하여 결과를 검증할 수 있습니다
  * **조정성** : 소스 코드 위치를 알려주어 필요 시 수정 가능합니다

* * *

### 5.5 Context Managers

**🔄 신규** : 자동 저장 및 예외 처리를 제공하는 Context Manager 패턴

  * ✅ **자동 저장** : with 블록 종료 시 자동으로 결과 저장
  * ✅ **예외 안전** : 오류 발생 시에도 결과 파일 저장
  * ✅ **코드 간소화** : try-finally 블록 불필요
  * ✅ **전체 리포트 자동 포함** : Dashboard 호환 형식 자동 생성

#### evaluation_session()

**시그니처:**
```python
    def evaluation_session(
        filename: str,
        enable_security: bool = False,
        security_config: Optional[Dict] = None
    ) -> PerformanceMonitor
```

**사용 예제:**
```python
    from agent_evaluator import evaluation_session, create_taskresult
    
    # with 블록 종료 시 자동 저장
    with evaluation_session("results.json", enable_security=True) as monitor:
        # 평가 코드 작성
        for i in range(10):
            task = create_taskresult(
                task_id=f"task_{i}",
                question=f"Question {i}",
                response=f"Answer {i}",
                ground_truth=f"Truth {i}",
                execution_time=1.0
            )
            monitor.record_task(task)
    
        # with 블록 종료 시 자동으로 results.json에 저장!
    
    # 예외 발생 시에도 결과 저장됨
```

#### hybrid_evaluation_session()

**시그니처:**
```python
    def hybrid_evaluation_session(
        filename: str,
        use_deepeval: bool = False,
        use_ragas: bool = False
    ) -> HybridPerformanceMonitor
```

**사용 예제:**
```python
    from agent_evaluator import hybrid_evaluation_session
    
    # Layer 3 평가 포함 (DeepEval)
    with hybrid_evaluation_session(
        "hybrid_results.json",
        use_deepeval=True
    ) as monitor:
        # HybridPerformanceMonitor로 고급 평가 수행
        results = monitor.evaluate_with_golden_dataset(
            agent_fn=my_agent,
            dataset_path="dataset.json",
            enable_layer2_metrics=True
        )
```

* * *

### 5.6 LLM 통합 헬퍼

**🤖 신규** : LLM 호출, 평가, 기록을 한 줄로 처리하는 통합 헬퍼

  * ✅ **한 줄 평가** : LLM 호출 + 평가 + 자동 기록
  * ✅ **Batch 지원** : 대량 평가 최적화
  * ✅ **자동 오류 처리** : API 오류 자동 처리 및 재시도
  * ✅ **다중 제공자** : OpenAI, Anthropic(Claude) 지원

#### LLMHelper (OpenAI)

**Import:**
```python
    from agent_evaluator import PerformanceMonitor, LLMHelper
```

**사용 예제:**
```python
    from agent_evaluator import PerformanceMonitor, LLMHelper
    
    monitor = PerformanceMonitor()
    llm_helper = LLMHelper(monitor)
    
    # 🔥 한 줄로 LLM 호출 + 평가 + 기록!
    task = llm_helper.evaluate_openai_call(
        task_id="qa_001",
        prompt="What is the capital of France?",
        ground_truth="Paris",
        model="gpt-4o-mini"
    )
    
    print(f"Answer: {task.response}")
    print(f"Accuracy: {task.accuracy_score:.2f}")
    # 자동으로 monitor에 기록됨!
    
    # Batch 평가
    tasks = [
        {"task_id": "qa_001", "prompt": "Question 1", "ground_truth": "Answer 1"},
        {"task_id": "qa_002", "prompt": "Question 2", "ground_truth": "Answer 2"},
    ]
    results = llm_helper.evaluate_batch_openai_calls(tasks, model="gpt-4o-mini")
    
    # 결과 저장
    monitor.save_to_file("llm_eval_results.json")
```

#### ClaudeHelper (Anthropic)

**Import:**
```python
    from agent_evaluator import PerformanceMonitor, ClaudeHelper
```

**사용 예제:**
```python
    from agent_evaluator import PerformanceMonitor, ClaudeHelper
    
    monitor = PerformanceMonitor()
    claude_helper = ClaudeHelper(monitor)
    
    # Claude API 사용
    task = claude_helper.evaluate_claude_call(
        task_id="qa_001",
        prompt="Explain quantum computing",
        ground_truth="Quantum computing uses quantum bits...",
        model="claude-3-5-sonnet-20241022"
    )
    
    print(f"Response: {task.response}")
    print(f"Tokens: {task.tokens_used['total']}")
```

* * *

### 5.7 ExampleRunner

**📦 신규** : 예제 파일 작성을 위한 표준화된 베이스 클래스

  * ✅ **일관된 형식** : 모든 예제에 동일한 출력 형식 적용
  * ✅ **파일명 자동 생성** : Prefix + suffix 자동 조합
  * ✅ **Dashboard 안내** : 결과 확인 방법 자동 출력
  * ✅ **의존성 체크** : 필요한 라이브러리 자동 확인

#### 기본 사용법

**Import:**
```python
    from agent_evaluator import ExampleRunner, PerformanceMonitor, create_taskresult
```

**사용 예제:**
```python
    from agent_evaluator import ExampleRunner, PerformanceMonitor, create_taskresult
    
    def main(runner: ExampleRunner):
        """예제 실행 함수"""
        monitor = PerformanceMonitor()
    
        # 평가 수행
        for i in range(5):
            task = create_taskresult(
                task_id=f"task_{i}",
                question=f"Question {i}",
                response=f"Answer {i}",
                ground_truth=f"Truth {i}",
                execution_time=1.0
            )
            monitor.record_task(task)
    
        # 🔥 save_and_finish()가 자동으로:
        # - 파일명 prefix 추가 ([L1-01]_demo_results.json)
        # - 전체 리포트 포함
        # - Dashboard 안내 출력
        runner.save_and_finish(
            monitor=monitor,
            filename_suffix="demo_results",
            dashboard_tabs=["📊 Overview", "🔒 Security"]
        )
    
    if __name__ == "__main__":
        runner = ExampleRunner(
            example_id="01",
            level=1,
            title="데모 예제",
            required_libs=[],
            requires_api_key=False
        )
        runner.run(lambda: main(runner))
```

**주요 메서드:**

  * `save_and_finish(monitor, filename_suffix, dashboard_tabs)`: 결과 저장 및 Dashboard 안내
  * `run(func)`: 예제 함수 실행 (오류 처리 포함)
  * `check_dependencies()`: 필요한 라이브러리 확인

* * *

## 🔌 6. 프레임워크 통합 (v0.5.2)

#### 5.4 보안 헬퍼 함수

**📝 설명**

입력 검증, 출력 유출 검사, 도구 권한 검증을 위한 헬퍼 함수들입니다.

**Import:**
```python
    [](<#cb_helper1-1>)from agent_evaluator.helpers import (
    [](<#cb_helper1-2>)    validate_input_security,
    [](<#cb_helper1-3>)    check_output_leakage,
    [](<#cb_helper1-4>)    validate_tool_authorization
    [](<#cb_helper1-5>))
```

##### validate_input_security()

**시그니처:**
```python
    [](<#cb_helper2-1>)def validate_input_security(input_text: str) -> Dict[str, Any]
```

**사용 예제:**
```python
    [](<#cb_helper3-1>)from agent_evaluator.helpers import validate_input_security
    [](<#cb_helper3-2>)
    [](<#cb_helper3-3>)# SQL Injection 시도 검사
    [](<#cb_helper3-4>)user_input = "SELECT * FROM users WHERE '1'='1'"
    [](<#cb_helper3-5>)result = validate_input_security(user_input)
    [](<#cb_helper3-6>)
    [](<#cb_helper3-7>)print(result)
    [](<#cb_helper3-8>)# {
    [](<#cb_helper3-9>)#     'is_safe': False,
    [](<#cb_helper3-10>)#     'risk_level': 'high',
    [](<#cb_helper3-11>)#     'threats_detected': ['sql_injection'],
    [](<#cb_helper3-12>)#     'threat_details': [{'type': 'sql_injection', 'severity': 'high'}],
    [](<#cb_helper3-13>)#     'input_length': 38
    [](<#cb_helper3-14>)# }
    [](<#cb_helper3-15>)
    [](<#cb_helper3-16>)# 안전한 입력인 경우
    [](<#cb_helper3-17>)safe_input = "What is the capital of Korea?"
    [](<#cb_helper3-18>)result = validate_input_security(safe_input)
    [](<#cb_helper3-19>)print(result['is_safe'])  # True
```

##### check_output_leakage()

**시그니처:**
```python
    [](<#cb_helper4-1>)def check_output_leakage(output_text: str) -> Dict[str, Any]
```

**사용 예제:**
```python
    [](<#cb_helper5-1>)from agent_evaluator.helpers import check_output_leakage
    [](<#cb_helper5-2>)
    [](<#cb_helper5-3>)# API Key 유출 검사
    [](<#cb_helper5-4>)output = "The API key is sk-1234567890abcdefghijklmnopqrstuvwxyz"
    [](<#cb_helper5-5>)result = check_output_leakage(output)
    [](<#cb_helper5-6>)
    [](<#cb_helper5-7>)print(result)
    [](<#cb_helper5-8>)# {
    [](<#cb_helper5-9>)#     'has_leakage': True,
    [](<#cb_helper5-10>)#     'severity': 'critical',
    [](<#cb_helper5-11>)#     'leakage_types': ['api_key'],
    [](<#cb_helper5-12>)#     'leakage_count': 1,
    [](<#cb_helper5-13>)#     'details': [{'type': 'api_key', 'subtype': 'openai_api_key', 'count': 1}]
    [](<#cb_helper5-14>)# }
    [](<#cb_helper5-15>)
    [](<#cb_helper5-16>)# CI/CD 통합 예제
    [](<#cb_helper5-17>)if result['severity'] == 'critical':
    [](<#cb_helper5-18>)    raise SecurityError("Critical data leakage detected!")
```

##### validate_tool_authorization()

**시그니처:**
```python
    [](<#cb_helper6-1>)def validate_tool_authorization(
    [](<#cb_helper6-2>)    tool_name: str,
    [](<#cb_helper6-3>)    tool_params: Dict[str, Any],
    [](<#cb_helper6-4>)    allowed_tools: Optional[List[str]] = None,
    [](<#cb_helper6-5>)    restricted_tools: Optional[List[str]] = None
    [](<#cb_helper6-6>)) -> Dict[str, Any]
```

**사용 예제:**
```python
    [](<#cb_helper7-1>)from agent_evaluator.helpers import validate_tool_authorization
    [](<#cb_helper7-2>)
    [](<#cb_helper7-3>)# 도구 권한 검증
    [](<#cb_helper7-4>)result = validate_tool_authorization(
    [](<#cb_helper7-5>)    tool_name='execute_command',
    [](<#cb_helper7-6>)    tool_params={'command': 'rm -rf /'},
    [](<#cb_helper7-7>)    allowed_tools=['search', 'calculator'],
    [](<#cb_helper7-8>)    restricted_tools=['execute_command', 'delete_file']
    [](<#cb_helper7-9>))
    [](<#cb_helper7-10>)
    [](<#cb_helper7-11>)print(result)
    [](<#cb_helper7-12>)# {
    [](<#cb_helper7-13>)#     'is_authorized': False,
    [](<#cb_helper7-14>)#     'violation_type': 'restricted_tool',
    [](<#cb_helper7-15>)#     'risk_level': 'high',
    [](<#cb_helper7-16>)#     'reason': "Tool 'execute_command' is restricted",
    [](<#cb_helper7-17>)#     'dangerous_params': []
    [](<#cb_helper7-18>)# }
    [](<#cb_helper7-19>)
    [](<#cb_helper7-20>)# Agent 실행 전 검증
    [](<#cb_helper7-21>)if not result['is_authorized']:
    [](<#cb_helper7-22>)    raise PermissionError(result['reason'])
```

* * *

Agent Evaluator v0.5.2은 CrewAI, LangChain, LangGraph, AutoGen 등 주요 AI 프레임워크에 대한 고급 통합 기능을 제공합니다. 모든 통합은 **Layer 1/2/3 메트릭을 완전히 지원** 하며, 동적 계산 및 자동 추적 기능을 갖추고 있습니다.

### 주요 특징

  * ✅ **Layer 1 완전 지원** : TCR, Accuracy, Latency, Token Usage 등 7개 네이티브 메트릭 자동 계산
  * ✅ **Layer 2 자동 추적** : Tool Selection, Agent Coordination, Workflow Execution 자동 추적
  * ✅ **Layer 3 통합** : Hallucination Detection, RAGAS 메트릭 등 고급 평가
  * ✅ **Zero Configuration** : 최소한의 설정으로 즉시 사용 가능
  * ✅ **보고서 생성** : 통합된 평가 보고서 자동 생성
  * ✅ **Golden Dataset 지원** : Ground truth 기반 평가

### 6.1 CrewAIEvaluator

CrewAI 프레임워크에 대한 고급 평가 클래스입니다.

#### 초기화
```python
    [](<#cb72-1>)from agent_evaluator.integrations import CrewAIEvaluator
    [](<#cb72-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb72-3>)
    [](<#cb72-4>)# Crew 생성
    [](<#cb72-5>)crew = Crew(agents=[agent1, agent2], tasks=[task1, task2])
    [](<#cb72-6>)
    [](<#cb72-7>)# 평가 래퍼 생성
    [](<#cb72-8>)evaluator = CrewAIEvaluator(
    [](<#cb72-9>)    crew=crew,
    [](<#cb72-10>)    monitor=PerformanceMonitor(),
    [](<#cb72-11>)    enable_layer2=True,
    [](<#cb72-12>)    enable_layer3=False,
    [](<#cb72-13>)    verbose=True
    [](<#cb72-14>))
```

#### 주요 메서드

##### kickoff()

Crew를 실행하고 평가를 수행합니다.
```python
    [](<#cb73-1>)result = evaluator.kickoff(
    [](<#cb73-2>)    inputs={"topic": "AI Agents"},
    [](<#cb73-3>)    ground_truth="Expected output...",
    [](<#cb73-4>)    expected_workflow_steps=["research", "write"]
    [](<#cb73-5>))
```

##### generate_report()

평가 보고서를 생성합니다.
```python
    [](<#cb74-1>)report = evaluator.generate_report(output_path="crewai_report.json")
    [](<#cb74-2>)
    [](<#cb74-3>)# 출력 예시:
    [](<#cb74-4>)# 🔹 Layer 1: Native Metrics
    [](<#cb74-5>)#    TCR: 95.0%
    [](<#cb74-6>)#    Accuracy: 88.5%
    [](<#cb74-7>)#    Avg Latency: 2.34s
    [](<#cb74-8>)# 🔹 Layer 2: Agentic AI Metrics
    [](<#cb74-9>)#    Agent Coordination Rate: 92.0%
    [](<#cb74-10>)#    Workflow Execution Score: 90.0%
```

##### Manual Tracking APIs

수동으로 메트릭을 기록할 수 있습니다.
```python
    [](<#cb75-1>)# 워크플로우 단계 추적
    [](<#cb75-2>)evaluator.track_workflow_step(step_name="research", success=True, duration=1.5)
    [](<#cb75-3>)
    [](<#cb75-4>)# 에이전트 상호작용 추적
    [](<#cb75-5>)evaluator.track_agent_interaction(from_agent="researcher", to_agent="writer")
    [](<#cb75-6>)
    [](<#cb75-7>)# 도구 사용 추적
    [](<#cb75-8>)evaluator.track_tool_usage(tool_name="web_search", success=True, duration=0.8)
```

#### 편의 함수
```python
    [](<#cb76-1>)from agent_evaluator.integrations import create_evaluated_crew
    [](<#cb76-2>)
    [](<#cb76-3>)evaluator = create_evaluated_crew(
    [](<#cb76-4>)    crew=crew,
    [](<#cb76-5>)    enable_layer2=True
    [](<#cb76-6>))
```

* * *

### 6.2 LangChainEvaluator

LangChain 프레임워크에 대한 고급 평가 클래스입니다.

#### 초기화
```python
    [](<#cb77-1>)from agent_evaluator.integrations import LangChainEvaluator
    [](<#cb77-2>)
    [](<#cb77-3>)# LangChain 에이전트 생성
    [](<#cb77-4>)agent = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION)
    [](<#cb77-5>)
    [](<#cb77-6>)# 평가 래퍼 생성
    [](<#cb77-7>)evaluator = LangChainEvaluator(
    [](<#cb77-8>)    agent=agent,
    [](<#cb77-9>)    enable_layer2=True,
    [](<#cb77-10>)    enable_layer3=False
    [](<#cb77-11>))
```

#### 주요 메서드

##### run()

에이전트를 실행하고 평가를 수행합니다.
```python
    [](<#cb78-1>)result = evaluator.run(
    [](<#cb78-2>)    query="What is the weather in Tokyo?",
    [](<#cb78-3>)    ground_truth="Expected answer...",
    [](<#cb78-4>)    expected_tools=["weather_api", "search"]
    [](<#cb78-5>))
```

##### generate_report()
```python
    [](<#cb79-1>)report = evaluator.generate_report(output_path="langchain_report.json")
    [](<#cb79-2>)
    [](<#cb79-3>)# 출력 예시:
    [](<#cb79-4>)# 🔹 Layer 1: Native Metrics
    [](<#cb79-5>)#    TCR: 93.0%
    [](<#cb79-6>)#    Avg Latency: 1.87s
    [](<#cb79-7>)# 🔹 Layer 2: Agentic AI Metrics
    [](<#cb79-8>)#    Tool Selection Accuracy: 85.0%
    [](<#cb79-9>)#    Workflow Execution Score: 88.0%
```

#### 고급 콜백 핸들러

직접 콜백을 사용하려면:
```python
    [](<#cb80-1>)from agent_evaluator.integrations import AdvancedLangChainCallback
    [](<#cb80-2>)
    [](<#cb80-3>)callback = AdvancedLangChainCallback(
    [](<#cb80-4>)    monitor=monitor,
    [](<#cb80-5>)    expected_tools=["search"],
    [](<#cb80-6>)    ground_truth="Expected..."
    [](<#cb80-7>))
    [](<#cb80-8>)
    [](<#cb80-9>)agent.run(query, callbacks=[callback])
```

* * *

### 6.3 LangGraphEvaluator

LangGraph 워크플로우에 대한 고급 평가 클래스입니다.

#### 초기화 및 사용
```python
    [](<#cb81-1>)from agent_evaluator.integrations import LangGraphEvaluator
    [](<#cb81-2>)
    [](<#cb81-3>)# 평가 래퍼 생성
    [](<#cb81-4>)evaluator = LangGraphEvaluator(
    [](<#cb81-5>)    enable_layer2=True
    [](<#cb81-6>))
    [](<#cb81-7>)
    [](<#cb81-8>)# 노드 추가 (자동으로 평가가 래핑됨)
    [](<#cb81-9>)evaluator.add_node("process", process_function)
    [](<#cb81-10>)evaluator.add_node("analyze", analyze_function)
    [](<#cb81-11>)
    [](<#cb81-12>)# 엣지 추가
    [](<#cb81-13>)evaluator.add_edge("start", "process")
    [](<#cb81-14>)evaluator.add_edge("process", "analyze")
    [](<#cb81-15>)evaluator.add_edge("analyze", "end")
    [](<#cb81-16>)
    [](<#cb81-17>)# 실행
    [](<#cb81-18>)result = evaluator.run(
    [](<#cb81-19>)    initial_state={"messages": []},
    [](<#cb81-20>)    ground_truth="Expected...",
    [](<#cb81-21>)    expected_workflow_steps=["process", "analyze"]
    [](<#cb81-22>))
```

#### 자동 워크플로우 추적

LangGraphEvaluator는 각 노드의 실행을 자동으로 추적하여 Layer 2 메트릭을 계산합니다:

  * 각 노드의 성공/실패 상태
  * 각 노드의 실행 시간
  * 전체 워크플로우 실행 성공률
  * 단계별 오류 추적

* * *

### 6.4 AutoGenEvaluator

AutoGen 에이전트에 대한 고급 평가 클래스입니다.

#### 초기화 및 사용
```python
    [](<#cb82-1>)from agent_evaluator.integrations import AutoGenEvaluator
    [](<#cb82-2>)from autogen import AssistantAgent, UserProxyAgent
    [](<#cb82-3>)
    [](<#cb82-4>)# AutoGen 에이전트 생성
    [](<#cb82-5>)assistant = AssistantAgent(
    [](<#cb82-6>)    name="assistant",
    [](<#cb82-7>)    llm_config={"model": "gpt-4"}
    [](<#cb82-8>))
    [](<#cb82-9>)
    [](<#cb82-10>)# 평가 래퍼 생성
    [](<#cb82-11>)evaluator = AutoGenEvaluator(
    [](<#cb82-12>)    agent=assistant,
    [](<#cb82-13>)    enable_layer2=True
    [](<#cb82-14>))
    [](<#cb82-15>)
    [](<#cb82-16>)# evaluator.agent를 일반 에이전트처럼 사용
    [](<#cb82-17>)user_proxy.initiate_chat(evaluator.agent, message="Hello")
    [](<#cb82-18>)
    [](<#cb82-19>)# 보고서 생성
    [](<#cb82-20>)report = evaluator.generate_report()
```

#### 자동 에이전트 상호작용 추적

AutoGenEvaluator는 에이전트 간의 메시지 교환을 자동으로 추적하여 Agent Coordination 메트릭을 계산합니다.

* * *

## 7\. 예외

### EvaluationError

평가 중 발생하는 일반적인 예외입니다.
```python
    [](<#cb72-1>)class EvaluationError(Exception):
    [](<#cb72-2>)    pass
```

**사용 예제**
```python
    [](<#cb73-1>)try:
    [](<#cb73-2>)    monitor.record_task(invalid_task)
    [](<#cb73-3>)except EvaluationError as e:
    [](<#cb73-4>)    print(f"평가 오류: {e}")
```

### MetricAdapterError

메트릭 어댑터 관련 예외입니다.
```python
    [](<#cb74-1>)class MetricAdapterError(Exception):
    [](<#cb74-2>)    pass
```

**사용 예제**
```json
    [](<#cb75-1>)try:
    [](<#cb75-2>)    adapter = DeepEvalAdapter()
    [](<#cb75-3>)    if not adapter.is_available():
    [](<#cb75-4>)        raise MetricAdapterError("DeepEval not available")
    [](<#cb75-5>)except MetricAdapterError as e:
    [](<#cb75-6>)    print(f"어댑터 오류: {e}")
```

* * *

## 8\. 전체 워크플로우 예제

### 기본 워크플로우 (수정된 버전)
```python
    [](<#cb76-1>)from agent_evaluator import (
    [](<#cb76-2>)    PerformanceMonitor,
    [](<#cb76-3>)    TaskResult,
    [](<#cb76-4>)    TaskType
    [](<#cb76-5>))
    [](<#cb76-6>)from datetime import datetime
    [](<#cb76-7>)
    [](<#cb76-8>)# 1. Monitor 초기화 (⚠️ thresholds 파라미터 없음)
    [](<#cb76-9>)monitor = PerformanceMonitor(
    [](<#cb76-10>)    pricing={"input": 0.003, "output": 0.015}
    [](<#cb76-11>))
    [](<#cb76-12>)
    [](<#cb76-13>)# 임계값은 별도로 설정
    [](<#cb76-14>)monitor.thresholds = {
    [](<#cb76-15>)    "tcr": 85.0,
    [](<#cb76-16>)    "accuracy": 80.0,
    [](<#cb76-17>)    "hallucination": 5.0
    [](<#cb76-18>)}
    [](<#cb76-19>)
    [](<#cb76-20>)# 2. 작업 실행 및 기록
    [](<#cb76-21>)for i in range(10):
    [](<#cb76-22>)    # 작업 수행 (사용자 정의 함수)
    [](<#cb76-23>)    result = perform_task(f"task_{i}")
    [](<#cb76-24>)
    [](<#cb76-25>)    # 결과 기록 (⚠️ tool_calls는 Dict 리스트!)
    [](<#cb76-26>)    task = TaskResult(
    [](<#cb76-27>)        task_id=f"task_{i}",
    [](<#cb76-28>)        task_type=TaskType.QA.value,
    [](<#cb76-29>)        success=result['success'],
    [](<#cb76-30>)        completion_score=result['completion_score'],
    [](<#cb76-31>)        accuracy_score=result['accuracy_score'],
    [](<#cb76-32>)        execution_time=result['execution_time'],
    [](<#cb76-33>)        tokens_used=result['tokens'],  # {"input": 100, "output": 200, "total": 300}
    [](<#cb76-34>)        tool_calls=[
    [](<#cb76-35>)            {"tool_name": tool, "success": True}
    [](<#cb76-36>)            for tool in result['tools']
    [](<#cb76-37>)        ],  # ⚠️ List[Dict]로 변환!
    [](<#cb76-38>)        attempts=result['attempts'],
    [](<#cb76-39>)        errors=result['errors'],
    [](<#cb76-40>)        timestamp=datetime.now()
    [](<#cb76-41>)    )
    [](<#cb76-42>)
    [](<#cb76-43>)    monitor.record_task(task)
    [](<#cb76-44>)
    [](<#cb76-45>)# 3. 리포트 생성 (⚠️ period 파라미터 없음)
    [](<#cb76-46>)report = monitor.generate_report()
    [](<#cb76-47>)
    [](<#cb76-48>)# 4. 결과 출력 (⚠️ print_report()로 변경됨)
    [](<#cb76-49>)monitor.print_report()
    [](<#cb76-50>)
    [](<#cb76-51>)# 5. 저장 (⚠️ 반환값 있음)
    [](<#cb76-52>)saved_path = monitor.save_to_file("test_results.json")
    [](<#cb76-53>)print(f"저장 완료: {saved_path}")
    [](<#cb76-54>)
    [](<#cb76-55>)# 6. 알림 확인 (⚠️ get_alerts() 없음, report.alerts 사용)
    [](<#cb76-56>)if report.alerts:
    [](<#cb76-57>)    print("\n⚠️  알림:")
    [](<#cb76-58>)    for alert in report.alerts:
    [](<#cb76-59>)        print(f"[{alert['severity'].upper()}] {alert['metric']}")
    [](<#cb76-60>)        print(f"  {alert['message']}")
    [](<#cb76-61>)        print(f"  조치: {alert['action']}\n")
    [](<#cb76-62>)
    [](<#cb76-63>)# 7. 비용 분석 (⚠️ get_cost_analysis() 없음)
    [](<#cb76-64>)cost_stats = monitor.token_tracker.get_usage_stats()
    [](<#cb76-65>)print(f"\n💰 비용 분석:")
    [](<#cb76-66>)print(f"  총 비용: ${cost_stats['total_cost']:.4f}")
    [](<#cb76-67>)print(f"  작업당 평균: ${cost_stats['avg_cost_per_task']:.4f}")
    [](<#cb76-68>)print(f"  예상 월간 비용: ${cost_stats['estimated_monthly_cost']:.2f}")
```

### 실전 예제: LangChain 에이전트 평가
```python
    [](<#cb77-1>)from agent_evaluator import PerformanceMonitor, TaskResult, TaskType
    [](<#cb77-2>)from datetime import datetime
    [](<#cb77-3>)from langchain.agents import AgentExecutor
    [](<#cb77-4>)from langchain.tools import Tool
    [](<#cb77-5>)
    [](<#cb77-6>)# Monitor 초기화
    [](<#cb77-7>)monitor = PerformanceMonitor(
    [](<#cb77-8>)    pricing={"input": 0.003, "output": 0.015}
    [](<#cb77-9>))
    [](<#cb77-10>)
    [](<#cb77-11>)# LangChain 에이전트 실행 및 평가
    [](<#cb77-12>)def evaluate_agent_task(agent: AgentExecutor, question: str, task_id: str):
    [](<#cb77-13>)    """LangChain 에이전트 실행 및 결과 평가"""
    [](<#cb77-14>)
    [](<#cb77-15>)    start_time = datetime.now()
    [](<#cb77-16>)
    [](<#cb77-17>)    try:
    [](<#cb77-18>)        # 에이전트 실행
    [](<#cb77-19>)        result = agent.invoke({"input": question})
    [](<#cb77-20>)
    [](<#cb77-21>)        end_time = datetime.now()
    [](<#cb77-22>)        execution_time = (end_time - start_time).total_seconds()
    [](<#cb77-23>)
    [](<#cb77-24>)        # 토큰 사용량 추출 (LangChain callback 사용)
    [](<#cb77-25>)        tokens_used = {
    [](<#cb77-26>)            "input": result.get("token_usage", {}).get("prompt_tokens", 0),
    [](<#cb77-27>)            "output": result.get("token_usage", {}).get("completion_tokens", 0),
    [](<#cb77-28>)            "total": result.get("token_usage", {}).get("total_tokens", 0)
    [](<#cb77-29>)        }
    [](<#cb77-30>)
    [](<#cb77-31>)        # 사용된 도구 추출 (⚠️ Dict 리스트로 변환)
    [](<#cb77-32>)        tool_calls = []
    [](<#cb77-33>)        for step in result.get("intermediate_steps", []):
    [](<#cb77-34>)            action, output = step
    [](<#cb77-35>)            tool_calls.append({
    [](<#cb77-36>)                "tool_name": action.tool,
    [](<#cb77-37>)                "success": True,
    [](<#cb77-38>)                "parameters": action.tool_input
    [](<#cb77-39>)            })
    [](<#cb77-40>)
    [](<#cb77-41>)        # TaskResult 생성
    [](<#cb77-42>)        task = TaskResult(
    [](<#cb77-43>)            task_id=task_id,
    [](<#cb77-44>)            task_type=TaskType.QA.value,
    [](<#cb77-45>)            success=True,
    [](<#cb77-46>)            completion_score=1.0,
    [](<#cb77-47>)            accuracy_score=0.95,  # 실제로는 평가 로직 필요
    [](<#cb77-48>)            execution_time=execution_time,
    [](<#cb77-49>)            tokens_used=tokens_used,
    [](<#cb77-50>)            tool_calls=tool_calls,
    [](<#cb77-51>)            attempts=1,
    [](<#cb77-52>)            errors=[],
    [](<#cb77-53>)            timestamp=end_time
    [](<#cb77-54>)        )
    [](<#cb77-55>)
    [](<#cb77-56>)        # 기록
    [](<#cb77-57>)        monitor.record_task(task)
    [](<#cb77-58>)
    [](<#cb77-59>)        return result["output"]
    [](<#cb77-60>)
    [](<#cb77-61>)    except Exception as e:
    [](<#cb77-62>)        end_time = datetime.now()
    [](<#cb77-63>)        execution_time = (end_time - start_time).total_seconds()
    [](<#cb77-64>)
    [](<#cb77-65>)        # 실패 케이스
    [](<#cb77-66>)        task = TaskResult(
    [](<#cb77-67>)            task_id=task_id,
    [](<#cb77-68>)            task_type=TaskType.QA.value,
    [](<#cb77-69>)            success=False,
    [](<#cb77-70>)            completion_score=0.0,
    [](<#cb77-71>)            accuracy_score=0.0,
    [](<#cb77-72>)            execution_time=execution_time,
    [](<#cb77-73>)            tokens_used={"input": 0, "output": 0, "total": 0},
    [](<#cb77-74>)            tool_calls=[],
    [](<#cb77-75>)            attempts=1,
    [](<#cb77-76>)            errors=[str(e)],
    [](<#cb77-77>)            timestamp=end_time
    [](<#cb77-78>)        )
    [](<#cb77-79>)
    [](<#cb77-80>)        monitor.record_task(task)
    [](<#cb77-81>)        raise
    [](<#cb77-82>)
    [](<#cb77-83>)# 사용 예
    [](<#cb77-84>)questions = [
    [](<#cb77-85>)    "What is the capital of France?",
    [](<#cb77-86>)    "Calculate 15% of 240",
    [](<#cb77-87>)    "What is the weather in New York?"
    [](<#cb77-88>)]
    [](<#cb77-89>)
    [](<#cb77-90>)for i, question in enumerate(questions):
    [](<#cb77-91>)    try:
    [](<#cb77-92>)        answer = evaluate_agent_task(agent, question, f"task_{i+1}")
    [](<#cb77-93>)        print(f"Q: {question}")
    [](<#cb77-94>)        print(f"A: {answer}\n")
    [](<#cb77-95>)    except Exception as e:
    [](<#cb77-96>)        print(f"Error: {e}\n")
    [](<#cb77-97>)
    [](<#cb77-98>)# 리포트 출력
    [](<#cb77-99>)monitor.print_report()
    [](<#cb77-100>)
    [](<#cb77-101>)# 저장
    [](<#cb77-102>)monitor.save_to_file("langchain_evaluation.json")
```

### 고급 워크플로우 (DeepEval + RAGAS)
```python
    [](<#cb78-1>)from hybrid_monitor import create_monitor
    [](<#cb78-2>)
    [](<#cb78-3>)# 1. 하이브리드 Monitor 생성
    [](<#cb78-4>)monitor = create_monitor(profile="rag")
    [](<#cb78-5>)
    [](<#cb78-6>)# 2. RAG 시스템 작업
    [](<#cb78-7>)query = "What is the capital of France?"
    [](<#cb78-8>)retrieved_docs = retriever.search(query)
    [](<#cb78-9>)answer = llm.generate(query, context=retrieved_docs)
    [](<#cb78-10>)
    [](<#cb78-11>)# 3. 기본 TaskResult 생성
    [](<#cb78-12>)task = TaskResult(
    [](<#cb78-13>)    task_id="rag_001",
    [](<#cb78-14>)    task_type=TaskType.INFORMATION_RETRIEVAL.value,
    [](<#cb78-15>)    success=True,
    [](<#cb78-16>)    completion_score=1.0,
    [](<#cb78-17>)    accuracy_score=0.95,
    [](<#cb78-18>)    execution_time=2.3,
    [](<#cb78-19>)    tokens_used={"input": 200, "output": 150, "total": 350},
    [](<#cb78-20>)    tool_calls=["retriever", "llm"],
    [](<#cb78-21>)    attempts=1,
    [](<#cb78-22>)    errors=[],
    [](<#cb78-23>)    timestamp=datetime.now()
    [](<#cb78-24>))
    [](<#cb78-25>)
    [](<#cb78-26>)# 4. 고급 평가와 함께 기록
    [](<#cb78-27>)monitor.record_task(
    [](<#cb78-28>)    task,
    [](<#cb78-29>)    enable_advanced_metrics=True,
    [](<#cb78-30>)    input_text=query,
    [](<#cb78-31>)    output_text=answer,
    [](<#cb78-32>)    expected_output="Paris",
    [](<#cb78-33>)    retrieved_context=[doc.content for doc in retrieved_docs],
    [](<#cb78-34>)    quality_criteria="""
    [](<#cb78-35>)    Answer should:
    [](<#cb78-36>)    1. Be accurate and factual
    [](<#cb78-37>)    2. Be based on retrieved context
    [](<#cb78-38>)    3. Be concise and clear
    [](<#cb78-39>)    """
    [](<#cb78-40>))
    [](<#cb78-41>)
    [](<#cb78-42>)# 5. 하이브리드 리포트 생성
    [](<#cb78-43>)hybrid_report = monitor.generate_hybrid_report()
    [](<#cb78-44>)
    [](<#cb78-45>)# 6. 네이티브 메트릭
    [](<#cb78-46>)print(f"TCR: {hybrid_report.tcr:.1f}%")
    [](<#cb78-47>)print(f"정확도: {hybrid_report.accuracy_metrics['accuracy_scores']['overall_accuracy']:.1f}%")
    [](<#cb78-48>)
    [](<#cb78-49>)# 7. DeepEval 메트릭
    [](<#cb78-50>)adv = hybrid_report.advanced_metrics_summary
    [](<#cb78-51>)if 'g_eval_score' in adv:
    [](<#cb78-52>)    print(f"G-Eval: {adv['g_eval_score']['mean']:.3f}")
    [](<#cb78-53>)if 'hallucination_detection' in adv:
    [](<#cb78-54>)    hall = adv['hallucination_detection']
    [](<#cb78-55>)    print(f"Hallucination Rate: {hall['rate']*100:.1f}%")
    [](<#cb78-56>)
    [](<#cb78-57>)# 8. RAGAS 메트릭
    [](<#cb78-58>)if 'ragas_faithfulness' in adv:
    [](<#cb78-59>)    print(f"Faithfulness: {adv['ragas_faithfulness']['mean']:.3f}")
    [](<#cb78-60>)if 'ragas_context_precision' in adv:
    [](<#cb78-61>)    print(f"Context Precision: {adv['ragas_context_precision']['mean']:.3f}")
    [](<#cb78-62>)if 'ragas_overall_score' in adv:
    [](<#cb78-63>)    print(f"RAGAS Overall: {adv['ragas_overall_score']['mean']:.3f}")
    [](<#cb78-64>)
    [](<#cb78-65>)# 9. 저장
    [](<#cb78-66>)monitor.save_to_file("rag_evaluation.json")
```

* * *

## 9\. 타입 힌트
```python
    [](<#cb79-1>)from typing import Optional, Dict, List, Any, Union
    [](<#cb79-2>)from datetime import datetime
    [](<#cb79-3>)
    [](<#cb79-4>)# 가격 설정 타입
    [](<#cb79-5>)PricingConfig = Dict[str, float]
    [](<#cb79-6>)# 예: {"input": 0.003, "output": 0.015}
    [](<#cb79-7>)
    [](<#cb79-8>)# 임계값 타입
    [](<#cb79-9>)ThresholdsConfig = Dict[str, float]
    [](<#cb79-10>)# 예: {"tcr": 80.0, "accuracy": 70.0}
    [](<#cb79-11>)
    [](<#cb79-12>)# 토큰 사용량 타입
    [](<#cb79-13>)TokenUsage = Dict[str, int]
    [](<#cb79-14>)# 예: {"input": 100, "output": 200, "total": 300}
    [](<#cb79-15>)
    [](<#cb79-16>)# 메트릭 데이터 타입
    [](<#cb79-17>)MetricData = Dict[str, Any]
    [](<#cb79-18>)# 예: {"mean": 0.85, "min": 0.5, "max": 1.0, "count": 10}
    [](<#cb79-19>)
    [](<#cb79-20>)# 알림 타입
    [](<#cb79-21>)Alert = Dict[str, str]
    [](<#cb79-22>)# 예: {"level": "high", "message": "TCR below threshold"}
```

* * *

## 참고 자료

  * [메트릭 가이드](<METRICS_GUIDE.md>): 모든 평가 지표 상세 설명
  * [프레임워크 통합 가이드](<FRAMEWORK_INTEGRATION.md>): CrewAI, AutoGen 등 통합
  * [배포 가이드](<13_DEPLOYMENT_GUIDE.md>): FastAPI 대시보드 배포 (`agent-eval serve`)
