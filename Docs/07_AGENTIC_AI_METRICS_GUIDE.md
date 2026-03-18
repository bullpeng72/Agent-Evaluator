# 🔬 고급 메트릭 가이드

Layer 2 & Layer 3 AI 품질 메트릭

# Agentic AI Metrics 완전 가이드

> 📚 Layer 2 메트릭의 모든 것 - Tool Selection, Tool Efficiency, Agent Coordination, Workflow Execution

## 📋 목차

  1. [Layer 2 메트릭 개요](<#layer-2-메트릭-개요>)
  2. [1\. Tool Selection Accuracy](<#tool-selection-accuracy>)
  3. [2\. Tool Efficiency](<#tool-efficiency>)
  4. [3\. Agent Coordination](<#agent-coordination>)
  5. [4\. Workflow Execution](<#workflow-execution>)
  6. [Framework 통합](<#framework-통합>)
     * [Context Manager 패턴](<#context-manager>)
     * [LLM 통합 헬퍼](<#llm-helpers>)
     * [간소화된 API](<#simplified-api>)
  7. [실전 예제](<#실전-예제>)
  8. [Golden Dataset 활용](<#golden-dataset-활용-1>)
  9. [Threshold 설정](<#threshold-설정>)
  10. [Best Practices](<#best-practices-3>)
  11. [Troubleshooting](<#troubleshooting>)
  12. [📊 품질 관리자 가이드 (QA Manager)](<#qa-품질-관리자-가이드>)
     * [1\. Layer 2 메트릭 품질 해석](<#qa-1-layer-2-메트릭-품질-해석>)
     * [2\. 임계값 설정 및 품질 기준](<#qa-2-임계값-설정-및-품질-기준>)
     * [3\. 배포 전 품질 체크리스트](<#qa-3-배포-전-품질-체크리스트>)
     * [4\. 문제 해결 시나리오](<#qa-4-문제-해결-시나리오>)
     * [5\. QA 관리자 핵심 원칙](<#qa-5-qa-관리자-핵심-원칙>)

* * *

## Layer 2 메트릭 개요

### 왜 Layer 2가 필요한가?

기존 Layer 1 (Native Metrics)은 개별 작업의 성능을 측정합니다:

  * TCR, Accuracy, Latency 등

하지만 **멀티 에이전트 시스템** 은 추가적인 평가가 필요합니다:

  * 에이전트가 올바른 도구를 선택하는가?
  * 에이전트들이 효과적으로 협업하는가?
  * 워크플로우가 효율적으로 실행되는가?

**Layer 2 메트릭** 은 이러한 고급 요구사항을 충족합니다.

### Layer 2 메트릭 구성

메트릭 | 측정 대상 | 주요 프레임워크 | 단위 | 구현 클래스  
---|---|---|---|---  
**Tool Selection Accuracy** | 도구 선택 정확도 | LangChain, AutoGen | % | `ToolSelectionTracker`  
**Tool Efficiency** | 도구 실행 효율성 | 모든 프레임워크 | % | `ToolCallAnalyzer`  
**Agent Coordination** | 에이전트 협업 품질 | CrewAI, AutoGen | 0-10 척도 | `AgentCoordinationTracker`  
**Workflow Execution** | 워크플로우 성공률 | LangChain, LangGraph | % | `WorkflowExecutionTracker`  
  
### 각 메트릭의 핵심 메서드

**ToolSelectionTracker** :

  * `evaluate_selection()`: 도구 선택 평가 (Precision, Recall, F1 계산)
  * `get_accuracy_stats()`: 전체 평가 통계 조회

**AgentCoordinationTracker** :

  * `track_interaction()`: 에이전트 간 상호작용 추적
  * `calculate_coordination_score()`: 협업 점수 계산 (0-10 척도)
  * `get_delegation_success_rate()`: 위임 성공률 계산

**WorkflowExecutionTracker** :

  * `track_step()`: 워크플로우 단계 추적
  * `calculate_execution_success_rate()`: 성공률 계산 (단계별/작업별)
  * `get_graph_traversal_efficiency()`: 그래프 순회 효율성 (LangGraph 전용)

* * *

## 1\. Tool Selection Accuracy

### 개요

**Tool Selection Accuracy** 는 에이전트가 작업을 수행하기 위해 올바른 도구를 선택하는 능력을 측정합니다.

### 작동 원리

  1. **Golden Dataset** 에 `expected_tools` 정의
  2. 에이전트 실행 시 실제 사용한 도구 기록
  3. 예상 도구 vs 실제 도구 비교
  4. Precision, Recall, F1 Score 계산

### 메트릭 계산 (실제 구현)

**구현 위치** : `agent_evaluator/core/agent_evaluator.py` \- `ToolSelectionTracker.evaluate_selection()` (lines 1444-1508)
```json
    [](<#cb1-1>)# 1. 집합 연산으로 TP, FP, FN 계산
    [](<#cb1-2>)expected_set = set(expected_tools)
    [](<#cb1-3>)actual_set = set(actual_tools)
    [](<#cb1-4>)
    [](<#cb1-5>)true_positives = len(expected_set & actual_set)  # 교집합
    [](<#cb1-6>)false_positives = len(actual_set - expected_set)  # actual에만 있음
    [](<#cb1-7>)false_negatives = len(expected_set - actual_set)  # expected에만 있음
    [](<#cb1-8>)
    [](<#cb1-9>)# 2. Precision, Recall, F1 계산
    [](<#cb1-10>)precision = true_positives / len(actual_set) if actual_set else 0
    [](<#cb1-11>)recall = true_positives / len(expected_set) if expected_set else 0
    [](<#cb1-12>)f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    [](<#cb1-13>)
    [](<#cb1-14>)# 3. Accuracy = F1 Score (백분율로 변환)
    [](<#cb1-15>)accuracy = f1_score * 100
```

**예시:** \- Expected Tools: `["search", "calculator", "python_repl"]` \- Actual Tools: `["search", "calculator"]`
```json
    [](<#cb2-1>)True Positives = 2  # {"search", "calculator"} ∩ expected
    [](<#cb2-2>)False Positives = 0  # actual - expected = {}
    [](<#cb2-3>)False Negatives = 1  # expected - actual = {"python_repl"}
    [](<#cb2-4>)
    [](<#cb2-5>)Precision = 2 / 2 = 100%
    [](<#cb2-6>)Recall = 2 / 3 = 66.7%
    [](<#cb2-7>)F1 Score = 2 × (1.0 × 0.667) / (1.0 + 0.667) = 80%
    [](<#cb2-8>)Accuracy = 80%
```

**특별 케이스** : expected_tools가 비어있으면 `{"accuracy": 100.0, "note": "No expected tools defined"}` 반환

### 기본 사용법
```python
    [](<#cb3-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb3-2>)
    [](<#cb3-3>)monitor = PerformanceMonitor()
    [](<#cb3-4>)
    [](<#cb3-5>)# 도구 선택 평가
    [](<#cb3-6>)result = monitor.tool_selection_tracker.evaluate_selection(
    [](<#cb3-7>)    task_id="task_001",
    [](<#cb3-8>)    expected_tools=["search", "calculator", "python_repl"],
    [](<#cb3-9>)    actual_tools=["search", "calculator"]
    [](<#cb3-10>))
    [](<#cb3-11>)
    [](<#cb3-12>)print(f"Accuracy: {result['accuracy']}%")
    [](<#cb3-13>)print(f"Precision: {result['precision']}%")
    [](<#cb3-14>)print(f"Recall: {result['recall']}%")
    [](<#cb3-15>)print(f"F1 Score: {result['f1_score']}%")
```

### LangChain 자동 평가

**✨ 새로운 방식 (권장):**
```python
    [](<#cb4-1>)from agent_evaluator.integrations import LangChainEvaluator
    [](<#cb4-2>)
    [](<#cb4-3>)# LangChain Agent 래핑
    [](<#cb4-4>)evaluator = LangChainEvaluator(
    [](<#cb4-5>)    agent,
    [](<#cb4-6>)    enable_layer2=True  # Layer 2 메트릭 자동 추적
    [](<#cb4-7>))
    [](<#cb4-8>)
    [](<#cb4-9>)# 평가와 함께 실행
    [](<#cb4-10>)result = evaluator.run(
    [](<#cb4-11>)    query="What is 2+2?",
    [](<#cb4-12>)    ground_truth="4",
    [](<#cb4-13>)    expected_tools=["calculator"]  # 자동 평가!
    [](<#cb4-14>))
    [](<#cb4-15>)
    [](<#cb4-16>)# 평가 보고서 생성
    [](<#cb4-17>)report = evaluator.generate_report()
```

**📌 레거시 방식 (DEPRECATED):**
```python
    [](<#cb4b-1>)# ⚠️ v4.0에서 제거 예정
    [](<#cb4b-2>)from agent_evaluator.integrations import LangChainEvaluationCallback
    [](<#cb4b-3>)
    [](<#cb4b-4>)evaluator = LangChainEvaluator(agent,
    [](<#cb4b-5>)    monitor,
    [](<#cb4b-6>)    expected_tools=["search", "calculator"]
    [](<#cb4b-7>))
    [](<#cb4b-8>)result = agent.run("What is 2+2?", callbacks=[callback])
```

### Golden Dataset 기반 자동 평가
```json
    [](<#cb5-1>)# Golden Dataset에 expected_tools 포함
    [](<#cb5-2>)# {
    [](<#cb5-3>)#   "qa_id": "qa_001",
    [](<#cb5-4>)#   "question": "회사의 휴가 정책은?",
    [](<#cb5-5>)#   "expected_tools": ["policy_search", "document_reader"]
    [](<#cb5-6>)# }
    [](<#cb5-7>)
    [](<#cb5-8>)# 자동 평가
    [](<#cb5-9>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb5-10>)    agent_fn=my_agent,
    [](<#cb5-11>)    dataset_path="dataset.json",
    [](<#cb5-12>)    enable_layer2_metrics=True  # Tool Selection 자동 평가
    [](<#cb5-13>))
    [](<#cb5-14>)
    [](<#cb5-15>)print(f"Tool Selection Accuracy: {results['layer2_metrics']['tool_selection_accuracy']}%")
```

### Best Practices

#### 1\. expected_tools 정의

**좋은 예:**
```json
    [](<#cb6-1>){
    [](<#cb6-2>)  "question": "2024년 3분기 매출은?",
    [](<#cb6-3>)  "expected_tools": ["database_query", "calculator", "chart_generator"]
    [](<#cb6-4>)}
```

**나쁜 예:**
```json
    [](<#cb7-1>){
    [](<#cb7-2>)  "question": "2024년 3분기 매출은?",
    [](<#cb7-3>)  "expected_tools": []  # 비어있음 - 평가 불가
    [](<#cb7-4>)}
```

#### 2\. 도구 이름 일관성
```json
    [](<#cb8-1>)# 일관된 이름 사용
    [](<#cb8-2>)expected_tools = ["web_search", "calculator"]
    [](<#cb8-3>)actual_tools = ["web_search", "calculator"]  # ✅ 일치
    [](<#cb8-4>)
    [](<#cb8-5>)# 대소문자 주의
    [](<#cb8-6>)expected_tools = ["WebSearch", "Calculator"]
    [](<#cb8-7>)actual_tools = ["web_search", "calculator"]  # ❌ 불일치
```

#### 3\. 도구 세분화 수준
```json
    [](<#cb9-1>)# 너무 세분화 (권장하지 않음)
    [](<#cb9-2>)expected_tools = ["google_search", "bing_search", "duckduckgo_search"]
    [](<#cb9-3>)
    [](<#cb9-4>)# 적절한 수준 (권장)
    [](<#cb9-5>)expected_tools = ["web_search", "calculator", "code_execution"]
```

* * *

## 2\. Tool Efficiency

### 개요

**Tool Efficiency** 는 선택된 도구가 얼마나 효율적으로 실행되었는지 측정합니다.

### 측정 항목

  1. **성공률 (Success Rate)** : 도구 호출이 성공적으로 완료된 비율
  2. **중복률 (Redundancy Rate)** : 불필요하게 중복 호출된 비율
  3. **효율성 점수 (Efficiency Score)** : 전체 도구 실행 효율성
  4. **평균 실행 시간** : 도구당 평균 실행 소요 시간

### 계산 방식

**구현 위치** : `agent_evaluator/core/agent_evaluator.py` \- `ToolCallAnalyzer` (lines 1195-1343)
```python
    # Tool Efficiency 계산
    success_rate = (successful_calls / total_calls) * 100
    redundancy_rate = (redundant_calls / total_calls) * 100
    efficiency_score = success_rate * (1 - redundancy_rate / 100)
    
```

### 사용 예시
```python
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    
    # 도구 효율성 통계 가져오기
    tool_stats = monitor.tool_analyzer.get_efficiency_stats()
    
    print(f"Success Rate: {tool_stats['success_rate']:.1f}%")
    print(f"Efficiency Score: {tool_stats['avg_efficiency_score']:.1f}%")
    print(f"Redundancy Rate: {tool_stats['redundancy_rate']:.1f}%")
    
```

### Best Practices

  1. **중복 호출 최소화** : 이미 실행한 도구를 캐싱하여 재사용
  2. **실패 처리** : 도구 실행 실패 시 재시도 로직 구현
  3. **타임아웃 설정** : 도구 실행에 적절한 타임아웃 설정
  4. **에러 핸들링** : 도구 실행 실패를 적절히 처리

* * *

## 3\. Agent Coordination

### 개요

**Agent Coordination** 은 멀티 에이전트 시스템에서 에이전트 간 협업 품질을 측정합니다.

### 측정 항목

  1. **상호작용 성공률** : 에이전트 간 통신/위임의 성공률
  2. **에이전트 다양성** : 참여하는 에이전트 수
  3. **상호작용 유형 균형** : delegation, communication, collaboration 균형

### 점수 계산 (0-10 척도) - 실제 구현

**구현 위치** : `agent_evaluator/core/agent_evaluator.py` \- `AgentCoordinationTracker.calculate_coordination_score()` (lines 1515-1746)
```json
    [](<#cb10-1>)# 1. 성공률 계산 (0-100%)
    [](<#cb10-2>)success_rate = sum(1 for i in interactions if i["success"]) / len(interactions) * 100
    [](<#cb10-3>)
    [](<#cb10-4>)# 2. 에이전트 다양성 점수 (0-10)
    [](<#cb10-5>)agents = set()
    [](<#cb10-6>)for i in interactions:
    [](<#cb10-7>)    agents.add(i["from_agent"])
    [](<#cb10-8>)    agents.add(i["to_agent"])
    [](<#cb10-9>)
    [](<#cb10-10>)diversity_score = min(len(agents) / 5, 1.0) * 10  # 5명 이상이 이상적
    [](<#cb10-11>)
    [](<#cb10-12>)# 3. 상호작용 유형 균형 점수 (0-10)
    [](<#cb10-13>)type_counts = defaultdict(int)
    [](<#cb10-14>)for i in interactions:
    [](<#cb10-15>)    type_counts[i["interaction_type"]] += 1
    [](<#cb10-16>)
    [](<#cb10-17>)balance_score = (len(type_counts) / 3) * 10  # 3가지 유형이 이상적
    [](<#cb10-18>)
    [](<#cb10-19>)# 4. 최종 점수 계산 (0-10 척도)
    [](<#cb10-20>)coordination_score = (
    [](<#cb10-21>)    success_rate * 0.5 / 10 +    # 50% 가중치 (success_rate를 0-10으로 정규화)
    [](<#cb10-22>)    diversity_score * 0.3 +        # 30% 가중치
    [](<#cb10-23>)    balance_score * 0.2            # 20% 가중치
    [](<#cb10-24>))
```

**반환값** :
```json
    [](<#cb11-1>){
    [](<#cb11-2>)    "score": 7.85,  # 최종 협업 점수 (0-10)
    [](<#cb11-3>)    "success_rate": 95.0,  # 성공률 (%)
    [](<#cb11-4>)    "total_interactions": 10,  # 총 상호작용 수
    [](<#cb11-5>)    "unique_agents": 4,  # 참여 에이전트 수
    [](<#cb11-6>)    "interaction_types": {  # 유형별 카운트
    [](<#cb11-7>)        "delegation": 4,
    [](<#cb11-8>)        "communication": 3,
    [](<#cb11-9>)        "collaboration": 3
    [](<#cb11-10>)    }
    [](<#cb11-11>)}
```

### 기본 사용법
```python
    [](<#cb12-1>)# 상호작용 기록
    [](<#cb12-2>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb12-3>)    task_id="task_001",
    [](<#cb12-4>)    from_agent="manager",
    [](<#cb12-5>)    to_agent="researcher",
    [](<#cb12-6>)    interaction_type="delegation",  # delegation, communication, collaboration
    [](<#cb12-7>)    success=True,
    [](<#cb12-8>)    context={"task": "market_research"}
    [](<#cb12-9>))
    [](<#cb12-10>)
    [](<#cb12-11>)# 협업 점수 계산
    [](<#cb12-12>)score_data = monitor.agent_coordination_tracker.calculate_coordination_score()
    [](<#cb12-13>)
    [](<#cb12-14>)print(f"Coordination Score: {score_data['score']}/10")
    [](<#cb12-15>)print(f"Success Rate: {score_data['success_rate']}%")
    [](<#cb12-16>)print(f"Unique Agents: {score_data['unique_agents']}")
```

### 상호작용 유형

#### 1\. Delegation (작업 위임)

Manager가 Worker에게 작업을 위임하는 경우:
```python
    [](<#cb13-1>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb13-2>)    task_id="task_001",
    [](<#cb13-3>)    from_agent="manager",
    [](<#cb13-4>)    to_agent="worker",
    [](<#cb13-5>)    interaction_type="delegation",
    [](<#cb13-6>)    success=True,
    [](<#cb13-7>)    context={"task": "data_collection", "deadline": "2024-12-01"}
    [](<#cb13-8>))
```

#### 2\. Communication (정보 전달)

에이전트 간 정보를 공유하는 경우:
```python
    [](<#cb14-1>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb14-2>)    task_id="task_001",
    [](<#cb14-3>)    from_agent="researcher",
    [](<#cb14-4>)    to_agent="analyst",
    [](<#cb14-5>)    interaction_type="communication",
    [](<#cb14-6>)    success=True,
    [](<#cb14-7>)    context={"data": "research_findings", "format": "json"}
    [](<#cb14-8>))
```

#### 3\. Collaboration (협업 작업)

에이전트들이 함께 작업하는 경우:
```python
    [](<#cb15-1>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb15-2>)    task_id="task_001",
    [](<#cb15-3>)    from_agent="developer",
    [](<#cb15-4>)    to_agent="tester",
    [](<#cb15-5>)    interaction_type="collaboration",
    [](<#cb15-6>)    success=True,
    [](<#cb15-7>)    context={"project": "feature_x", "branch": "dev"}
    [](<#cb15-8>))
```

### CrewAI 자동 추적

**✨ 새로운 방식 (권장):**
```python
    [](<#cb16-1>)from agent_evaluator.integrations import CrewAIEvaluator
    [](<#cb16-2>)from crewai import Crew, Agent, Task
    [](<#cb16-3>)
    [](<#cb16-4>)# Agents 생성
    [](<#cb16-5>)manager = Agent(role="Manager", goal="Coordinate team", ...)
    [](<#cb16-6>)researcher = Agent(role="Researcher", goal="Research topics", ...)
    [](<#cb16-7>)writer = Agent(role="Writer", goal="Write articles", ...)
    [](<#cb16-8>)
    [](<#cb16-9>)# Crew 생성
    [](<#cb16-10>)crew = Crew(agents=[manager, researcher, writer], tasks=[...])
    [](<#cb16-11>)
    [](<#cb16-12>)# Evaluator로 래핑 - Layer 2 메트릭 자동 추적
    [](<#cb16-13>)evaluator = CrewAIEvaluator(
    [](<#cb16-14>)    crew,
    [](<#cb16-15>)    enable_layer2=True  # Agent Coordination, Tool Selection 등 자동 추적
    [](<#cb16-16>))
    [](<#cb16-17>)
    [](<#cb16-18>)# 평가와 함께 실행
    [](<#cb16-19>)result = evaluator.kickoff(
    [](<#cb16-20>)    inputs={'topic': 'AI trends'},
    [](<#cb16-21>)    ground_truth='Expected answer...',
    [](<#cb16-22>)    expected_tools=['search', 'analysis'],
    [](<#cb16-23>)    expected_agents=['Manager', 'Researcher', 'Writer']
    [](<#cb16-24>))
    [](<#cb16-25>)
    [](<#cb16-26>)# 평가 보고서 생성 - 모든 Layer 메트릭 포함
    [](<#cb16-27>)report = evaluator.generate_report()
```

**📌 레거시 방식 (DEPRECATED):**
```python
    [](<#cb16b-1>)# ⚠️ v4.0에서 제거 예정
    [](<#cb16b-2>)from agent_evaluator.integrations import EvaluatedCrew
    [](<#cb16b-3>)
    [](<#cb16b-4>)evaluator = CrewAIEvaluator(
    [](<#cb16b-5>)    crew, monitor,
    [](<#cb16b-6>)    enable_coordination_tracking=True
    [](<#cb16b-7>))
    [](<#cb16b-8>)result = evaluated.kickoff()
```

### Golden Dataset 활용
```json
    [](<#cb17-1>){
    [](<#cb17-2>)  "qa_id": "qa_001",
    [](<#cb17-3>)  "question": "시장 분석 보고서 작성",
    [](<#cb17-4>)  "expected_agents": ["manager", "researcher", "analyst", "writer"],
    [](<#cb17-5>)  "expected_interactions": [
    [](<#cb17-6>)    {"from": "manager", "to": "researcher", "type": "delegation"},
    [](<#cb17-7>)    {"from": "researcher", "to": "analyst", "type": "communication"},
    [](<#cb17-8>)    {"from": "analyst", "to": "writer", "type": "collaboration"}
    [](<#cb17-9>)  ]
    [](<#cb17-10>)}
```

### Best Practices

#### 1\. 명확한 에이전트 역할 정의
```json
    [](<#cb18-1>)# 좋은 예: 역할이 명확함
    [](<#cb18-2>)agents = ["manager", "researcher", "writer", "reviewer"]
    [](<#cb18-3>)
    [](<#cb18-4>)# 나쁜 예: 역할이 불명확함
    [](<#cb18-5>)agents = ["agent1", "agent2", "agent3"]
```

#### 2\. 상호작용 성공/실패 기록
```python
    [](<#cb19-1>)# 성공한 위임
    [](<#cb19-2>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb19-3>)    task_id="task_001",
    [](<#cb19-4>)    from_agent="manager",
    [](<#cb19-5>)    to_agent="worker",
    [](<#cb19-6>)    interaction_type="delegation",
    [](<#cb19-7>)    success=True
    [](<#cb19-8>))
    [](<#cb19-9>)
    [](<#cb19-10>)# 실패한 위임 (중요!)
    [](<#cb19-11>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb19-12>)    task_id="task_002",
    [](<#cb19-13>)    from_agent="manager",
    [](<#cb19-14>)    to_agent="worker",
    [](<#cb19-15>)    interaction_type="delegation",
    [](<#cb19-16>)    success=False,
    [](<#cb19-17>)    context={"reason": "worker_busy"}
    [](<#cb19-18>))
```

#### 3\. 위임 성공률 모니터링
```python
    [](<#cb20-1>)delegation_rate = monitor.agent_coordination_tracker.get_delegation_success_rate()
    [](<#cb20-2>)
    [](<#cb20-3>)if delegation_rate < 80.0:
    [](<#cb20-4>)    print("⚠️ 위임 성공률이 낮습니다. 작업 분배 전략을 검토하세요.")
```

* * *

## 4\. Workflow Execution

### 개요

**Workflow Execution** 은 LangChain 체인과 LangGraph 워크플로우의 실행 성공률을 측정합니다.

### 측정 항목

**구현 위치** : `agent_evaluator/core/agent_evaluator.py` \- `WorkflowExecutionTracker` (lines 1752-1971)

  1. **단계 성공률 (Step Success Rate)** : 모든 단계 중 성공한 단계의 비율
  2. **작업 성공률 (Task Success Rate)** : 모든 단계가 성공한 작업의 비율
  3. **그래프 순회 효율성 (Graph Traversal Efficiency)** : LangGraph 전용 - 노드 실행 효율성

### 성공률 계산 (실제 구현)

**calculate_execution_success_rate() 반환값** :
```json
    [](<#cb21-1>){
    [](<#cb21-2>)    "step_success_rate": 95.0,  # 개별 단계 성공률 (%)
    [](<#cb21-3>)    "total_steps": 20,  # 총 단계 수
    [](<#cb21-4>)    "successful_steps": 19,  # 성공한 단계 수
    [](<#cb21-5>)    "failed_steps": 1,  # 실패한 단계 수
    [](<#cb21-6>)    "total_tasks": 5,  # 총 작업 수
    [](<#cb21-7>)    "fully_successful_tasks": 4,  # 모든 단계가 성공한 작업 수
    [](<#cb21-8>)    "task_success_rate": 80.0,  # 작업 성공률 (%)
    [](<#cb21-9>)    "avg_steps_per_task": 4.0  # 작업당 평균 단계 수
    [](<#cb21-10>)}
```

### 그래프 순회 효율성 (LangGraph 전용)

**get_graph_traversal_efficiency() 반환값** :
```json
    [](<#cb22-1>){
    [](<#cb22-2>)    "efficiency": 85.0,  # 효율성 = (successful_nodes / total_steps) * 100
    [](<#cb22-3>)    "total_steps": 20,  # 전체 단계 수 (node + branch + edge)
    [](<#cb22-4>)    "nodes_executed": 15,  # 실행된 노드 수
    [](<#cb22-5>)    "branches_taken": 3,  # 선택된 분기 수
    [](<#cb22-6>)    "successful_nodes": 14,  # 성공한 노드 수
    [](<#cb22-7>)    "avg_node_time": 0.523  # 평균 노드 실행 시간 (초)
    [](<#cb22-8>)}
```

### 기본 사용법
```python
    [](<#cb23-1>)# 워크플로우 단계 추적
    [](<#cb23-2>)monitor.workflow_tracker.track_step(
    [](<#cb23-3>)    task_id="task_001",
    [](<#cb23-4>)    step_name="retrieval",
    [](<#cb23-5>)    step_type="node",  # chain_step, node, edge, branch
    [](<#cb23-6>)    success=True,
    [](<#cb23-7>)    execution_time=0.8,
    [](<#cb23-8>)    framework="langgraph",  # langchain or langgraph
    [](<#cb23-9>)    metadata={"node_id": "node_1"}
    [](<#cb23-10>))
    [](<#cb23-11>)
    [](<#cb23-12>)# 성공률 계산
    [](<#cb23-13>)stats = monitor.workflow_tracker.calculate_execution_success_rate()
    [](<#cb23-14>)
    [](<#cb23-15>)print(f"Step Success Rate: {stats['step_success_rate']}%")
    [](<#cb23-16>)print(f"Task Success Rate: {stats['task_success_rate']}%")
```

### 단계 유형

#### 1\. chain_step (LangChain)
```python
    [](<#cb24-1>)monitor.workflow_tracker.track_step(
    [](<#cb24-2>)    task_id="task_001",
    [](<#cb24-3>)    step_name="document_retrieval",
    [](<#cb24-4>)    step_type="chain_step",
    [](<#cb24-5>)    success=True,
    [](<#cb24-6>)    execution_time=1.2,
    [](<#cb24-7>)    framework="langchain"
    [](<#cb24-8>))
```

#### 2\. node (LangGraph)
```python
    [](<#cb25-1>)monitor.workflow_tracker.track_step(
    [](<#cb25-2>)    task_id="task_001",
    [](<#cb25-3>)    step_name="agent_decision",
    [](<#cb25-4>)    step_type="node",
    [](<#cb25-5>)    success=True,
    [](<#cb25-6>)    execution_time=0.5,
    [](<#cb25-7>)    framework="langgraph",
    [](<#cb25-8>)    metadata={"node_id": "decision_node"}
    [](<#cb25-9>))
```

#### 3\. edge (LangGraph)
```python
    [](<#cb26-1>)monitor.workflow_tracker.track_step(
    [](<#cb26-2>)    task_id="task_001",
    [](<#cb26-3>)    step_name="transition",
    [](<#cb26-4>)    step_type="edge",
    [](<#cb26-5>)    success=True,
    [](<#cb26-6>)    execution_time=0.01,
    [](<#cb26-7>)    framework="langgraph"
    [](<#cb26-8>))
```

#### 4\. branch (LangGraph)
```python
    [](<#cb27-1>)monitor.workflow_tracker.track_step(
    [](<#cb27-2>)    task_id="task_001",
    [](<#cb27-3>)    step_name="conditional_branch",
    [](<#cb27-4>)    step_type="branch",
    [](<#cb27-5>)    success=True,
    [](<#cb27-6>)    execution_time=0.05,
    [](<#cb27-7>)    framework="langgraph",
    [](<#cb27-8>)    metadata={"condition": "high_confidence"}
    [](<#cb27-9>))
```

### LangGraph 자동 추적
```python
    [](<#cb28-1>)from agent_evaluator.integrations import LangGraphEvaluator
    [](<#cb28-2>)
    [](<#cb28-3>)evaluator = LangGraphEvaluator(
    [](<#cb28-4>)    monitor,
    [](<#cb28-5>)    enable_workflow_tracking=True  # 자동 추적!
    [](<#cb28-6>))
    [](<#cb28-7>)
    [](<#cb28-8>)# 노드 추가 (자동으로 래핑됨)
    [](<#cb28-9>)def retrieval_node(state):
    [](<#cb28-10>)    # 검색 로직
    [](<#cb28-11>)    return state
    [](<#cb28-12>)
    [](<#cb28-13>)workflow.add_node("retrieval", retrieval_node)
    [](<#cb28-14>)workflow.add_node("generation", generation_node)
    [](<#cb28-15>)workflow.add_edge("retrieval", "generation")
    [](<#cb28-16>)
    [](<#cb28-17>)# 실행 (자동으로 각 노드 추적!)
    [](<#cb28-18>)result = workflow.compile_and_run({"messages": ["input"]})
    [](<#cb28-19>)
    [](<#cb28-20>)# 통계 확인
    [](<#cb28-21>)stats = monitor.workflow_tracker.calculate_execution_success_rate()
```

### 그래프 순회 효율성 (LangGraph 전용)
```python
    [](<#cb29-1>)efficiency = monitor.workflow_tracker.get_graph_traversal_efficiency(
    [](<#cb29-2>)    task_id="task_001"
    [](<#cb29-3>))
    [](<#cb29-4>)
    [](<#cb29-5>)print(f"Efficiency: {efficiency['efficiency']}%")
    [](<#cb29-6>)print(f"Nodes Executed: {efficiency['nodes_executed']}")
    [](<#cb29-7>)print(f"Branches Taken: {efficiency['branches_taken']}")
    [](<#cb29-8>)print(f"Avg Node Time: {efficiency['avg_node_time']}s")
```

### Best Practices

#### 1\. 실패 단계 상세 기록
```json
    [](<#cb30-1>)try:
    [](<#cb30-2>)    result = execute_step()
    [](<#cb30-3>)    success = True
    [](<#cb30-4>)    error = None
    [](<#cb30-5>)except Exception as e:
    [](<#cb30-6>)    success = False
    [](<#cb30-7>)    error = str(e)
    [](<#cb30-8>)
    [](<#cb30-9>)monitor.workflow_tracker.track_step(
    [](<#cb30-10>)    task_id="task_001",
    [](<#cb30-11>)    step_name="critical_step",
    [](<#cb30-12>)    step_type="node",
    [](<#cb30-13>)    success=success,
    [](<#cb30-14>)    execution_time=time.time() - start,
    [](<#cb30-15>)    framework="langgraph",
    [](<#cb30-16>)    metadata={"error": error} if error else {}
    [](<#cb30-17>))
```

#### 2\. 단계 이름 일관성
```json
    [](<#cb31-1>)# 좋은 예: 명확하고 일관된 이름
    [](<#cb31-2>)steps = ["data_retrieval", "data_processing", "result_generation"]
    [](<#cb31-3>)
    [](<#cb31-4>)# 나쁜 예: 불명확한 이름
    [](<#cb31-5>)steps = ["step1", "step2", "step3"]
```

#### 3\. 프레임워크별 필터링
```python
    [](<#cb32-1>)# LangChain 워크플로우만
    [](<#cb32-2>)langchain_stats = monitor.workflow_tracker.calculate_execution_success_rate(
    [](<#cb32-3>)    framework="langchain"
    [](<#cb32-4>))
    [](<#cb32-5>)
    [](<#cb32-6>)# LangGraph 워크플로우만
    [](<#cb32-7>)langgraph_stats = monitor.workflow_tracker.calculate_execution_success_rate(
    [](<#cb32-8>)    framework="langgraph"
    [](<#cb32-9>))
```

* * *

## Framework 통합

**구현 파일** : `framework_integrations.py`

### 1\. LangChain - Tool Selection 자동 평가

**클래스** : `LangChainEvaluator` \+ `AdvancedLangChainCallback`
```python
    [](<#cb33-1>)from agent_evaluator.integrations import LangChainEvaluator, AdvancedLangChainCallback
    [](<#cb33-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb33-3>)
    [](<#cb33-4>)monitor = PerformanceMonitor()
    [](<#cb33-5>)
    [](<#cb33-6>)# LangChain 에이전트 평가 설정
    [](<#cb33-7>)evaluator = LangChainEvaluator(
    [](<#cb33-8>)    agent=agent,
    [](<#cb33-9>)    monitor=monitor,
    [](<#cb33-10>)    enable_layer2=True  # Layer 2 메트릭 활성화
    [](<#cb33-11>))
    [](<#cb33-12>)
    [](<#cb33-13>)# Callback 생성 (Golden Dataset 사용)
    [](<#cb33-14>)callback = AdvancedLangChainCallback(
    [](<#cb33-15>)    evaluator,
    [](<#cb33-16>)    expected_tools=["search", "calculator", "python_repl"]  # Golden Dataset
    [](<#cb33-17>))
    [](<#cb33-18>)
    [](<#cb33-19>)# 에이전트 실행
    [](<#cb33-20>)result = agent.run("What is 2+2?", callbacks=[callback])
    [](<#cb33-21>)
    [](<#cb33-22>)# 보고서 생성
    [](<#cb33-23>)report = evaluator.generate_report()
    [](<#cb33-24>)print(f"Tool Selection Accuracy: {report.tool_selection_accuracy:.1f}%")
```

**자동 추적 기능** :

  * `on_tool_start()`: 도구 사용 시작 시 자동 기록
  * `on_tool_end()`: 도구 완료 시 자동 기록
  * `on_chain_end()`: 체인 완료 시 자동 평가
  * Layer 1/2/3 메트릭 자동 계산 및 보고서 생성

### 2\. CrewAI - Agent Coordination 자동 추적

**클래스** : `CrewAIEvaluator`
```python
    [](<#cb34-1>)from agent_evaluator.integrations import CrewAIEvaluator
    [](<#cb34-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb34-3>)from crewai import Crew, Agent, Task
    [](<#cb34-4>)
    [](<#cb34-5>)# Agents 생성
    [](<#cb34-6>)manager = Agent(role="Manager", goal="Coordinate team", ...)
    [](<#cb34-7>)researcher = Agent(role="Researcher", goal="Research topics", ...)
    [](<#cb34-8>)writer = Agent(role="Writer", goal="Write content", ...)
    [](<#cb34-9>)
    [](<#cb34-10>)# Crew 생성
    [](<#cb34-11>)crew = Crew(agents=[manager, researcher, writer], tasks=[...])
    [](<#cb34-12>)
    [](<#cb34-13>)# Monitor 생성
    [](<#cb34-14>)monitor = PerformanceMonitor()
    [](<#cb34-15>)
    [](<#cb34-16>)# Evaluator 생성 (Layer 2 자동 추적 활성화)
    [](<#cb34-17>)evaluator = CrewAIEvaluator(
    [](<#cb34-18>)    crew=crew,
    [](<#cb34-19>)    monitor=monitor,
    [](<#cb34-20>)    enable_layer2=True  # Agent Coordination 자동 추적
    [](<#cb34-21>))
    [](<#cb34-22>)
    [](<#cb34-23>)# Crew 실행
    [](<#cb34-24>)result = evaluator.kickoff(inputs={"topic": "AI trends"})
    [](<#cb34-25>)
    [](<#cb34-26>)# 보고서 생성
    [](<#cb34-27>)report = evaluator.generate_report()
    [](<#cb34-28>)print(f"Coordination Score: {report.coordination_score:.1f}/10")
```

**자동 추적 기능** :

  * Agent 간 task delegation 자동 추적
  * 에이전트 실행 순서 추적
  * 상호작용 성공/실패 자동 기록
  * Layer 1/2/3 메트릭 자동 계산 및 보고서 생성

### 3\. LangGraph - Workflow Execution 자동 추적

**클래스** : `LangGraphEvaluator`
```python
    [](<#cb35-1>)from agent_evaluator.integrations import LangGraphEvaluator
    [](<#cb35-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb35-2>)
    [](<#cb35-3>)monitor = PerformanceMonitor()
    [](<#cb35-4>)
    [](<#cb35-5>)# 워크플로우 생성
    [](<#cb35-6>)evaluator = LangGraphEvaluator(
    [](<#cb35-7>)    monitor,
    [](<#cb35-8>)    enable_workflow_tracking=True,  # 자동 추적 활성화
    [](<#cb35-9>)    expected_workflow_steps=["retrieval", "generation", "validation"]
    [](<#cb35-10>))
    [](<#cb35-11>)
    [](<#cb35-12>)# 노드 추가 (자동으로 래핑됨)
    [](<#cb35-13>)def retrieval_node(state):
    [](<#cb35-14>)    # 검색 로직
    [](<#cb35-15>)    return state
    [](<#cb35-16>)
    [](<#cb35-17>)def generation_node(state):
    [](<#cb35-18>)    # 생성 로직
    [](<#cb35-19>)    return state
    [](<#cb35-20>)
    [](<#cb35-21>)workflow.add_node("retrieval", retrieval_node)
    [](<#cb35-22>)workflow.add_node("generation", generation_node)
    [](<#cb35-23>)workflow.add_edge("retrieval", "generation")
    [](<#cb35-24>)
    [](<#cb35-25>)# 실행 (각 노드가 자동으로 추적됨!)
    [](<#cb35-26>)result = workflow.compile_and_run({"messages": ["input"]})
    [](<#cb35-27>)
    [](<#cb35-28>)# 통계 확인
    [](<#cb35-29>)stats = monitor.workflow_tracker.calculate_execution_success_rate()
    [](<#cb35-30>)print(f"Step Success Rate: {stats['step_success_rate']:.1f}%")
    [](<#cb35-31>)
    [](<#cb35-32>)# LangGraph 전용: 그래프 순회 효율성
    [](<#cb35-33>)efficiency = monitor.workflow_tracker.get_graph_traversal_efficiency(task_id)
    [](<#cb35-34>)print(f"Efficiency: {efficiency['efficiency']:.1f}%")
```

**자동 추적 기능** :

  * 각 노드 실행 자동 추적 (성공/실패, 실행 시간)
  * Edge 전환 추적
  * Branch 선택 추적
  * 전체 워크플로우 성공률 계산

### 4\. AutoGen - Multi-Agent Conversation

**클래스** : `AutoGenEvaluator` (lines 558-634)
```python
    [](<#cb36-1>)from agent_evaluator.integrations import AutoGenEvaluator
    [](<#cb36-2>)from autogen import AssistantAgent, UserProxyAgent
    [](<#cb36-3>)
    [](<#cb36-4>)monitor = PerformanceMonitor()
    [](<#cb36-5>)
    [](<#cb36-6>)# Assistant Agent 생성
    [](<#cb36-7>)assistant = AssistantAgent(
    [](<#cb36-8>)    name="assistant",
    [](<#cb36-9>)    llm_config={"model": "gpt-4"},
    [](<#cb36-10>))
    [](<#cb36-11>)
    [](<#cb36-12>)# 평가 통합
    [](<#cb36-13>)evaluator = AutoGenEvaluator(assistant, monitor)
    [](<#cb36-14>)
    [](<#cb36-15>)# 일반 agent처럼 사용 (자동으로 평가됨)
    [](<#cb36-16>)# evaluated.agent로 접근
    [](<#cb36-17>)user_proxy = UserProxyAgent(name="user")
    [](<#cb36-18>)user_proxy.initiate_chat(evaluated.agent, message="Hello")
    [](<#cb36-19>)
    [](<#cb36-20>)# 통계 확인
    [](<#cb36-21>)stats = monitor.get_performance_stats()
```

**자동 추적 기능** :

  * `generate_reply()` 메서드 자동 래핑
  * 토큰 사용량 추정
  * 응답 시간 추적
  * 에러 자동 기록

### Framework 비교표

Framework | Layer 2 메트릭 | 자동 추적 | 통합 방식 | 구현 난이도  
---|---|---|---|---  
**LangChain** | Tool Selection | ✅ | Callback Handler | 쉬움  
**CrewAI** | Agent Coordination | ✅ | Crew Wrapper | 쉬움  
**LangGraph** | Workflow Execution | ✅ | Workflow Wrapper | 중간  
**AutoGen** | Tool Selection, Coordination | ⚠️ 부분적 | Agent Wrapper | 중간  
  
* * *

### 예제 1: RAG 시스템 평가

**시나리오** : 문서 검색 후 답변 생성하는 RAG 시스템
```python
    [](<#cb37-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb37-2>)from agent_evaluator.integrations import LangChainEvaluator, AdvancedLangChainCallback
    [](<#cb37-3>)
    [](<#cb37-4>)monitor = PerformanceMonitor()
    [](<#cb37-5>)
    [](<#cb37-6>)# Golden Dataset에서 로드
    [](<#cb37-7>)qa_pair = {
    [](<#cb37-8>)    "question": "2024년 회사 휴가 정책은?",
    [](<#cb37-9>)    "expected_tools": ["document_retriever", "text_splitter"],  # RAG에 필요한 도구들
    [](<#cb37-10>)    "answer": "2024년 연차는 15일입니다."
    [](<#cb37-11>)}
    [](<#cb37-12>)
    [](<#cb37-13>)# LangChain Callback 설정
    [](<#cb37-14>)evaluator = LangChainEvaluator(agent,
    [](<#cb37-15>)    monitor,
    [](<#cb37-16>)    expected_tools=qa_pair["expected_tools"]
    [](<#cb37-17>))
    [](<#cb37-18>)
    [](<#cb37-19>)# RAG Chain 실행
    [](<#cb37-20>)result = rag_chain.run(qa_pair["question"], callbacks=[callback])
    [](<#cb37-21>)
    [](<#cb37-22>)# 평가 결과
    [](<#cb37-23>)tool_stats = monitor.tool_selection_tracker.get_accuracy_stats()
    [](<#cb37-24>)print(f"Tool Selection Accuracy: {tool_stats['avg_accuracy']:.1f}%")
    [](<#cb37-25>)print(f"Precision: {tool_stats['avg_precision']:.1f}%")
    [](<#cb37-26>)print(f"Recall: {tool_stats['avg_recall']:.1f}%")
```

### 예제 2: 멀티 에이전트 컨텐츠 생성

**시나리오** : 리서치 → 작성 → 리뷰 파이프라인
```python
    [](<#cb38-1>)from agent_evaluator.integrations import CrewAIEvaluator
    [](<#cb38-2>)from crewai import Crew, Agent, Task
    [](<#cb38-3>)
    [](<#cb38-4>)monitor = PerformanceMonitor()
    [](<#cb38-5>)
    [](<#cb38-6>)# Agents 정의
    [](<#cb38-7>)researcher = Agent(
    [](<#cb38-8>)    role="Researcher",
    [](<#cb38-9>)    goal="Research comprehensive information",
    [](<#cb38-10>)    backstory="Expert at finding relevant data"
    [](<#cb38-11>))
    [](<#cb38-12>)
    [](<#cb38-13>)writer = Agent(
    [](<#cb38-14>)    role="Writer",
    [](<#cb38-15>)    goal="Write engaging content",
    [](<#cb38-16>)    backstory="Professional content writer"
    [](<#cb38-17>))
    [](<#cb38-18>)
    [](<#cb38-19>)reviewer = Agent(
    [](<#cb38-20>)    role="Reviewer",
    [](<#cb38-21>)    goal="Review and improve content",
    [](<#cb38-22>)    backstory="Editor with keen eye for detail"
    [](<#cb38-23>))
    [](<#cb38-24>)
    [](<#cb38-25>)# Tasks 정의
    [](<#cb38-26>)research_task = Task(
    [](<#cb38-27>)    description="Research about AI trends",
    [](<#cb38-28>)    agent=researcher
    [](<#cb38-29>))
    [](<#cb38-30>)
    [](<#cb38-31>)write_task = Task(
    [](<#cb38-32>)    description="Write article based on research",
    [](<#cb38-33>)    agent=writer
    [](<#cb38-34>))
    [](<#cb38-35>)
    [](<#cb38-36>)review_task = Task(
    [](<#cb38-37>)    description="Review and polish the article",
    [](<#cb38-38>)    agent=reviewer
    [](<#cb38-39>))
    [](<#cb38-40>)
    [](<#cb38-41>)# Crew 생성 및 평가 통합
    [](<#cb38-42>)crew = Crew(
    [](<#cb38-43>)    agents=[researcher, writer, reviewer],
    [](<#cb38-44>)    tasks=[research_task, write_task, review_task],
    [](<#cb38-45>)    process="sequential"
    [](<#cb38-46>))
    [](<#cb38-47>)
    [](<#cb38-48>)evaluator = CrewAIEvaluator(
    [](<#cb38-49>)    crew,
    [](<#cb38-50>)    monitor,
    [](<#cb38-51>)    enable_coordination_tracking=True,
    [](<#cb38-52>)    expected_agents=["researcher", "writer", "reviewer"]
    [](<#cb38-53>))
    [](<#cb38-54>)
    [](<#cb38-55>)# 실행
    [](<#cb38-56>)result = evaluated.kickoff(inputs={"topic": "AI in 2024"})
    [](<#cb38-57>)
    [](<#cb38-58>)# 협업 평가
    [](<#cb38-59>)score_data = monitor.agent_coordination_tracker.calculate_coordination_score()
    [](<#cb38-60>)print(f"\n협업 점수: {score_data['score']:.1f}/10")
    [](<#cb38-61>)print(f"성공률: {score_data['success_rate']:.1f}%")
    [](<#cb38-62>)print(f"참여 에이전트: {score_data['unique_agents']}명")
    [](<#cb38-63>)
    [](<#cb38-64>)# 위임 성공률
    [](<#cb38-65>)delegation_rate = monitor.agent_coordination_tracker.get_delegation_success_rate()
    [](<#cb38-66>)print(f"위임 성공률: {delegation_rate:.1f}%")
```

### 예제 3: LangGraph 복잡한 워크플로우

**시나리오** : 조건부 분기가 있는 데이터 처리 파이프라인
```python
    [](<#cb39-1>)from agent_evaluator.integrations import LangGraphEvaluator
    [](<#cb39-2>)
    [](<#cb39-3>)monitor = PerformanceMonitor()
    [](<#cb39-4>)
    [](<#cb39-5>)# 워크플로우 생성
    [](<#cb39-6>)evaluator = LangGraphEvaluator(
    [](<#cb39-7>)    monitor,
    [](<#cb39-8>)    enable_workflow_tracking=True,
    [](<#cb39-9>)    expected_workflow_steps=["validate", "process", "quality_check", "save"]
    [](<#cb39-10>))
    [](<#cb39-11>)
    [](<#cb39-12>)# 노드 정의
    [](<#cb39-13>)def validate_node(state):
    [](<#cb39-14>)    """데이터 검증"""
    [](<#cb39-15>)    if state["data"]:
    [](<#cb39-16>)        return {"validated": True, "data": state["data"]}
    [](<#cb39-17>)    return {"validated": False, "error": "No data"}
    [](<#cb39-18>)
    [](<#cb39-19>)def process_node(state):
    [](<#cb39-20>)    """데이터 처리"""
    [](<#cb39-21>)    processed = state["data"].upper()
    [](<#cb39-22>)    return {"data": processed, "processed": True}
    [](<#cb39-23>)
    [](<#cb39-24>)def quality_check_node(state):
    [](<#cb39-25>)    """품질 검사"""
    [](<#cb39-26>)    quality_score = len(state["data"]) > 10
    [](<#cb39-27>)    return {"quality_ok": quality_score}
    [](<#cb39-28>)
    [](<#cb39-29>)def save_node(state):
    [](<#cb39-30>)    """결과 저장"""
    [](<#cb39-31>)    # 저장 로직
    [](<#cb39-32>)    return {"saved": True}
    [](<#cb39-33>)
    [](<#cb39-34>)# 워크플로우 구성
    [](<#cb39-35>)workflow.add_node("validate", validate_node)
    [](<#cb39-36>)workflow.add_node("process", process_node)
    [](<#cb39-37>)workflow.add_node("quality_check", quality_check_node)
    [](<#cb39-38>)workflow.add_node("save", save_node)
    [](<#cb39-39>)
    [](<#cb39-40>)# 조건부 분기
    [](<#cb39-41>)def should_process(state):
    [](<#cb39-42>)    return "process" if state.get("validated") else "end"
    [](<#cb39-43>)
    [](<#cb39-44>)workflow.add_conditional_edges("validate", should_process)
    [](<#cb39-45>)workflow.add_edge("process", "quality_check")
    [](<#cb39-46>)workflow.add_edge("quality_check", "save")
    [](<#cb39-47>)
    [](<#cb39-48>)# 실행
    [](<#cb39-49>)result = workflow.compile_and_run({"data": "test input"})
    [](<#cb39-50>)
    [](<#cb39-51>)# 워크플로우 평가
    [](<#cb39-52>)stats = monitor.workflow_tracker.calculate_execution_success_rate(framework="langgraph")
    [](<#cb39-53>)print(f"\n단계 성공률: {stats['step_success_rate']:.1f}%")
    [](<#cb39-54>)print(f"작업 성공률: {stats['task_success_rate']:.1f}%")
    [](<#cb39-55>)print(f"평균 단계/작업: {stats['avg_steps_per_task']:.1f}")
    [](<#cb39-56>)
    [](<#cb39-57>)# 그래프 효율성
    [](<#cb39-58>)efficiency = monitor.workflow_tracker.get_graph_traversal_efficiency(task_id)
    [](<#cb39-59>)print(f"\n그래프 효율성: {efficiency['efficiency']:.1f}%")
    [](<#cb39-60>)print(f"평균 노드 시간: {efficiency['avg_node_time']:.3f}초")
```

### 예제 4: 통합 평가 - Golden Dataset 사용

**시나리오** : Golden Dataset으로 전체 시스템 평가
```python
    [](<#cb40-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb40-2>)
    [](<#cb40-3>)monitor = PerformanceMonitor()
    [](<#cb40-4>)
    [](<#cb40-5>)# 임계값 설정
    [](<#cb40-6>)monitor.thresholds = {
    [](<#cb40-7>)    # Layer 1
    [](<#cb40-8>)    'tcr': 90.0,
    [](<#cb40-9>)    'accuracy': 85.0,
    [](<#cb40-10>)    'latency': 3.0,
    [](<#cb40-11>)    # Layer 2
    [](<#cb40-12>)    'tool_selection_accuracy': 80.0,
    [](<#cb40-13>)    'agent_coordination': 7.0,
    [](<#cb40-14>)    'workflow_execution': 90.0
    [](<#cb40-15>)}
    [](<#cb40-16>)
    [](<#cb40-17>)# Golden Dataset으로 평가
    [](<#cb40-18>)def my_agent_function(question):
    [](<#cb40-19>)    # 실제 에이전트 실행 로직
    [](<#cb40-20>)    # LangChain/CrewAI/LangGraph 등 사용
    [](<#cb40-21>)    pass
    [](<#cb40-22>)
    [](<#cb40-23>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb40-24>)    agent_fn=my_agent_function,
    [](<#cb40-25>)    dataset_path="dataset.json",
    [](<#cb40-26>)    enable_layer2_metrics=True  # Layer 2 자동 평가
    [](<#cb40-27>))
    [](<#cb40-28>)
    [](<#cb40-29>)# Layer 2 메트릭 확인
    [](<#cb40-30>)print("\n=== Layer 2 평가 결과 ===")
    [](<#cb40-31>)print(f"Tool Selection Accuracy: {results['layer2_metrics'].get('tool_selection_accuracy', 0):.1f}%")
    [](<#cb40-32>)print(f"Agent Coordination: {results['layer2_metrics'].get('agent_coordination', 0):.1f}/10")
    [](<#cb40-33>)print(f"Workflow Execution: {results['layer2_metrics'].get('workflow_execution', 0):.1f}%")
    [](<#cb40-34>)
    [](<#cb40-35>)# 임계값 비교
    [](<#cb40-36>)comparison = monitor.compare_with_thresholds()
    [](<#cb40-37>)print("\n=== 임계값 비교 ===")
    [](<#cb40-38>)for metric, data in comparison.items():
    [](<#cb40-39>)    if data.get('layer') == 'Layer 2':
    [](<#cb40-40>)        status = "✅" if data['status'] == 'pass' else "❌"
    [](<#cb40-41>)        print(f"{status} {data['name']}: {data['value']:.1f}{data['unit']} (임계값: {data['threshold']}{data['unit']})")
```

### 예제 5: CI/CD 파이프라인 통합

**시나리오** : CI/CD 파이프라인에서 자동 평가
```python
    [](<#cb41-1>)# test_agent_performance.py
    [](<#cb41-2>)import sys
    [](<#cb41-3>)from agent_evaluator import PerformanceMonitor
    [](<#cb41-4>)
    [](<#cb41-5>)def test_agent_performance():
    [](<#cb41-6>)    monitor = PerformanceMonitor()
    [](<#cb41-7>)
    [](<#cb41-8>)    # 프로덕션 임계값
    [](<#cb41-9>)    monitor.thresholds = {
    [](<#cb41-10>)        'tool_selection_accuracy': 85.0,
    [](<#cb41-11>)        'agent_coordination': 7.5,
    [](<#cb41-12>)        'workflow_execution': 92.0
    [](<#cb41-13>)    }
    [](<#cb41-14>)
    [](<#cb41-15>)    # 평가 실행
    [](<#cb41-16>)    results = monitor.evaluate_with_golden_dataset(
    [](<#cb41-17>)        agent_fn=production_agent,
    [](<#cb41-18>)        dataset_path="test_dataset.json",
    [](<#cb41-19>)        enable_layer2_metrics=True
    [](<#cb41-20>)    )
    [](<#cb41-21>)
    [](<#cb41-22>)    # 임계값 검증
    [](<#cb41-23>)    comparison = monitor.compare_with_thresholds()
    [](<#cb41-24>)    failures = [m for m, d in comparison.items() if d.get('status') == 'fail']
    [](<#cb41-25>)
    [](<#cb41-26>)    if failures:
    [](<#cb41-27>)        print(f"❌ Failed metrics: {', '.join(failures)}")
    [](<#cb41-28>)        sys.exit(1)
    [](<#cb41-29>)
    [](<#cb41-30>)    print("✅ All metrics passed!")
    [](<#cb41-31>)    return 0
    [](<#cb41-32>)
    [](<#cb41-33>)if __name__ == "__main__":
    [](<#cb41-34>)    sys.exit(test_agent_performance())
```
```json
    [](<#cb42-1>)# .gitlab-ci.yml (권장)
    [](<#cb42-2>)# GitLab CI를 사용한 CI/CD 예제
    [](<#cb42-3>)
    [](<#cb42-4>)stages:
    [](<#cb42-5>)  - test
    [](<#cb42-6>)
    [](<#cb42-7>)test_layer2_metrics:
    [](<#cb42-8>)  stage: test
    [](<#cb42-9>)  image: python:3.11
    [](<#cb42-10>)  script:
    [](<#cb42-11>)    - pip install agent-evaluator
    [](<#cb42-12>)    - python test_agent_performance.py
    [](<#cb42-13>)  only:
    [](<#cb42-14>)    - merge_requests
    [](<#cb42-15>)    - main
```

* * *

## Golden Dataset 활용

### QAPair 구조 (Layer 2 포함)
```json
    [](<#cb43-1>){
    [](<#cb43-2>)  "qa_id": "qa_001",
    [](<#cb43-3>)  "question": "2024년 3분기 매출 분석 보고서 작성",
    [](<#cb43-4>)  "answer": "3분기 매출은 500억원으로...",
    [](<#cb43-5>)  "context": "회사 재무 데이터...",
    [](<#cb43-6>)  "ground_truth": "500억원",
    [](<#cb43-7>)  "metadata": {
    [](<#cb43-8>)    "category": "finance",
    [](<#cb43-9>)    "difficulty": "medium"
    [](<#cb43-10>)  },
    [](<#cb43-11>)  "expected_tools": ["database_query", "calculator", "chart_generator"],
    [](<#cb43-12>)  "expected_agents": ["data_analyst", "finance_expert", "report_writer"],
    [](<#cb43-13>)  "expected_workflow_steps": ["data_collection", "analysis", "visualization", "report_generation"]
    [](<#cb43-14>)}
```

### Dashboard에서 편집

  1. Dashboard 접속
  2. **📄 Golden Dataset** 탭 클릭
  3. **✏️ 기존 데이터셋 편집** 선택
  4. Layer 2 필드 편집: 
     * `Expected Tools`: 쉼표로 구분 (예: `search,calculator,python_repl`)
     * `Expected Agents`: 쉼표로 구분 (예: `manager,researcher,writer`)
     * `Expected Workflow Steps`: 쉼표로 구분 (예: `retrieval,generation,validation`)
  5. **💾 저장** 클릭

* * *

## Threshold 설정

### Layer 2 임계값
```python
    [](<#cb44-1>)monitor.thresholds = {
    [](<#cb44-2>)    # Layer 1
    [](<#cb44-3>)    'tcr': 90.0,
    [](<#cb44-4>)    'accuracy': 85.0,
    [](<#cb44-5>)
    [](<#cb44-6>)    # Layer 2
    [](<#cb44-7>)    'tool_selection_accuracy': 80.0,  # Tool Selection ≥ 80%
    [](<#cb44-8>)    'agent_coordination': 7.0,  # Coordination Score ≥ 7/10
    [](<#cb44-9>)    'workflow_execution': 90.0  # Workflow Success ≥ 90%
    [](<#cb44-10>)}
    [](<#cb44-11>)
    [](<#cb44-12>)# 임계값 비교
    [](<#cb44-13>)comparison = monitor.compare_with_thresholds()
    [](<#cb44-14>)
    [](<#cb44-15>)for metric, data in comparison.items():
    [](<#cb44-16>)    if data.get('layer') == 'Layer 2':
    [](<#cb44-17>)        print(f"{data['name']}: {data['value']:.1f}{data['unit']} (임계값: {data['threshold']}{data['unit']})")
    [](<#cb44-18>)        print(f"상태: {data['status']}")
```

### 프로파일별 임계값 권장

#### Development (개발 환경)
```json
    [](<#cb45-1>)thresholds = {
    [](<#cb45-2>)    'tool_selection_accuracy': 70.0,
    [](<#cb45-3>)    'agent_coordination': 5.0,
    [](<#cb45-4>)    'workflow_execution': 80.0
    [](<#cb45-5>)}
```

#### Staging (스테이징 환경)
```json
    [](<#cb46-1>)thresholds = {
    [](<#cb46-2>)    'tool_selection_accuracy': 80.0,
    [](<#cb46-3>)    'agent_coordination': 7.0,
    [](<#cb46-4>)    'workflow_execution': 90.0
    [](<#cb46-5>)}
```

#### Production (프로덕션 환경)
```json
    [](<#cb47-1>)thresholds = {
    [](<#cb47-2>)    'tool_selection_accuracy': 90.0,
    [](<#cb47-3>)    'agent_coordination': 8.5,
    [](<#cb47-4>)    'workflow_execution': 95.0
    [](<#cb47-5>)}
```

* * *

## Best Practices

### 1\. 점진적 도입
```python
    [](<#cb48-1>)# Phase 1: Layer 1만 사용
    [](<#cb48-2>)monitor = PerformanceMonitor()
    [](<#cb48-3>)# TCR, Accuracy 등만 측정
    [](<#cb48-4>)
    [](<#cb48-5>)# Phase 2: Tool Selection 추가
    [](<#cb48-6>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb48-7>)    agent_fn=my_agent,
    [](<#cb48-8>)    enable_layer2_metrics=True  # Tool Selection만
    [](<#cb48-9>))
    [](<#cb48-10>)
    [](<#cb48-11>)# Phase 3: 모든 Layer 2 활성화
    [](<#cb48-12>)# CrewAI, LangGraph 통합
```

### 2\. Golden Dataset 품질

  * ✅ expected_tools는 최소 필수 도구만 포함
  * ✅ 도구 이름은 일관되게 유지
  * ✅ 각 QA마다 명확한 예상 도구 정의
  * ❌ 모든 QA에 동일한 도구 사용하지 않기

### 3\. 모니터링 주기
```json
    [](<#cb49-1>)# 개발 중: 매 커밋
    [](<#cb49-2>)# CI/CD: Pull Request마다
    [](<#cb49-3>)# 프로덕션: 매일 또는 매주
    [](<#cb49-4>)
    [](<#cb49-5>)# 자동화
    [](<#cb49-6>)results = monitor.evaluate_with_golden_dataset(...)
    [](<#cb49-7>)if results['layer2_metrics']['tool_selection_accuracy'] < 80.0:
    [](<#cb49-8>)    send_alert("Tool Selection Accuracy 저하!")
```

### 4\. 메트릭 해석

#### Tool Selection Accuracy

  * **90%+** : 우수 - 에이전트가 최적의 도구 선택
  * **80-89%** : 양호 - 일부 개선 필요
  * **70-79%** : 보통 - 도구 선택 로직 검토 필요
  * **70% 미만** : 나쁨 - 즉시 개선 필요

#### Agent Coordination

  * **8.5-10** : 우수 - 매우 효과적인 협업
  * **7-8.4** : 양호 - 안정적인 협업
  * **5-6.9** : 보통 - 협업 개선 필요
  * **5 미만** : 나쁨 - 협업 메커니즘 재설계 필요

#### Workflow Execution

  * **95%+** : 우수 - 매우 안정적인 워크플로우
  * **90-94%** : 양호 - 안정적
  * **80-89%** : 보통 - 일부 단계 개선 필요
  * **80% 미만** : 나쁨 - 워크플로우 재설계 필요

* * *

## Troubleshooting

### Q1: Tool Selection Accuracy가 0%로 나옵니다

**원인:** \- expected_tools가 비어있거나 None - 도구 이름 불일치 (대소문자, 공백) - 실제로 도구가 사용되지 않음

**해결:**
```python
    [](<#cb50-1>)# 1. Golden Dataset 확인
    [](<#cb50-2>)qa_pair = load_qa_pair()
    [](<#cb50-3>)print(f"Expected tools: {qa_pair.get('expected_tools')}")
    [](<#cb50-4>)# None, [], [""] 등이면 문제
    [](<#cb50-5>)
    [](<#cb50-6>)# 2. 도구 이름 일관성 확인
    [](<#cb50-7>)expected = ["web_search", "calculator"]
    [](<#cb50-8>)actual = ["WebSearch", "Calculator"]  # ❌ 대소문자 불일치
    [](<#cb50-9>)
    [](<#cb50-10>)# 해결: 소문자로 통일
    [](<#cb50-11>)expected = [t.lower() for t in expected_tools]
    [](<#cb50-12>)actual = [t.lower() for t in actual_tools]
    [](<#cb50-13>)
    [](<#cb50-14>)# 3. 실제 도구 사용 추적 확인
    [](<#cb50-15>)evaluator = LangChainEvaluator(agent,monitor, expected_tools=expected)
    [](<#cb50-16>)# on_tool_start()가 호출되는지 로그 확인
```

**디버깅 팁** :
```python
    [](<#cb51-1>)# evaluate_selection() 반환값 확인
    [](<#cb51-2>)result = monitor.tool_selection_tracker.evaluate_selection(
    [](<#cb51-3>)    task_id="test",
    [](<#cb51-4>)    expected_tools=["search"],
    [](<#cb51-5>)    actual_tools=["search"]
    [](<#cb51-6>))
    [](<#cb51-7>)print(result)
    [](<#cb51-8>)# {'accuracy': 100.0, 'precision': 100.0, ...} 나오는지 확인
```

### Q2: Agent Coordination Score가 항상 0입니다

**원인:** \- 상호작용이 전혀 기록되지 않음 - `enable_coordination_tracking=False` \- CrewAI에서 에이전트 간 통신이 없음

**해결:**
```python
    [](<#cb52-1>)# 1. 상호작용 기록 확인
    [](<#cb52-2>)interactions = monitor.agent_coordination_tracker.interactions
    [](<#cb52-3>)print(f"Total interactions: {len(interactions)}")  # 0이면 문제
    [](<#cb52-4>)
    [](<#cb52-5>)# 2. 수동 추적 테스트
    [](<#cb52-6>)monitor.agent_coordination_tracker.track_interaction(
    [](<#cb52-7>)    task_id="test",
    [](<#cb52-8>)    from_agent="agent1",
    [](<#cb52-9>)    to_agent="agent2",
    [](<#cb52-10>)    interaction_type="delegation",
    [](<#cb52-11>)    success=True
    [](<#cb52-12>))
    [](<#cb52-13>)score_data = monitor.agent_coordination_tracker.calculate_coordination_score()
    [](<#cb52-14>)print(f"Score: {score_data['score']}")  # 값이 나오는지 확인
    [](<#cb52-15>)
    [](<#cb52-16>)# 3. CrewAI 자동 추적 활성화 확인
    [](<#cb52-17>)evaluator = CrewAIEvaluator(
    [](<#cb52-18>)    crew,
    [](<#cb52-19>)    monitor,
    [](<#cb52-20>)    enable_coordination_tracking=True  # 반드시 True!
    [](<#cb52-21>))
```

**일반적인 함정** :
```json
    [](<#cb53-1>)# ❌ 잘못된 사용
    [](<#cb53-2>)evaluator = CrewAIEvaluator(crew, monitor)  # 자동 추적 비활성화 상태
    [](<#cb53-3>)result = evaluated.kickoff()
    [](<#cb53-4>)
    [](<#cb53-5>)# ✅ 올바른 사용
    [](<#cb53-6>)evaluator = CrewAIEvaluator(
    [](<#cb53-7>)    crew,
    [](<#cb53-8>)    monitor,
    [](<#cb53-9>)    enable_coordination_tracking=True  # 명시적으로 활성화
    [](<#cb53-10>))
    [](<#cb53-11>)result = evaluated.kickoff()
```

### Q3: Workflow Execution Rate이 항상 0%입니다

**원인:** \- 워크플로우 단계가 추적되지 않음 - `enable_workflow_tracking=False` \- 수동으로 track_step()을 호출하지 않음

**해결:**
```python
    [](<#cb54-1>)# 1. 단계 추적 확인
    [](<#cb54-2>)executions = monitor.workflow_tracker.executions
    [](<#cb54-3>)print(f"Total steps tracked: {len(executions)}")  # 0이면 문제
    [](<#cb54-4>)
    [](<#cb54-5>)# 2. 수동 추적 테스트
    [](<#cb54-6>)monitor.workflow_tracker.track_step(
    [](<#cb54-7>)    task_id="test",
    [](<#cb54-8>)    step_name="test_step",
    [](<#cb54-9>)    step_type="node",
    [](<#cb54-10>)    success=True,
    [](<#cb54-11>)    execution_time=0.5,
    [](<#cb54-12>)    framework="langgraph"
    [](<#cb54-13>))
    [](<#cb54-14>)stats = monitor.workflow_tracker.calculate_execution_success_rate()
    [](<#cb54-15>)print(stats)  # step_success_rate가 나오는지 확인
    [](<#cb54-16>)
    [](<#cb54-17>)# 3. LangGraph 자동 추적 활성화
    [](<#cb54-18>)evaluator = LangGraphEvaluator(
    [](<#cb54-19>)    monitor,
    [](<#cb54-20>)    enable_workflow_tracking=True  # 반드시 True!
    [](<#cb54-21>))
```

### Q4: 임계값 비교에 Layer 2가 나타나지 않습니다

**원인:** \- Layer 2 메트릭이 평가되지 않음 - 임계값이 설정되지 않음 - 메트릭 이름 불일치

**해결:**
```python
    [](<#cb55-1>)# 1. 임계값 설정 확인
    [](<#cb55-2>)print(monitor.thresholds)
    [](<#cb55-3>)# 출력: {'tool_selection_accuracy': 80.0, 'agent_coordination': 7.0, ...}
    [](<#cb55-4>)
    [](<#cb55-5>)# 2. 메트릭 평가 확인
    [](<#cb55-6>)tool_stats = monitor.tool_selection_tracker.get_accuracy_stats()
    [](<#cb55-7>)print(f"Tool evaluations: {tool_stats.get('total_evaluations', 0)}")
    [](<#cb55-8>)
    [](<#cb55-9>)coord_score = monitor.agent_coordination_tracker.calculate_coordination_score()
    [](<#cb55-10>)print(f"Coordination interactions: {coord_score.get('total_interactions', 0)}")
    [](<#cb55-11>)
    [](<#cb55-12>)workflow_stats = monitor.workflow_tracker.calculate_execution_success_rate()
    [](<#cb55-13>)print(f"Workflow steps: {workflow_stats.get('total_steps', 0)}")
    [](<#cb55-14>)
    [](<#cb55-15>)# 3. 임계값과 메트릭 이름이 일치하는지 확인
    [](<#cb55-16>)# 임계값 키: 'tool_selection_accuracy'
    [](<#cb55-17>)# compare_with_thresholds()가 사용하는 키도 동일해야 함
```

### Q5: get_accuracy_stats()에서 빈 딕셔너리 {}가 반환됩니다

**원인:** \- `selections` 리스트가 비어있음 (평가가 한 번도 안 됨)

**해결:**
```python
    [](<#cb56-1>)# 구현 확인 (agent_evaluator/core/agent_evaluator.py lines 1492-1508)
    [](<#cb56-2>)# if not self.selections:
    [](<#cb56-3>)#     return {}
    [](<#cb56-4>)
    [](<#cb56-5>)# 최소 한 번은 evaluate_selection() 호출 필요
    [](<#cb56-6>)monitor.tool_selection_tracker.evaluate_selection(
    [](<#cb56-7>)    task_id="test",
    [](<#cb56-8>)    expected_tools=["search"],
    [](<#cb56-9>)    actual_tools=["search"]
    [](<#cb56-10>))
    [](<#cb56-11>)
    [](<#cb56-12>)# 이제 stats 확인 가능
    [](<#cb56-13>)stats = monitor.tool_selection_tracker.get_accuracy_stats()
    [](<#cb56-14>)print(stats)  # {'total_evaluations': 1, 'avg_accuracy': 100.0, ...}
```

### Q6: Coordination Score 계산 공식이 이상합니다

**문제** : Score가 예상보다 낮거나 높게 나옴

**이해:**
```python
    [](<#cb57-1>)# 실제 구현 (agent_evaluator/core/agent_evaluator.py lines 1544-1585)
    [](<#cb57-2>)# 성공률: 0-100% → 0-10으로 정규화 (÷10) → 50% 가중치
    [](<#cb57-3>)# 다양성: 에이전트 수 ÷ 5 → 0-10 → 30% 가중치
    [](<#cb57-4>)# 균형: 상호작용 유형 수 ÷ 3 → 0-10 → 20% 가중치
    [](<#cb57-5>)
    [](<#cb57-6>)coordination_score = (
    [](<#cb57-7>)    success_rate * 0.5 / 10 +    # success_rate가 100%일 때 5점
    [](<#cb57-8>)    diversity_score * 0.3 +        # 5명일 때 3점
    [](<#cb57-9>)    balance_score * 0.2            # 3가지 유형일 때 2점
    [](<#cb57-10>))
    [](<#cb57-11>)# 최대 점수 = 5 + 3 + 2 = 10
```

**예시 계산** :
```json
    [](<#cb58-1>)# success_rate = 100%, 4명 참여, 2가지 유형 사용
    [](<#cb58-2>)success_contribution = 100 * 0.5 / 10 = 5.0
    [](<#cb58-3>)diversity_contribution = (4/5) * 10 * 0.3 = 2.4
    [](<#cb58-4>)balance_contribution = (2/3) * 10 * 0.2 = 1.33
    [](<#cb58-5>)total_score = 5.0 + 2.4 + 1.33 = 8.73
```

### Q7: LangGraph efficiency가 100%를 초과합니다

**원인** : 실제로는 100%를 초과할 수 없음 - 버그 가능성

**확인:**
```python
    [](<#cb59-1>)# 구현 확인 (agent_evaluator/core/agent_evaluator.py lines 1823-1846)
    [](<#cb59-2>)# efficiency = (successful_nodes / len(steps)) * 100
    [](<#cb59-3>)
    [](<#cb59-4>)# 버그 확인
    [](<#cb59-5>)efficiency = monitor.workflow_tracker.get_graph_traversal_efficiency("task_id")
    [](<#cb59-6>)print(f"Successful nodes: {efficiency['successful_nodes']}")
    [](<#cb59-7>)print(f"Total steps: {efficiency['total_steps']}")
    [](<#cb59-8>)print(f"Efficiency: {efficiency['efficiency']}")
    [](<#cb59-9>)
    [](<#cb59-10>)# successful_nodes > total_steps면 버그
```

### Q8: 메트릭이 Golden Dataset 평가 후에도 업데이트되지 않습니다

**원인:** \- `enable_layer2_metrics=False` \- Golden Dataset에 Layer 2 필드 누락

**해결:**
```python
    [](<#cb60-1>)# 1. Layer 2 활성화 확인
    [](<#cb60-2>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb60-3>)    agent_fn=my_agent,
    [](<#cb60-4>)    dataset_path="dataset.json",
    [](<#cb60-5>)    enable_layer2_metrics=True  # 반드시 True!
    [](<#cb60-6>))
    [](<#cb60-7>)
    [](<#cb60-8>)# 2. Golden Dataset 형식 확인
    [](<#cb60-9>)import json
    [](<#cb60-10>)with open("dataset.json") as f:
    [](<#cb60-11>)    data = json.load(f)
    [](<#cb60-12>)    for qa in data:
    [](<#cb60-13>)        print(f"QA {qa['qa_id']}:")
    [](<#cb60-14>)        print(f"  expected_tools: {qa.get('expected_tools')}")
    [](<#cb60-15>)        print(f"  expected_agents: {qa.get('expected_agents')}")
    [](<#cb60-16>)        print(f"  expected_workflow_steps: {qa.get('expected_workflow_steps')}")
    [](<#cb60-17>)        # 하나라도 None이면 해당 메트릭 평가 안 됨
```

### Q9: 프레임워크 통합이 작동하지 않습니다

**원인:** \- 프레임워크가 설치되지 않음 - Import 오류

**해결:**
```python
    [](<#cb61-1>)# 1. 설치 확인
    [](<#cb61-2>)try:
    [](<#cb61-3>)    from langchain.callbacks.base import BaseCallbackHandler
    [](<#cb61-4>)    print("✅ LangChain available")
    [](<#cb61-5>)except ImportError:
    [](<#cb61-6>)    print("❌ Install: pip install langchain")
    [](<#cb61-7>)
    [](<#cb61-8>)try:
    [](<#cb61-9>)    from crewai import Crew
    [](<#cb61-10>)    print("✅ CrewAI available")
    [](<#cb61-11>)except ImportError:
    [](<#cb61-12>)    print("❌ Install: pip install crewai")
    [](<#cb61-13>)
    [](<#cb61-14>)try:
    [](<#cb61-15>)    from langgraph.graph import StateGraph
    [](<#cb61-16>)    print("✅ LangGraph available")
    [](<#cb61-17>)except ImportError:
    [](<#cb61-18>)    print("❌ Install: pip install langgraph")
    [](<#cb61-19>)
    [](<#cb61-20>)# 2. framework_integrations.py 가용성 확인
    [](<#cb61-21>)from framework_integrations import (
    [](<#cb61-22>)    LANGCHAIN_AVAILABLE,
    [](<#cb61-23>)    CREWAI_AVAILABLE,
    [](<#cb61-24>)    LANGGRAPH_AVAILABLE,
    [](<#cb61-25>)    AUTOGEN_AVAILABLE
    [](<#cb61-26>))
    [](<#cb61-27>)print(f"LangChain: {LANGCHAIN_AVAILABLE}")
    [](<#cb61-28>)print(f"CrewAI: {CREWAI_AVAILABLE}")
    [](<#cb61-29>)print(f"LangGraph: {LANGGRAPH_AVAILABLE}")
    [](<#cb61-30>)print(f"AutoGen: {AUTOGEN_AVAILABLE}")
```

* * *

## 📊 품질 관리자 가이드 (QA Manager)

> 💼 **품질 관리자를 위한 Layer 2 메트릭 실전 가이드** : 멀티 에이전트 시스템의 품질을 측정, 평가, 관리하는 체계적인 방법을 제공합니다.

**🎯 이 가이드를 읽으면 알 수 있는 것**

  * ✅ Layer 2 메트릭이 전체 시스템 품질에 미치는 영향
  * ✅ 단계별(Alpha/Beta/Production) 적절한 임계값 설정 방법
  * ✅ 배포 전 반드시 확인해야 할 체크리스트
  * ✅ 문제 발생 시 신속하게 대응하는 시나리오별 조치 방법
  * ✅ 멀티 에이전트 시스템의 품질을 지속적으로 개선하는 원칙

### 1\. Layer 2 메트릭 품질 해석

#### 🤖 Layer 2 핵심 메트릭 품질 지표

**Layer 2 메트릭의 특징:** Layer 1이 개별 작업의 성능을 측정한다면, Layer 2는 **멀티 에이전트 시스템의 협업 품질** 을 측정합니다.

메트릭 | 무엇을 측정? | 품질 영향도 | 권장 임계값 | ⚠️ 위험 신호  
---|---|---|---|---  
**Tool Selection  
Accuracy**  
 _(도구 선택 정확도)_ | 에이전트가 **올바른 도구** 를  
선택하는 비율 | ⭐⭐⭐⭐⭐  
**매우 높음**  
작업 성공률 직결 | ✅ ≥ 85%  
⚠️ 70-85%  
❌ < 70% | **< 70%:**  
도구 선택 로직  
재설계 필요  
**Tool Usage  
Efficiency**  
 _(도구 사용 효율)_ | **불필요한 도구 호출**  
최소화 정도 | ⭐⭐⭐⭐  
**높음**  
비용·속도 영향 | ✅ ≥ 80%  
⚠️ 60-80%  
❌ < 60% | **< 60%:**  
중복 호출 분석  
최적화 필요  
**Agent  
Coordination**  
 _(협업 점수)_ | **멀티 에이전트 간**  
협업 효과성 (0-10 척도) | ⭐⭐⭐⭐⭐  
**매우 높음**  
복잡한 작업 품질 | ✅ ≥ 4.0/10  
⚠️ 3.0-4.0  
❌ < 3.0 | **< 3.0:**  
에이전트 간  
협업 개선 필요  
**Workflow  
Execution**  
 _(워크플로우 실행)_ | **워크플로우**  
실행 성공률 | ⭐⭐⭐⭐  
**높음**  
전체 성능 | ✅ ≥ 75%  
⚠️ 60-75%  
❌ < 60% | **< 60%:**  
워크플로우  
최적화 필요  
  
#### 📊 Layer 1 ← Layer 2 영향 관계 (인과관계 맵)

**💡 핵심 인사이트: Layer 2가 Layer 1에 미치는 영향**

Layer 2 문제 | → | Layer 1 영향 | 결과  
---|---|---|---  
**Tool Selection ↓** | → | **TCR ↓** | 잘못된 도구로 작업 실패  
**Tool Efficiency ↓** | → | **Latency ↑, Cost ↑** | 불필요한 호출로 느려지고 비용 증가  
**Coordination ↓** | → | **Quality ↓, Accuracy ↓** | 협업 실패로 답변 품질 저하  
**Tool Efficiency ↓** | → | **Cost ↑, Latency ↑** | 도구 실행 실패 및 중복으로 자원 낭비  
**Workflow Execution ↓** | → | **TCR ↓, Cost ↑** | 비효율적 워크플로우로 실패율·비용 증가  
  
**📈 최적화 전략:** Layer 2 메트릭을 먼저 개선하면 Layer 1 메트릭이 자연스럽게 향상됩니다!

#### 🔍 실전 예시: 메트릭 해석 연습

**시나리오:** 다음과 같은 메트릭 결과를 받았습니다.
```python
    Layer 1:
      - TCR: 78% (목표: 90%)
      - Accuracy: 82% (목표: 85%)
      - Latency: 4.2초 (목표: <3초)
      - Cost: $0.15/task (예산: $0.10)
    
    Layer 2:
      - Tool Selection: 65%
      - Tool Efficiency: 55%
      - Agent Coordination: 3.8/10
      - Workflow Execution: 72%
    
```

**📊 분석:**

  * **주 문제:** Tool Selection (65%)과 Tool Efficiency (55%)가 매우 낮음
  * **근본 원인:** 에이전트가 잘못된 도구를 선택하고, 불필요하게 많이 호출
  * **Layer 1 영향:**
    * 낮은 Tool Selection → TCR 78% (작업 실패 증가)
    * 낮은 Tool Efficiency → Latency 4.2초, Cost $0.15 (비효율)
  * **🎯 우선 조치:**
    1. 도구 선택 로직 개선 (프롬프트 강화, Few-shot 예제)
    2. 불필요한 도구 호출 제거 (캐싱, 조건부 호출)
    3. → 이것만 해도 TCR 85%+, Latency 3초, Cost $0.12로 개선 가능!

### 2\. 임계값 설정 및 품질 기준

#### 🎯 개발 단계별 Layer 2 임계값 전략

**💡 임계값 설정 철학**

  * **Alpha:** 기본 동작 확인 (낮은 기준)
  * **Beta:** 실사용 가능 수준 (중간 기준)
  * **Production:** 고품질 보장 (높은 기준)
  * **Enterprise:** 미션 크리티컬 (최고 기준)

단계 | Tool Selection | Tool Efficiency | Coordination | Workflow Eff.  
---|---|---|---|---  
**🔬 Alpha**  
(내부 테스트) | ≥ 65%  
_(기본 동작 확인)_ | ≥ 50%  
_(허용 범위 넓음)_ | ≥ 2.5/5.0  
 _(최소 협업)_ | ≥ 50%  
_(기본 실행)_  
**🧪 Beta**  
(제한 공개) | ≥ 80%  
_(안정화)_ | ≥ 70%  
_(개선 필요)_ | ≥ 3.5/5.0  
 _(양호한 협업)_ | ≥ 65%  
_(실용 수준)_  
**🚀 Production**  
(전체 공개) | ≥ 85%  
_(고품질)_ | ≥ 80%  
_(효율적)_ | ≥ 4.0/5.0  
 _(우수한 협업)_ | ≥ 75%  
_(최적화)_  
**💎 Enterprise**  
(미션 크리티컬) | ≥ 90%  
_(최고 수준)_ | ≥ 85%  
_(최적화)_ | ≥ 4.5/5.0  
 _(탁월한 협업)_ | ≥ 80%  
_(완벽)_  
  
#### 🏢 멀티 에이전트 시스템 유형별 우선순위

시스템 유형 | 특징 | 우선 메트릭 | 권장 임계값  
---|---|---|---  
**🛠️ 도구 중심**  
(Tool-heavy) | 많은 외부 도구 사용  
(API, DB, 검색 등) | 1\. Tool Selection  
2\. Tool Efficiency | Selection ≥ 90%  
Efficiency ≥ 85%  
**🤝 협업 중심**  
(Collaborative) | 다수 에이전트 간  
긴밀한 협력 | 1\. Agent Coordination  
2\. Tool Selection | Coordination ≥ 4.5/10  
Selection ≥ 85%  
**📊 워크플로우 중심**  
(Workflow-based) | 정형화된 다단계  
작업 프로세스 | 1\. Workflow Execution  
2\. Tool Efficiency | Workflow ≥ 75%  
Efficiency ≥ 80%  
**🔀 하이브리드**  
(Hybrid) | 도구+협업+워크플로우  
모두 중요 | 모든 메트릭 균형 | 모든 메트릭  
≥ Production 기준  
  
#### ⚙️ 실전 코드: Layer 2 임계값 설정 및 검증
```python
    [](<#cb-qa-layer2-code-1>)from agent_evaluator import HybridPerformanceMonitor
    [](<#cb-qa-layer2-code-2>)
    [](<#cb-qa-layer2-code-3>)# Production 단계 Layer 2 임계값 (4개 메트릭)
    [](<#cb-qa-layer2-code-4>)LAYER2_THRESHOLDS_PRODUCTION = {
    [](<#cb-qa-layer2-code-5>)    "tool_selection_accuracy": 85.0,  # % (도구 선택 정확도)
    [](<#cb-qa-layer2-code-6>)    "tool_efficiency": 80.0,  # % (도구 실행 효율성)
    [](<#cb-qa-layer2-code-7>)    "agent_coordination": 4.0,  # 0-10 척도 (에이전트 협업 품질)
    [](<#cb-qa-layer2-code-8>)    "workflow_execution": 75.0  # % (워크플로우 성공률)
    [](<#cb-qa-layer2-code-9>)}
    [](<#cb-qa-layer2-code-12>)
    [](<#cb-qa-layer2-code-13>)# 모니터 생성 (Layer 2 활성화)
    [](<#cb-qa-layer2-code-14>)monitor = HybridPerformanceMonitor(
    [](<#cb-qa-layer2-code-15>)    use_deepeval=False,
    [](<#cb-qa-layer2-code-16>)    use_ragas=False
    [](<#cb-qa-layer2-code-17>))
    [](<#cb-qa-layer2-code-18>)
    [](<#cb-qa-layer2-code-19>)# Golden Dataset 평가 (Layer 2 필수 활성화!)
    [](<#cb-qa-layer2-code-20>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb-qa-layer2-code-21>)    agent_fn=my_multi_agent_system,
    [](<#cb-qa-layer2-code-22>)    dataset_path="golden_datasets/multi_agent.json",
    [](<#cb-qa-layer2-code-23>)    enable_layer2_metrics=True  # ← 반드시 True!
    [](<#cb-qa-layer2-code-24>))
    [](<#cb-qa-layer2-code-25>)
    [](<#cb-qa-layer2-code-26>)# Layer 2 임계값 검증 함수
    [](<#cb-qa-layer2-code-27>)def validate_layer2_thresholds(results, thresholds):print("""
        """Layer 2 임계값 검증"""
    [](<#cb-qa-layer2-code-28>)    layer2 = results.get("layer2_metrics", {})
    [](<#cb-qa-layer2-code-29>)    
    [](<#cb-qa-layer2-code-30>)    passed = True
    [](<#cb-qa-layer2-code-31>)    
    [](<#cb-qa-layer2-code-32>)    # Tool Selection
    [](<#cb-qa-layer2-code-33>)    if layer2.get("tool_selection_accuracy", 0) < thresholds["tool_selection_accuracy"]:
    [](<#cb-qa-layer2-code-34>)        print(f"❌ Tool Selection: {layer2['tool_selection_accuracy']:.1f}% < {thresholds['tool_selection_accuracy']}%")
    [](<#cb-qa-layer2-code-35>)        passed = False
    [](<#cb-qa-layer2-code-36>)    
    [](<#cb-qa-layer2-code-37>)    # Coordination
    [](<#cb-qa-layer2-code-38>)    if layer2.get("agent_coordination_score", 0) < thresholds["agent_coordination_score"]:
    [](<#cb-qa-layer2-code-39>)        print(f"❌ Coordination: {layer2['agent_coordination_score']:.1f} < {thresholds['agent_coordination_score']}")
    [](<#cb-qa-layer2-code-40>)        passed = False
    [](<#cb-qa-layer2-code-41>)    
    [](<#cb-qa-layer2-code-42>)    # ... 나머지 메트릭 검증
    [](<#cb-qa-layer2-code-43>)    
    [](<#cb-qa-layer2-code-44>)    if passed:
    [](<#cb-qa-layer2-code-45>)        print("✅ 모든 Layer 2 임계값 통과!")
    [](<#cb-qa-layer2-code-46>)    else:
    [](<#cb-qa-layer2-code-47>)        print("🚨 임계값 미달: 배포 중단하고 개선 필요")
    [](<#cb-qa-layer2-code-48>)    
    [](<#cb-qa-layer2-code-49>)    return passed
    [](<#cb-qa-layer2-code-50>)
    [](<#cb-qa-layer2-code-51>)# 실행
    [](<#cb-qa-layer2-code-52>)validate_layer2_thresholds(results, LAYER2_THRESHOLDS_PRODUCTION)
```

### 3\. 배포 전 품질 체크리스트

#### ✅ 멀티 에이전트 시스템 배포 체크리스트

**📋 Layer 2 Release Checklist (Production 배포 전 필수)**

카테고리 | 항목 | 기준 | 결과 | Pass/Fail  
---|---|---|---|---  
**🛠️ 도구  
선택** | Tool Selection Accuracy | ≥ 85% | _____% | [ ]  
Tool Usage Efficiency | ≥ 80% | _____% | [ ]  
**⚡ 도구  
효율성** | Tool Efficiency | ≥ 80% | _____% | [ ]  
**🤝 에이전트  
협업** | Agent Coordination | ≥ 4.0/10 | _____/10 | [ ]  
**📊 워크  
플로우** | Workflow Execution | ≥ 75% | _____% | [ ]  
**📈 Layer 1  
연계** | TCR (Task Completion Rate) | ≥ 90% | _____% | [ ]  
Accuracy | ≥ 85% | _____% | [ ]  
Total Cost per Task | < 예산 | $_____ | [ ]  
  
**🔴 하나라도 Fail 시 → 즉시 배포 중단하고 해당 영역 개선 후 재평가**

**✅ 모두 Pass 시 → 배포 승인 + 주간 모니터링 계획 수립**

#### 📅 주간 Layer 2 모니터링 체크리스트

**🗓️ 매주 월요일 오전 체크 (지난 7일 데이터)**

모니터링 항목 | 확인 방법 | 조치 기준  
---|---|---  
**Tool Selection 트렌드** | 지난 7일 평균 추이 | 5% 이상 하락 시 조사  
**Tool Efficiency 저하** | 불필요한 호출 증가 여부 | 비용 10% 이상 증가 시  
**Tool Efficiency 하락** | 도구 실행 효율성 | 80% 미만 시 최적화 필요  
**Coordination Score 변동** | 에이전트 간 협업 품질 | 0.5점 이상 하락 시 분석  
**Workflow 병목 지점** | 가장 느린 워크플로우 단계 | P95 latency 3초 초과 시  
**비용 vs 효율성** | 비용 대비 TCR 분석 | 효율성 하락 + 비용 증가 시  
  
### 4\. 문제 해결 시나리오

#### 🚨 Layer 2 문제 유형별 실전 대응 가이드

##### 🔴 시나리오 1: Tool Selection Accuracy 급감 (85% → 60%)

**🔍 증상:**

  * 에이전트가 부적절한 도구를 자주 선택
  * 작업 실패율(TCR) 동시 하락
  * 사용자가 "엉뚱한 답변"이라고 피드백

**🕵️ 원인 분석 (우선순위 순):**

  1. **프롬프트 변경:** 최근 도구 선택 컨텍스트 약화
  2. **새 도구 추가:** 도구 간 역할 구분 불명확
  3. **모델 업데이트:** 새 모델의 도구 이해도 저하
  4. **데이터 분포 변화:** 새로운 유형의 요청 증가

**⚡ 즉시 조치 (1시간 내):**

  1. 📊 **로그 분석:** 도구 선택 실패 케이스 Top 10 추출
  2. 📝 **프롬프트 강화:** 각 도구의 설명(description) 명확화 
```# 나쁜 예
         tools = [Tool(name="search", description="Search")]
         
         # 좋은 예
         tools = [Tool(
             name="search",
             description="웹에서 최신 정보를 검색할 때 사용. 실시간 데이터, 뉴스, 사실 확인에 적합. 내부 지식보다 최신성이 중요한 경우 선택."
         )]
```

  3. 🎯 **Few-shot 예제 추가:** 올바른 도구 선택 예시 3개 제공
  4. 🔄 **임시 롤백:** 이전 버전으로 되돌린 후 비교 테스트

**🔧 근본 해결 (1주 내):**

  * 📚 도구별 사용 시나리오 문서화 (팀 공유)
  * 🧩 도구 선택 로직을 별도 레이어로 분리 (Router Agent)
  * 🎓 Fine-tuning으로 도구 선택 패턴 학습
  * ✅ Golden Dataset에 도구 선택 케이스 50개 추가

**✅ 성공 지표:** Tool Selection ≥ 85%, TCR ≥ 90%로 회복

##### 🟠 시나리오 2: Agent Coordination 저하 (4.5 → 2.8)

**🔍 증상:**

  * 멀티 에이전트 간 협업 효과성 감소
  * 작업 품질(Quality Score) 동시 하락
  * 중복 작업 또는 누락된 작업 발생

**🕵️ 원인 분석:**

  1. **역할 분담 불명확:** 각 에이전트의 책임 범위 모호
  2. **통신 프로토콜 오류:** 메시지 전달 실패 또는 지연
  3. **순환 의존성:** 에이전트 A ↔ B 간 무한 루프
  4. **리소스 경쟁:** 여러 에이전트가 동시에 같은 자원 접근

**⚡ 즉시 조치:**

  1. 📊 **메시지 교환 로그 분석:** 에이전트 간 통신 패턴 시각화
  2. 🎭 **역할 재정의:** 각 에이전트의 역할(role)과 책임 명확화 
```# 나쁜 예
         agent1 = Agent(role="assistant")
         agent2 = Agent(role="helper")
         
         # 좋은 예
         researcher = Agent(
             role="정보 수집 전문가",
             goal="사용자 질문에 필요한 정보를 웹/DB에서 수집",
             backstory="검색과 데이터 추출에 특화..."
         )
         writer = Agent(
             role="답변 작성 전문가",
             goal="수집된 정보를 바탕으로 사용자 친화적 답변 작성"
         )
```

  3. 👨‍✈️ **Supervisor 추가:** 에이전트 조율을 담당하는 상위 에이전트 도입
  4. 🔍 **협업 실패 케이스 수동 검토:** 가장 심각한 5개 케이스 분석

**🔧 근본 해결:**

  * 📐 에이전트 간 통신 프로토콜 표준화 (JSON 스키마 정의)
  * 🎯 작업 분담 전략 재설계 (Sequential vs Hierarchical vs Autonomous)
  * 🔗 에이전트 간 의존성 최소화 (느슨한 결합)
  * 🧪 멀티 에이전트 시나리오 통합 테스트 자동화

**✅ 성공 지표:** Coordination ≥ 4.0, Quality Score ≥ 4.0

##### 🟡 시나리오 3: Workflow Efficiency 저하 (80% → 55%)

**🔍 증상:**

  * 워크플로우 실행이 비효율적으로 변함
  * 응답 시간(Latency) 동시 증가
  * 특정 단계에서 반복 실패 또는 대기

**🕵️ 원인 분석:**

  1. **불필요한 단계 추가:** 워크플로우가 점점 복잡해짐
  2. **조건부 분기 오류:** 특정 조건에서 잘못된 경로 실행
  3. **병목 단계:** 특정 단계가 전체 워크플로우 속도 저하
  4. **에러 핸들링 부족:** 실패 시 재시도 없이 중단

**⚡ 즉시 조치:**

  1. 📊 **워크플로우 실행 로그 시각화:** Mermaid/Graphviz로 시각화 
```Step 1 (0.5s) → Step 2 (2.1s) → Step 3 (0.3s) → Step 4 (3.8s ⚠️) → Step 5 (0.4s)
                                                               ↑ 병목!
```

  2. 🎯 **병목 단계 식별:** 가장 오래 걸리는 단계 Top 3
  3. 📉 **단계 최적화:** 중복 실행 및 불필요한 단계 제거
  4. 🔄 **재시도 로직 추가:** 일시적 실패에 대한 복원력 강화

**🔧 근본 해결:**

  * 📊 워크플로우 DAG 최적화 (Directed Acyclic Graph)
  * ⚡ 병렬 실행 가능한 단계 식별 (Step 2 + Step 3 병렬 처리)
  * 🧹 불필요한 단계 제거 (4단계 → 3단계로 단순화)
  * 🎛️ 조건부 분기 로직 단순화 (if-elif-else → 룩업 테이블)

**✅ 성공 지표:** Workflow Execution ≥ 75%, Latency < 3초

#### 📊 에스컬레이션 가이드 (Layer 2 전용)

심각도 | 상황 | 대응 시간 | 담당자 | 조치 사항  
---|---|---|---|---  
**P0  
(Critical)** | • Tool Selection < 60%  
• Coordination < 2.5  
• TCR < 70% | **즉시**  
(30분 내) | CTO +  
Architecture  
Team | 시스템 중단  
긴급 패치  
**P1  
(High)** | • Tool Selection 60-70%  
• Workflow Eff. < 60%  
• TCR 70-85% | **2시간 이내** | Tech Lead +  
QA Manager | 배포 중단  
핫픽스 준비  
**P2  
(Medium)** | • Tool Eff. 60-75%  
• Comm. Overhead > 25%  
• 비용 20% 초과 | **당일** | QA Manager +  
Dev Team | 원인 분석  
개선 계획  
**P3  
(Low)** | • 임계값 근접  
• 최적화 여지  
• 트렌드 악화 | **주간 회의** | 담당 개발자 | 모니터링  
점진적 개선  
  
### 5\. QA 관리자 핵심 원칙

**💡 멀티 에이전트 시스템 품질 관리 7대 원칙**

  1. **🔗 Layer 1 + Layer 2 통합 모니터링**

두 레이어를 함께 분석하여 근본 원인을 파악합니다. Layer 2 문제가 Layer 1에 미치는 영향을 항상 염두에 둡니다.
``` 예: TCR 하락 → Layer 2 Tool Selection 확인 → 도구 선택 로직 개선
```

  2. **🛠️ 도구 중심 최적화**

Tool Selection과 Tool Efficiency 개선이 전체 성능 향상의 지름길입니다. 이 두 메트릭에 집중하면 TCR, Latency, Cost가 동시에 개선됩니다.

  3. **🤝 협업 품질 우선**

Coordination Score가 낮으면 다른 메트릭도 연쇄 하락합니다. 멀티 에이전트 시스템에서는 협업 품질이 가장 중요합니다.

  4. **📊 워크플로우 시각화**

워크플로우 실행 흐름을 시각화하여 병목 지점을 빠르게 발견합니다. 로그만으로는 부족하며, 그래프/차트가 필수입니다.

  5. **✅ 지속적 벤치마킹**

Golden Dataset으로 주간 평가하여 성능 퇴행을 조기에 방지합니다. CI/CD 파이프라인에 Layer 2 평가를 통합합니다.

  6. **💰 비용 효율성**

불필요한 호출과 중복 단계를 제거하여 비용을 최적화합니다. Efficiency 메트릭이 비용 절감의 핵심 지표입니다.

  7. **👥 사용자 피드백 연계**

Layer 2 메트릭과 실제 사용자 만족도의 상관관계를 분석합니다. Coordination Score와 사용자 평점의 관계를 추적합니다.

**⚠️ 주의사항 (반드시 피해야 할 4가지)**

  1. **❌ Layer 2 메트릭만으로 판단 금지**

항상 Layer 1 메트릭과 함께 고려하세요. Tool Selection이 90%라도 TCR이 70%면 무의미합니다.

  2. **❌ 과도한 최적화 주의**

Efficiency 향상을 위해 품질(Quality, Accuracy)을 희생하지 마세요. 사용자 만족이 최우선입니다.

  3. **❌ 시스템 복잡도 관리**

에이전트 수가 많을수록 Coordination이 어려워집니다. 5개 이상의 에이전트는 계층 구조(Hierarchical)를 고려하세요.

  4. **❌ Golden Dataset 다양성 부족**

멀티 에이전트 시나리오를 충분히 포함시키세요. 단일 에이전트 케이스만으로는 Layer 2 평가가 불가능합니다.

**✅ 성공 사례: Layer 2 개선으로 전체 품질 향상**

**배경:** 5-agent 협업 시스템, TCR 75%, Latency 5초, Cost $0.20/task (예산 초과)

**Layer 2 분석 결과:**

  * Tool Selection: 65% (낮음)
  * Tool Efficiency: 55% (매우 낮음)
  * Coordination: 3.2 (보통)

**개선 조치:**

  1. 도구 선택 로직 개선 (프롬프트 + Few-shot) → Tool Selection 88%
  2. 불필요한 도구 호출 제거 (캐싱) → Tool Efficiency 82%
  3. 에이전트 역할 재정의 → Coordination 4.1

**결과 (2주 후):**

  * ✅ TCR: 75% → 92% (+17%p)
  * ✅ Latency: 5초 → 2.8초 (-44%)
  * ✅ Cost: $0.20 → $0.12 (-40%)
  * ✅ 사용자 만족도: 3.5 → 4.3 (+0.8)

**💡 교훈:** Layer 2 개선이 Layer 1을 자동으로 향상시킵니다!

* * *

## 참고 자료

  * [API 레퍼런스](<API.md>) \- Layer 2 API 완전 문서
  * [Golden Dataset 가이드](<GOLDEN_DATASET_GUIDE.md>) \- Dataset 작성 가이드
  * [Threshold 설정 가이드](<THRESHOLD_CONFIGURATION_GUIDE.md>) \- 임계값 설정 가이드
  * [예제 코드](<../Evaluator_Examples/framework_with_layer2_example.py>) \- Framework 통합 예제

* * *

## 요약: Layer 2 메트릭 빠른 체크리스트

### Tool Selection Accuracy (LangChain, AutoGen)

**필수 단계** :

  * ✅ Golden Dataset에 `expected_tools` 정의
  * ✅ `LangChainEvaluator`에 `expected_tools` 전달
  * ✅ `get_accuracy_stats()`로 통계 확인

**검증** :
```python
    [](<#cb62-1>)stats = monitor.tool_selection_tracker.get_accuracy_stats()
    [](<#cb62-2>)assert stats.get('total_evaluations', 0) > 0, "No evaluations recorded"
    [](<#cb62-3>)assert stats['avg_accuracy'] >= 80.0, "Below threshold"
```

### Agent Coordination (CrewAI, AutoGen)

**필수 단계** :

  * ✅ `CrewAIEvaluator`에서 `enable_coordination_tracking=True` 설정
  * ✅ `track_interaction()`으로 상호작용 기록 (수동 모드)
  * ✅ `calculate_coordination_score()`로 점수 계산

**검증** :
```python
    [](<#cb63-1>)score_data = monitor.agent_coordination_tracker.calculate_coordination_score()
    [](<#cb63-2>)assert score_data.get('total_interactions', 0) > 0, "No interactions recorded"
    [](<#cb63-3>)assert score_data['score'] >= 7.0, "Below threshold"
```

### Workflow Execution (LangChain, LangGraph)

**필수 단계** :

  * ✅ `LangGraphEvaluator`에서 `enable_workflow_tracking=True` 설정
  * ✅ `track_step()`으로 단계 기록 (수동 모드)
  * ✅ `calculate_execution_success_rate()`로 성공률 계산

**검증** :
```python
    [](<#cb64-1>)stats = monitor.workflow_tracker.calculate_execution_success_rate()
    [](<#cb64-2>)assert stats.get('total_steps', 0) > 0, "No steps tracked"
    [](<#cb64-3>)assert stats['step_success_rate'] >= 90.0, "Below threshold"
```

### 임계값 설정 가이드

**개발 환경** :
```python
    [](<#cb65-1>)monitor.thresholds = {
    [](<#cb65-2>)    'tool_selection_accuracy': 70.0,
    [](<#cb65-3>)    'agent_coordination': 5.0,
    [](<#cb65-4>)    'workflow_execution': 80.0
    [](<#cb65-5>)}
```

**프로덕션 환경** :
```python
    [](<#cb66-1>)monitor.thresholds = {
    [](<#cb66-2>)    'tool_selection_accuracy': 90.0,
    [](<#cb66-3>)    'agent_coordination': 8.5,
    [](<#cb66-4>)    'workflow_execution': 95.0
    [](<#cb66-5>)}
```

### 일반적인 실수 방지

문제 | 원인 | 해결  
---|---|---  
Accuracy 0% | expected_tools 누락 | Golden Dataset 확인  
Coordination 0 | tracking 비활성화 | `enable_coordination_tracking=True`  
Workflow 0% | steps 미추적 | `enable_workflow_tracking=True`  
빈 stats {} | 평가 미실행 | 최소 1회 평가 필요  
Import 에러 | 프레임워크 미설치 | `pip install langchain crewai langgraph`  
  
### 코드 템플릿

**최소 실행 가능 예제** :
```python
    [](<#cb67-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb67-2>)from agent_evaluator.integrations import LangChainEvaluator, AdvancedLangChainCallback
    [](<#cb67-3>)
    [](<#cb67-4>)# 1. Monitor 초기화
    [](<#cb67-5>)monitor = PerformanceMonitor()
    [](<#cb67-6>)
    [](<#cb67-7>)# 2. 임계값 설정
    [](<#cb67-8>)monitor.thresholds = {
    [](<#cb67-9>)    'tool_selection_accuracy': 80.0,
    [](<#cb67-10>)    'agent_coordination': 7.0,
    [](<#cb67-11>)    'workflow_execution': 90.0
    [](<#cb67-12>)}
    [](<#cb67-13>)
    [](<#cb67-14>)# 3. Framework 통합
    [](<#cb67-15>)evaluator = LangChainEvaluator(agent,
    [](<#cb67-16>)    monitor,
    [](<#cb67-17>)    expected_tools=["search", "calculator"]
    [](<#cb67-18>))
    [](<#cb67-19>)
    [](<#cb67-20>)# 4. Agent 실행
    [](<#cb67-21>)result = agent.run("query", callbacks=[callback])
    [](<#cb67-22>)
    [](<#cb67-23>)# 5. 평가 결과
    [](<#cb67-24>)stats = monitor.tool_selection_tracker.get_accuracy_stats()
    [](<#cb67-25>)print(f"Tool Selection: {stats['avg_accuracy']:.1f}%")
    [](<#cb67-26>)
    [](<#cb67-27>)# 6. 임계값 비교
    [](<#cb67-28>)comparison = monitor.compare_with_thresholds()
    [](<#cb67-29>)for metric, data in comparison.items():
    [](<#cb67-30>)    if data.get('layer') == 'Layer 2':
    [](<#cb67-31>)        print(f"{data['name']}: {data['status']}")
```

* * *

## 문서 검증 정보

**검증 날짜** : 2026-03-17 **검증 대상** : `agent_evaluator/core/agent_evaluator.py` **검증 범위** : \- ✅ `ToolCallAnalyzer` (lines 1195-1343) \- ✅ `ToolSelectionTracker` (lines 1444-1508) \- ✅ `AgentCoordinationTracker` (lines 1515-1746) \- ✅ `WorkflowExecutionTracker` (lines 1752-1971) \- ✅ Framework Integrations (`agent_evaluator/integrations/`) \- ✅ 예제 코드 (`Evaluator_Examples/framework_with_layer2_example.py`)

**주요 개선사항** : 1. 실제 구현과 문서 설명 일치 확인 2. 메서드 시그니처 및 반환값 검증 3. 계산 공식 상세 설명 추가 4. 5개 실전 예제 추가 (RAG, Multi-Agent, LangGraph, Golden Dataset, CI/CD) 5. 9개 트러블슈팅 시나리오 추가 6. AutoGen 통합 예제 추가 7. Framework 비교표 추가 8. 빠른 체크리스트 및 코드 템플릿 추가

* * *

## 피드백

Layer 2 메트릭에 대한 질문이나 피드백이 있으시면 프로젝트 담당자에게 문의하세요!

* * *

* * *

**최종 업데이트** : 2026-03-19
**버전** : Agent Evaluator v0.5.3
**프로젝트** : Agent Evaluator - AI Agent Performance Evaluation System  
**문서** : Agentic AI Metrics Guide (Layer 2)
