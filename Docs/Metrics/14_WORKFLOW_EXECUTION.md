# 🔄 Workflow Execution Tracking

LangChain/LangGraph Workflow Performance Analysis

Agent Evaluator v0.5.1 - Layer 2 Advanced Metric

## 🎯 개요

**Workflow Execution Tracking (워크플로우 실행 추적)** 은 LangChain/LangGraph 기반 워크플로우의 실행 흐름과 성능을 분석하는 Layer 2 Advanced Metric입니다. 

  * **측정 대상** : Workflow Step 성공률, Critical Path, Bottleneck
  * **분석 항목** : Step-level Success, Graph Traversal Efficiency, 병렬화 기회
  * **적용 대상** : LangChain Chains, LangGraph State Machines
  * **구현 위치** : `agent_evaluator/core/agent_evaluator.py` (Lines 1752-1970)

#### ⚠️ Workflow Tracking이 중요한 이유

  * **성능 최적화** : Bottleneck 단계 식별 → 속도 개선
  * **안정성** : 실패 단계 탐지 → 신뢰성 향상
  * **병렬화** : 독립 단계 식별 → 동시 실행
  * **비용 절감** : 불필요한 단계 제거 → 리소스 절약

#### 🏗️ 구현 특징

  * **클래스** : `WorkflowExecutionTracker` (agent_evaluator.py:1752-1970)
  * **분석 방식** : Step-level Tracking + Critical Path Analysis
  * **지원 Framework** : LangChain (Chain), LangGraph (StatefulGraph)
  * **Layer 2 분류** : Workflow Performance Analysis

## 📊 핵심 메트릭

### Step-level 메트릭

메트릭 | 정의 | 목표  
---|---|---  
Step Success Rate | 성공한 Step / 전체 Step × 100 | 95% 이상  
Task Success Rate | 모든 Step 성공한 Task / 전체 Task × 100 | 90% 이상  
Avg Steps per Task | 전체 Step 수 / Task 수 | 작을수록 효율적  
Graph Traversal Efficiency | 성공한 Node / 전체 Step × 100 | 80% 이상 (LangGraph)  
  
### Step Type 분류

Type | 설명 | Framework | 예시  
---|---|---|---  
chain_step | LangChain의 Chain 단계 | LangChain | LLMChain, TransformChain  
node | LangGraph의 Node (상태 변환) | LangGraph | StateGraph Node  
edge | LangGraph의 Edge (노드 연결) | LangGraph | Conditional Edge  
branch | 분기점 (조건부 실행) | Both | If-else, Switch  
  
## 🔍 데이터 수집 방법 (실전 가이드)

#### 💡 데이터 수집 핵심 원칙

Workflow Execution Tracking 측정을 위해서는 **각 워크플로우 Step의 실행 기록** 이 필요합니다:

  * **필수 데이터** : step_name, step_type, success 상태, execution_time
  * **권장 데이터** : task_id, framework (langchain/langgraph), metadata
  * **수집 방법** : Framework Integration (자동) 또는 Manual Wrapping (수동)

### 방법 1: LangGraph Integration (자동 수집) 🚀

가장 권장하는 방법입니다. LangGraphEvaluator가 각 노드 실행을 자동으로 추적합니다.

#### LangGraph 자동 추적 예제

from agent_evaluator.integrations import LangGraphEvaluator from langgraph.graph import StateGraph, END from typing import TypedDict # State 정의 class AgentState(TypedDict): messages: list next_step: str # Evaluator 초기화 (자동 추적 활성화) evaluator = LangGraphEvaluator( enable_layer2=True, # ✅ Workflow Execution 자동 추적 verbose=True ) # 노드 함수 정의 def retrieve_docs(state: AgentState): """문서 검색 노드""" # 검색 로직... state["messages"].append("Retrieved documents") return state def generate_response(state: AgentState): """응답 생성 노드""" # LLM 호출... state["messages"].append("Generated response") return state # 노드 추가 (자동으로 래핑되어 추적됨) evaluator.add_node("retrieve_docs", retrieve_docs) evaluator.add_node("generate_response", generate_response) # 엣지 연결 evaluator.add_edge("start", "retrieve_docs") evaluator.add_edge("retrieve_docs", "generate_response") evaluator.add_edge("generate_response", "end") # 실행 (각 노드가 자동으로 추적됨) result = evaluator.run( initial_state={"messages": [], "next_step": ""}, ground_truth="Expected output" ) # Workflow 성능 분석 report = evaluator.generate_report() workflow_stats = evaluator.monitor.workflow_tracker.calculate_execution_success_rate( framework="langgraph" ) print(f"Step Success Rate: {workflow_stats['step_success_rate']}%") print(f"Task Success Rate: {workflow_stats['task_success_rate']}%") print(f"Avg Steps per Task: {workflow_stats['avg_steps_per_task']}") # Critical Path 분석 critical_path = evaluator.monitor.workflow_tracker.get_critical_path_analysis() print(f"\nBottlenecks:") for bottleneck in critical_path["bottlenecks"]: print(f" - {bottleneck['step_name']}: {bottleneck['avg_time']}s (성공률: {bottleneck['success_rate']}%)") 

#### 🔧 LangGraph에서 자동 수집되는 데이터

  * **step_name** : 노드 이름 (add_node()의 첫 번째 인자)
  * **step_type** : "node" (자동으로 "node"로 설정됨)
  * **success** : 예외 발생 여부로 판단
  * **execution_time** : 노드 시작~종료 시간 차이
  * **framework** : "langgraph" (자동 설정)
  * **metadata** : 에러 정보 (실패 시)

**구현 위치** : agent_evaluator/integrations/langgraph_integration.py (Lines 180-220)

#### _wrap_node_for_tracking() 메커니즘

**자동 추적의 핵심** : 각 노드가 자동으로 래핑되어 실행 전후에 추적 코드가 삽입됩니다.

# agent_evaluator/integrations/langgraph_integration.py:180-220 def _wrap_node_for_tracking(self, node_name: str, func): """노드를 래핑하여 Workflow Execution 추적""" def wrapped(state: AgentState): start_time = time.time() success = True error = None try: result = func(state) # 원본 노드 실행 except Exception as e: success = False error = str(e) result = state if "evaluation_data" in result: result["evaluation_data"]["errors"].append(error) execution_time = time.time() - start_time # ✅ WorkflowExecutionTracker에 자동 기록 if self.current_task_id: self.monitor.workflow_tracker.track_step( task_id=self.current_task_id, step_name=node_name, step_type="node", success=success, execution_time=execution_time, framework="langgraph", metadata={"error": error} if error else {} ) return result return wrapped 

### 방법 2: LangChain Integration (Chain 추적) 🔗

LangChain Chains의 각 단계를 추적하는 방법입니다.

#### LangChain Callback 기반 추적

from agent_evaluator.integrations import LangChainEvaluator from langchain.chains import SequentialChain, LLMChain from langchain_openai import ChatOpenAI # Evaluator 초기화 evaluator = LangChainEvaluator( agent_or_chain=your_chain, enable_layer2=True # Workflow 추적 활성화 ) # Chain 실행 (각 단계가 Callback으로 추적됨) result = evaluator.run( query="Analyze this data", ground_truth="Expected analysis" ) # Workflow 통계 확인 workflow_stats = evaluator.monitor.workflow_tracker.calculate_execution_success_rate( framework="langchain" ) print(f"Chain Execution Success: {workflow_stats['step_success_rate']}%") 

#### Custom Callback for Fine-grained Tracking

from langchain.callbacks.base import BaseCallbackHandler from agent_evaluator import WorkflowExecutionTracker import time class WorkflowTrackingCallback(BaseCallbackHandler): """LangChain Workflow Step 추적용 Callback""" def __init__(self, tracker: WorkflowExecutionTracker, task_id: str): self.tracker = tracker self.task_id = task_id self.step_start_times = {} def on_chain_start(self, serialized, inputs, **kwargs): """Chain 시작""" chain_name = serialized.get("name", "unknown_chain") self.step_start_times[chain_name] = time.perf_counter() def on_chain_end(self, outputs, **kwargs): """Chain 종료 - 성공""" chain_name = kwargs.get("name", "unknown_chain") if chain_name in self.step_start_times: execution_time = time.perf_counter() - self.step_start_times[chain_name] self.tracker.track_step( task_id=self.task_id, step_name=chain_name, step_type="chain_step", success=True, execution_time=execution_time, framework="langchain", metadata={"outputs": str(outputs)[:100]} # 첫 100자만 ) del self.step_start_times[chain_name] def on_chain_error(self, error, **kwargs): """Chain 종료 - 실패""" chain_name = kwargs.get("name", "unknown_chain") if chain_name in self.step_start_times: execution_time = time.perf_counter() - self.step_start_times[chain_name] self.tracker.track_step( task_id=self.task_id, step_name=chain_name, step_type="chain_step", success=False, execution_time=execution_time, framework="langchain", metadata={"error": str(error)} ) del self.step_start_times[chain_name] # 사용 예제 tracker = WorkflowExecutionTracker() callback = WorkflowTrackingCallback(tracker, task_id="task_001") # Chain에 Callback 전달 chain.run( input_data, callbacks=[callback] ) # 분석 stats = tracker.calculate_execution_success_rate() critical_path = tracker.get_critical_path_analysis() 

### 방법 3: 완전 수동 추적 (Custom Framework) 🔧

Framework Integration을 사용할 수 없는 경우 WorkflowExecutionTracker를 직접 사용합니다.

#### 수동 Step 추적

from agent_evaluator import WorkflowExecutionTracker import time class CustomWorkflowRunner: def __init__(self): self.tracker = WorkflowExecutionTracker() def run_workflow(self, task_id: str, data): """워크플로우 실행 및 추적""" # Step 1: 데이터 전처리 start = time.perf_counter() try: preprocessed_data = self.preprocess(data) success1 = True except Exception as e: preprocessed_data = None success1 = False self.tracker.track_step( task_id=task_id, step_name="preprocess", step_type="node", success=success1, execution_time=time.perf_counter() - start, framework="custom" ) if not success1: return None # Step 2: 모델 추론 start = time.perf_counter() try: result = self.inference(preprocessed_data) success2 = True except Exception as e: result = None success2 = False self.tracker.track_step( task_id=task_id, step_name="inference", step_type="node", success=success2, execution_time=time.perf_counter() - start, framework="custom" ) if not success2: return None # Step 3: 후처리 start = time.perf_counter() try: final_result = self.postprocess(result) success3 = True except Exception as e: final_result = None success3 = False self.tracker.track_step( task_id=task_id, step_name="postprocess", step_type="node", success=success3, execution_time=time.perf_counter() - start, framework="custom" ) return final_result def get_performance_report(self): """성능 리포트 생성""" stats = self.tracker.calculate_execution_success_rate() critical_path = self.tracker.get_critical_path_analysis() return { "success_rate": stats, "bottlenecks": critical_path["bottlenecks"], "recommendations": critical_path["optimization_recommendations"] } # 사용 runner = CustomWorkflowRunner() result = runner.run_workflow("task_001", input_data) report = runner.get_performance_report() print(f"Step Success Rate: {report['success_rate']['step_success_rate']}%") print(f"Bottlenecks: {report['bottlenecks']}") 

#### Decorator 패턴으로 추적 자동화

from functools import wraps import time def track_workflow_step( tracker: WorkflowExecutionTracker, task_id: str, step_name: str, step_type: str = "node" ): """워크플로우 Step 추적 Decorator""" def decorator(func): @wraps(func) def wrapper(*args, **kwargs): start = time.perf_counter() success = True error = None try: result = func(*args, **kwargs) except Exception as e: success = False error = str(e) raise finally: execution_time = time.perf_counter() - start tracker.track_step( task_id=task_id, step_name=step_name, step_type=step_type, success=success, execution_time=execution_time, framework="custom", metadata={"error": error} if error else {} ) return result return wrapper return decorator # 사용 예제 tracker = WorkflowExecutionTracker() @track_workflow_step(tracker, "task_001", "data_loading") def load_data(path): # 데이터 로딩 로직 return load(path) @track_workflow_step(tracker, "task_001", "processing") def process_data(data): # 처리 로직 return process(data) # 실행 (자동으로 추적됨) data = load_data("/data/input.csv") result = process_data(data) # 분석 stats = tracker.calculate_execution_success_rate() 

### 방법 4: 프로덕션 환경 모니터링 📊

프로덕션에서는 모든 워크플로우 실행을 추적하고 정기적으로 분석합니다.

from agent_evaluator import WorkflowExecutionTracker import logging from datetime import datetime, timedelta class ProductionWorkflowMonitor: def __init__(self, sample_rate=0.2): self.tracker = WorkflowExecutionTracker() self.sample_rate = sample_rate # 20% 샘플링 self.logger = logging.getLogger(__name__) self.alert_thresholds = { "step_success_rate": 90, "task_success_rate": 85, "max_step_time": 5.0 } def track_workflow(self, task_id: str, steps: List[Dict]): """워크플로우 추적 및 샘플링 분석""" import random # 각 Step 기록 for step in steps: self.tracker.track_step( task_id=task_id, step_name=step["name"], step_type=step.get("type", "node"), success=step["success"], execution_time=step["execution_time"], framework=step.get("framework", "custom") ) # 샘플링된 경우만 상세 분석 if random.random() < self.sample_rate: self._analyze_and_alert(task_id) def _analyze_and_alert(self, task_id: str): """워크플로우 분석 및 경고""" stats = self.tracker.calculate_execution_success_rate(task_id=task_id) alerts = [] # Step Success Rate 체크 if stats["step_success_rate"] < self.alert_thresholds["step_success_rate"]: alerts.append( f"🟡 Low step success rate: {stats['step_success_rate']}%" ) # Task Success Rate 체크 if stats["task_success_rate"] < self.alert_thresholds["task_success_rate"]: alerts.append( f"🔴 Low task success rate: {stats['task_success_rate']}%" ) # Critical Path 분석 critical = self.tracker.get_critical_path_analysis() for bottleneck in critical["bottlenecks"]: if bottleneck["avg_time"] > self.alert_thresholds["max_step_time"]: alerts.append( f"🐢 Slow step '{bottleneck['step_name']}': {bottleneck['avg_time']}s" ) # 경고 로깅 if alerts: self.logger.warning(f"Workflow {task_id} issues: {', '.join(alerts)}") def generate_daily_report(self) -> str: """일간 워크플로우 성능 리포트""" stats = self.tracker.calculate_execution_success_rate() critical = self.tracker.get_critical_path_analysis() report = f""" 📊 Workflow Execution Report {'='*50} Period: Last 24 hours (Sampled {self.sample_rate*100:.0f}%) Success Metrics: \- Step Success Rate: {stats['step_success_rate']}% \- Task Success Rate: {stats['task_success_rate']}% \- Total Tasks: {stats['total_tasks']} \- Avg Steps per Task: {stats['avg_steps_per_task']} Performance: \- Total Workflows: {critical['total_workflows']} \- Avg Workflow Time: {critical['workflow_statistics']['avg_total_time']}s \- Max Workflow Time: {critical['workflow_statistics']['max_total_time']}s Top Bottlenecks: """ for i, bottleneck in enumerate(critical["bottlenecks"], 1): report += f""" {i}. {bottleneck['step_name']} \- Avg Time: {bottleneck['avg_time']}s \- Success Rate: {bottleneck['success_rate']}% \- Executions: {bottleneck['execution_count']} """ report += f""" Optimization Recommendations: """ for rec in critical["optimization_recommendations"]: report += f" - {rec}\n" return report # 프로덕션 사용 monitor = ProductionWorkflowMonitor(sample_rate=0.2) # 워크플로우 실행 후 추적 def execute_production_workflow(task_id, data): steps = [] # Step 1 start = time.perf_counter() try: result1 = step1(data) success1 = True except: success1 = False steps.append({ "name": "step1", "success": success1, "execution_time": time.perf_counter() - start }) # ... 다른 Steps ... # 추적 monitor.track_workflow(task_id, steps) # 일간 리포트 (Cron으로 스케줄링) def daily_report_job(): report = monitor.generate_daily_report() print(report) # 또는 Slack/Email 전송

#### ⚠️ 프로덕션 데이터 수집 시 주의사항

  * **성능 오버헤드** : 샘플링(10-20%)으로 부담 최소화
  * **시간 측정** : time.perf_counter() 사용 (time.time()보다 정확)
  * **메타데이터 크기** : 큰 데이터는 요약하거나 제외
  * **에러 처리** : 추적 실패가 워크플로우 실패로 이어지지 않도록
  * **Step 명명** : 일관된 이름 사용 (분석 시 집계 용이)

## 🚨 실전 배포 시 주의사항

### 1\. Branch와 Conditional Edge 추적

# LangGraph Conditional Edge 추적 def route_decision(state: AgentState) -> str: """조건부 라우팅 결정""" start = time.perf_counter() # 라우팅 로직 if state["score"] > 0.8: next_node = "high_confidence" else: next_node = "low_confidence" # Branch 추적 tracker.track_step( task_id=state["task_id"], step_name=f"route_to_{next_node}", step_type="branch", # ✅ Branch로 표시 success=True, execution_time=time.perf_counter() - start, framework="langgraph", metadata={"decision": next_node, "score": state["score"]} ) return next_node # LangGraph에 적용 workflow.add_conditional_edges( "classifier", route_decision, { "high_confidence": "fast_path", "low_confidence": "careful_path" } ) 

### 2\. 병렬 실행 Step 추적

import asyncio from concurrent.futures import ThreadPoolExecutor async def parallel_workflow_tracking(tracker, task_id, steps): """병렬 실행 Step 추적""" async def track_step_async(step_func, step_name): start = time.perf_counter() success = True try: result = await step_func() except Exception as e: success = False result = None tracker.track_step( task_id=task_id, step_name=step_name, step_type="node", success=success, execution_time=time.perf_counter() - start, framework="custom", metadata={"parallel": True} # ✅ 병렬 표시 ) return result # 병렬 실행 results = await asyncio.gather( track_step_async(step1, "step1"), track_step_async(step2, "step2"), track_step_async(step3, "step3") ) return results 

### 3\. Graph Traversal Efficiency 최적화

# LangGraph 전용 효율성 분석 def analyze_graph_efficiency(tracker, task_id): """그래프 순회 효율성 분석""" efficiency = tracker.get_graph_traversal_efficiency(task_id) print(f"Graph Traversal Efficiency: {efficiency['efficiency']}%") print(f"Nodes Executed: {efficiency['nodes_executed']}") print(f"Branches Taken: {efficiency['branches_taken']}") print(f"Avg Node Time: {efficiency['avg_node_time']}s") # 비효율 탐지 if efficiency["efficiency"] < 80: print(f"⚠️ Low efficiency - too many branches or failed nodes") # 실패한 노드 식별 steps = [e for e in tracker.executions if e["task_id"] == task_id and not e["success"]] if steps: print(f"Failed steps:") for step in steps: print(f" - {step['step_name']}") 

### 4\. 실시간 Workflow 최적화 제안

class RealTimeWorkflowOptimizer: def __init__(self, tracker: WorkflowExecutionTracker): self.tracker = tracker self.optimization_history = [] def analyze_and_optimize(self) -> List[str]: """실시간 분석 및 최적화 제안""" critical = self.tracker.get_critical_path_analysis() suggestions = [] # 1. 병렬화 기회 if critical["parallelization_opportunities"]: for opp in critical["parallelization_opportunities"]: suggestions.append(f"💡 {opp['description']}") # 2. Bottleneck 최적화 for bottleneck in critical["bottlenecks"]: if bottleneck["avg_time"] > 2.0: suggestions.append( f"🔧 Optimize '{bottleneck['step_name']}' (avg: {bottleneck['avg_time']}s)" ) # 캐싱 제안 if bottleneck["execution_count"] > 10: suggestions.append( f"💾 Consider caching for '{bottleneck['step_name']}' (called {bottleneck['execution_count']} times)" ) # 3. 실패율 개선 for step in critical["critical_path"]: if step["success_rate"] < 95: suggestions.append( f"🔴 Improve reliability of '{step['step_name']}' (success: {step['success_rate']}%)" ) self.optimization_history.append({ "timestamp": datetime.now(), "suggestions": suggestions }) return suggestions # 사용 optimizer = RealTimeWorkflowOptimizer(tracker) suggestions = optimizer.analyze_and_optimize() if suggestions: print("\n🎯 Optimization Suggestions:") for suggestion in suggestions: print(f" {suggestion}") 

#### 💡 배포 체크리스트

  * ✅ **자동 추적** : LangGraph/LangChain Integration 사용
  * ✅ **성능 측정** : time.perf_counter() 사용
  * ✅ **Branch 추적** : Conditional edge를 "branch" 타입으로 기록
  * ✅ **병렬 실행** : 병렬 Step에 metadata 표시
  * ✅ **샘플링** : 프로덕션에서 10-20% 샘플링
  * ✅ **경고 시스템** : Success rate, bottleneck 임계값 설정
  * ✅ **주기적 분석** : Critical path 분석 및 최적화 제안

## ⚙️ 핵심 알고리즘

#### 📊 Workflow Execution Success Rate 계산 흐름

graph TD A[executions 리스트] --> B{task_id 필터링} B --> C[Step Success Rate  
성공 Step / 전체] C --> D[Task 그룹화] D --> E{각 Task별  
모든 Step 성공?} E -->|Yes| F[fully_successful_tasks++] E -->|No| G[failed_tasks++] F --> H[Task Success Rate  
성공 Task / 전체 Task] G --> H H --> I[통계 반환  
step_success_rate  
task_success_rate  
avg_steps_per_task] style A fill:#667eea,color:#fff style C fill:#48bb78,color:#fff style E fill:#ed8936,color:#fff style H fill:#3182ce,color:#fff style I fill:#667eea,color:#fff 

#### 📊 Critical Path Analysis 흐름

graph TD A[모든 executions] --> B[Task별 그룹화] B --> C[Step별 통계 계산] C --> D1[평균 실행 시간] C --> D2[표준 편차] C --> D3[성공률] C --> D4[실행 횟수] D1 --> E[Step 정렬  
avg_time 기준] D2 --> E D3 --> E D4 --> E E --> F[Bottleneck 식별  
Top 3 slowest] E --> G{고분산 Step?} G -->|Yes| H1[불안정 경고] E --> I{저성공률 Step?} I -->|Yes| H2[신뢰성 경고] E --> J[Branch 탐지] J --> K[병렬화 기회 제안] F --> L[최적화 권장사항 생성] H1 --> L H2 --> L K --> L style A fill:#667eea,color:#fff style C fill:#48bb78,color:#fff style F fill:#e53e3e,color:#fff style K fill:#10b981,color:#fff style L fill:#3182ce,color:#fff 

### track_step() 메서드

**위치** : Lines 1758-1781

**목적** : 개별 Workflow Step 실행 기록

def track_step( self, task_id: str, step_name: str, step_type: str, # chain_step, node, edge, branch success: bool, execution_time: float, framework: str = "langchain", metadata: Optional[Dict[str, Any]] = None ) -> Dict[str, Any]: """Track individual workflow step execution""" step = { "task_id": task_id, "step_name": step_name, "step_type": step_type, "success": success, "execution_time": execution_time, "framework": framework, "timestamp": datetime.now(), "metadata": metadata or {} } self.executions.append(step) return step 

### calculate_execution_success_rate() 메서드

**위치** : Lines 1783-1821

**목적** : Workflow 실행 성공률 계산

def calculate_execution_success_rate( self, task_id: Optional[str] = None, framework: Optional[str] = None ) -> Dict[str, Any]: """Calculate workflow execution success rate""" executions = self.executions # 필터링 if task_id: executions = [e for e in executions if e["task_id"] == task_id] if framework: executions = [e for e in executions if e["framework"] == framework] if not executions: return {"success_rate": 0, "total_steps": 0} # Step Success Rate success_count = sum(1 for e in executions if e["success"]) success_rate = (success_count / len(executions)) * 100 # Task 그룹화 task_groups = defaultdict(list) for e in executions: task_groups[e["task_id"]].append(e) # Fully Successful Tasks (모든 Step 성공) fully_successful_tasks = sum( 1 for steps in task_groups.values() if all(s["success"] for s in steps) ) return { "step_success_rate": round(success_rate, 2), "total_steps": len(executions), "successful_steps": success_count, "failed_steps": len(executions) - success_count, "total_tasks": len(task_groups), "fully_successful_tasks": fully_successful_tasks, "task_success_rate": round((fully_successful_tasks / len(task_groups)) * 100, 2) if task_groups else 0, "avg_steps_per_task": round(len(executions) / len(task_groups), 2) if task_groups else 0 } 

### get_critical_path_analysis() 메서드

**위치** : Lines 1847-1937

**목적** : Critical Path와 Bottleneck 분석, 최적화 권장사항 생성

def get_critical_path_analysis(self) -> Dict[str, Any]: """Analyze critical path and bottlenecks in workflow execution""" if not self.executions: return {"total_workflows": 0} # Task별 그룹화 task_groups = defaultdict(list) for execution in self.executions: task_groups[execution["task_id"]].append(execution) # Step별 통계 수집 step_stats = defaultdict(lambda: { "execution_times": [], "success_count": 0, "failure_count": 0, "total_count": 0 }) for task_id, steps in task_groups.items(): for step in steps: step_name = step["step_name"] step_stats[step_name]["execution_times"].append(step["execution_time"]) step_stats[step_name]["total_count"] += 1 if step["success"]: step_stats[step_name]["success_count"] += 1 else: step_stats[step_name]["failure_count"] += 1 # Step별 분석 step_analysis = [] for step_name, stats in step_stats.items(): times = stats["execution_times"] step_analysis.append({ "step_name": step_name, "avg_time": round(statistics.mean(times), 3), "median_time": round(statistics.median(times), 3), "max_time": round(max(times), 3), "std_time": round(statistics.stdev(times), 3) if len(times) > 1 else 0.0, "success_rate": round((stats["success_count"] / stats["total_count"]) * 100, 2) }) # 평균 시간 기준 정렬 (Critical Path) step_analysis.sort(key=lambda x: x["avg_time"], reverse=True) # Bottleneck 식별 (Top 3) bottlenecks = step_analysis[:3] if len(step_analysis) >= 3 else step_analysis # 최적화 권장사항 생성 recommendations = self._generate_optimization_recommendations(step_analysis, bottlenecks) return { "total_workflows": len(task_groups), "critical_path": step_analysis, "bottlenecks": bottlenecks, "optimization_recommendations": recommendations } 

#### Critical Path Analysis 항목

  * **avg_time** : 평균 실행 시간 (Bottleneck 식별)
  * **std_time** : 표준 편차 (성능 안정성)
  * **success_rate** : 성공률 (신뢰성)
  * **bottlenecks** : Top 3 느린 단계
  * **recommendations** : 자동 생성 최적화 제안

## 💻 사용 예제

### 기본 사용법

from agent_evaluator import WorkflowExecutionTracker # 트래커 초기화 tracker = WorkflowExecutionTracker() # Step 기록 tracker.track_step( task_id="workflow_001", step_name="retrieve_docs", step_type="chain_step", success=True, execution_time=0.523, framework="langchain" ) tracker.track_step( task_id="workflow_001", step_name="generate_response", step_type="chain_step", success=True, execution_time=1.847, framework="langchain" ) # 성공률 계산 stats = tracker.calculate_execution_success_rate() print(f"Step Success Rate: {stats['step_success_rate']}%") print(f"Task Success Rate: {stats['task_success_rate']}%") # Critical Path 분석 analysis = tracker.get_critical_path_analysis() print(f"Bottlenecks: {analysis['bottlenecks']}") print(f"Recommendations: {analysis['optimization_recommendations']}") 

### LangChain 통합 예제

from langchain.chains import LLMChain, SequentialChain from agent_evaluator import WorkflowExecutionTracker import time tracker = WorkflowExecutionTracker() # Custom Callback for Tracking class TrackingCallback: def on_chain_start(self, chain_name): self.start_time = time.time() def on_chain_end(self, chain_name, success): execution_time = time.time() - self.start_time tracker.track_step( task_id="rag_pipeline", step_name=chain_name, step_type="chain_step", success=success, execution_time=execution_time, framework="langchain" ) # Chain 실행 후 분석 stats = tracker.calculate_execution_success_rate(framework="langchain") print(f"LangChain Success Rate: {stats['step_success_rate']}%") 

### LangGraph 통합 예제

from langgraph.graph import StateGraph from agent_evaluator import WorkflowExecutionTracker tracker = WorkflowExecutionTracker() # Node 실행 추적 def tracked_node(state): start = time.time() success = True try: # Node 로직 result = process_state(state) except Exception as e: success = False raise finally: tracker.track_step( task_id=state["task_id"], step_name="process_node", step_type="node", success=success, execution_time=time.time() - start, framework="langgraph" ) return result # Graph Traversal Efficiency 계산 efficiency = tracker.get_graph_traversal_efficiency("task_001") print(f"Graph Efficiency: {efficiency['efficiency']}%") print(f"Nodes Executed: {efficiency['nodes_executed']}") 

## 📈 최적화 권장사항

### 자동 생성 권장사항 예시

#### ⚠️ 자동 탐지되는 문제

  * **느린 단계** : avg_time > 1.0s → "Optimize 'step_name' - average time 2.5s is high"
  * **불안정한 성능** : std_time > avg_time × 0.5 → "Investigate 'step_name' - high variance indicates inconsistent performance"
  * **낮은 성공률** : success_rate < 90% → "Improve reliability of 'step_name' - success rate 75% is below target"

### 최적화 전략

문제 | 원인 | 해결책  
---|---|---  
Bottleneck (느린 단계) | 외부 API 호출, 복잡한 연산 | 캐싱, 병렬화, 경량 모델 사용  
높은 분산 (불안정) | 네트워크 지연, 입력 크기 변동 | Timeout 설정, 입력 정규화  
낮은 성공률 | 잘못된 로직, 에러 처리 부족 | Retry 로직, Exception Handling  
많은 Step 수 | 불필요한 중간 단계 | Step 병합, 워크플로우 단순화  
  
## 🔗 관련 지표

관련 지표 | 관계 | 문서 링크  
---|---|---  
**Latency Metrics** | Workflow 단계별 지연 측정 | [Latency 가이드](<05_LATENCY_METRICS.html>)  
**Task Completion Rate** | Workflow 성공이 TCR에 영향 | [Task Completion 가이드](<01_TASK_COMPLETION_RATE.html>)  
**Agent Coordination** | Multi-Agent Workflow 협업 분석 | [Coordination 가이드](<12_AGENT_COORDINATION.html>)  
  
## 📋 요약

**Workflow Execution Tracking** 은 LangChain/LangGraph 워크플로우의 성능을 분석하는 핵심 Layer 2 지표입니다. 

  * **Step-level 추적** : 각 단계의 성공률, 실행 시간 측정
  * **Critical Path 분석** : Bottleneck 단계 자동 식별
  * **최적화 권장** : 느린 단계, 불안정한 성능, 낮은 성공률 자동 탐지
  * **적용 대상** : LangChain Chains, LangGraph StatefulGraph
  * **목표** : Task Success Rate 90% 이상

  
Layer 2 메트릭으로 복잡한 워크플로우의 성능 병목을 분석하며, LangChain/LangGraph 기반 프로덕션 시스템 최적화에 필수적입니다. 

## 📚 참고 자료

  * [Agent Evaluator 메인 문서](<../README.html>)
  * [종합 학습 가이드](<../LEARNING_GUIDE.html>)
  * [LangChain Documentation](<https://python.langchain.com/>)
  * [LangGraph Documentation](<https://langchain-ai.github.io/langgraph/>)

**최종 업데이트** : 2025-12-18 | **버전** : Agent Evaluator v0.5.1

**문서** : Workflow Execution Tracking 상세 가이드 (Layer 2 Metric)

© 2025 Agent Evaluator. All rights reserved.
