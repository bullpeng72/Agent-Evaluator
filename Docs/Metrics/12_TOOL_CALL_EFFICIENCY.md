# ⚡ Tool Call Efficiency

AI Agent Tool Usage Optimization Analysis

Agent Evaluator v0.5.2 - Layer 2 Advanced Metric

## 🎯 개요

**Tool Call Efficiency (도구 호출 효율성)** 는 AI Agent의 Tool 사용 효율성을 정량화하는 Layer 2 Advanced Metric입니다. 

  * **측정 대상** : Tool Call의 중복도, 실패율, 실행 시간
  * **평가 지표** : Efficiency Score (0-100), Redundancy Rate, Failure Rate
  * **적용 대상** : AutoGen, LangChain, CrewAI 등 Tool-using Agents
  * **구현 위치** : `agent_evaluator/core/agent_evaluator.py` (Lines 1195-1355)

#### ⚠️ Tool Call Efficiency가 중요한 이유

  * **비용 절감** : 중복/불필요한 Tool 호출 → API 비용 증가
  * **성능 향상** : 최적화된 Tool 사용 → 응답 시간 단축
  * **안정성** : 실패율 감소 → 작업 성공률 증가
  * **사용자 경험** : 빠른 처리 → 만족도 향상

#### 🏗️ 구현 특징

  * **클래스** : `ToolCallAnalyzer` (agent_evaluator.py:1195-1355)
  * **평가 방식** : Waste Rate 기반 (Redundancy + Failure)
  * **Layer 2 분류** : Agentic AI Performance (Tool 사용 최적화)
  * **외부 의존성** : 없음 (pandas만 사용)

## 📊 핵심 평가 메트릭

### Efficiency Score (효율성 점수)

#### 계산 공식
```python
    waste_rate = (redundant_calls + failed_calls) / total_calls
    efficiency_score = max(0, 100 - (waste_rate × 100))
                    
```

**의미** : 100점에서 낭비율을 뺀 점수

  * 100점: 모든 Tool Call이 필요하고 성공적
  * 80점: 20%의 Tool Call이 중복 또는 실패
  * 50점: 50%의 Tool Call이 낭비됨
  * 0점: 100% 낭비 (모두 중복/실패)

### 3가지 핵심 지표

지표 | 정의 | 계산식 | 목표  
---|---|---|---  
Redundancy Rate | 중복 호출 비율 | redundant / total × 100 | < 10%  
Failure Rate | 실패 호출 비율 | failed / total × 100 | < 5%  
Avg Duration | 평균 실행 시간 | sum(duration) / count | 작을수록 좋음  
  
### Efficiency Score 등급

점수 범위 | 등급 | 상태 | 조치  
---|---|---|---  
90-100 | Excellent | 최적화됨 | 현 상태 유지  
75-89 | Good | 양호 | 소폭 개선 검토  
50-74 | Fair | 개선 필요 | 중복/실패 분석  
0-49 | Poor | 심각 | 즉시 최적화 필요  
  
## 🔍 데이터 수집 방법 (실전 가이드)

#### 💡 데이터 수집 핵심 원칙

Tool Call Efficiency 측정을 위해서는 **실제 Tool 호출 기록** 이 필요합니다:

  * **필수 데이터** : tool_name, parameters, success 상태
  * **권장 데이터** : duration (실행 시간), timestamp
  * **수집 방법** : Framework Integration (자동) 또는 Helper Functions (수동)

### 방법 1: Framework Integration (자동 수집) 🚀

가장 권장하는 방법입니다. Framework별 Evaluator가 Tool 호출을 자동으로 추적합니다.

#### LangChain Integration

from agent_evaluator.integrations import LangChainEvaluator, AdvancedLangChainCallback from langchain.agents import AgentExecutor, create_react_agent from langchain_openai import ChatOpenAI from langchain.tools import Tool # Tools 정의 tools = [ Tool( name="search", func=lambda query: f"Search results for {query}", description="Search the web" ), Tool( name="calculator", func=lambda expr: eval(expr), description="Calculate mathematical expressions" ) ] # Agent 생성 llm = ChatOpenAI(model="gpt-4") agent = create_react_agent(llm, tools, prompt) agent_executor = AgentExecutor(agent=agent, tools=tools) # Evaluator로 감싸기 (Tool Call 자동 추적) evaluator = LangChainEvaluator( agent_executor, enable_layer2=True # ✅ Tool Call Efficiency 자동 측정 ) # 실행 (Tool 호출이 자동으로 추적됨) result = evaluator.run( query="What is 25 * 4? Then search for 'AI agents'", ground_truth="100, AI agents search results" ) # Tool Call Efficiency 지표 확인 print(f"Efficiency Score: {result.layer2_metrics['tool_call_efficiency']['efficiency_score']}") print(f"Redundancy Rate: {result.layer2_metrics['tool_call_efficiency']['redundancy_rate']}%") print(f"Failure Rate: {result.layer2_metrics['tool_call_efficiency']['failure_rate']}%") # 상세 Tool Call 리스트 for call in result.tool_calls: print(f"Tool: {call['tool']}, Success: {call.get('success', True)}, Duration: {call.get('duration', 0)}") 

#### 🔧 LangChain에서 자동 수집되는 데이터

  * **tool_name** : action.tool
  * **parameters** : action.tool_input
  * **success** : 예외 발생 여부로 판단
  * **duration** : on_agent_action ~ on_tool_end 시간 차이
  * **output** : observation (Tool 실행 결과)

**구현 위치** : agent_evaluator/integrations/langchain_integration.py (AdvancedLangChainCallback)

#### AutoGen Integration

from agent_evaluator.integrations import AutoGenEvaluator from autogen import AssistantAgent, UserProxyAgent # AutoGen Agent 설정 assistant = AssistantAgent( name="assistant", llm_config={"model": "gpt-4"}, system_message="You are a helpful AI assistant with access to tools." ) user_proxy = UserProxyAgent( name="user", human_input_mode="NEVER", code_execution_config={"work_dir": "coding"} ) # Evaluator로 감싸기 evaluator = AutoGenEvaluator( assistant, enable_layer2=True # Tool Call 추적 활성화 ) # 실행 result = evaluator.run( message="Calculate 100 + 200 and save it to a file", ground_truth="300 saved to file" ) # 효율성 지표 확인 efficiency = result.layer2_metrics['tool_call_efficiency'] print(f"Total Calls: {efficiency['total_calls']}") print(f"Redundant: {efficiency['redundant_calls']}") print(f"Failed: {efficiency['failed_calls']}") print(f"Efficiency Score: {efficiency['efficiency_score']}") 

#### CrewAI Integration

from agent_evaluator.integrations import CrewAIEvaluator from crewai import Agent, Task, Crew from crewai_tools import SerperDevTool, FileWriterTool # CrewAI Agent 설정 search_tool = SerperDevTool() writer_tool = FileWriterTool() agent = Agent( role="Researcher", goal="Research and save information", tools=[search_tool, writer_tool], verbose=True ) task = Task( description="Research AI trends and save to report.txt", agent=agent ) crew = Crew(agents=[agent], tasks=[task]) # Evaluator로 감싸기 evaluator = CrewAIEvaluator( crew, enable_layer2=True ) # 실행 result = evaluator.kickoff( inputs={"topic": "AI trends 2024"}, ground_truth="AI trends report saved" ) # Tool 사용 효율성 분석 efficiency = result.layer2_metrics['tool_call_efficiency'] print(f"Efficiency Score: {efficiency['efficiency_score']}") print(f"Avg Duration: {efficiency['avg_call_duration']}s") 

### 방법 2: Helper Functions (수동 추출) 🔧

Framework Integration을 사용할 수 없는 경우 Helper Functions로 수동 추출합니다.

#### LangChain 결과에서 Tool Call 추출

from agent_evaluator import extract_tool_calls_from_langchain from agent_evaluator import ToolCallAnalyzer # LangChain Agent 직접 실행 result = agent_executor.invoke({"input": "Search for AI and calculate 2+2"}) # Tool Calls 자동 추출 tool_calls = extract_tool_calls_from_langchain(result) # Returns: [ # {"tool": "search", "input": {"query": "AI"}, "output": "..."}, # {"tool": "calculator", "input": {"expr": "2+2"}, "output": "4"} # ] # Analyzer로 효율성 분석 analyzer = ToolCallAnalyzer() # Tool Call 형식 변환 (Helper가 반환한 형식 → Analyzer 형식) formatted_calls = [] for call in tool_calls: formatted_calls.append({ "tool_name": call["tool"], "parameters": call.get("input", {}), "success": True, # 실패 여부는 예외로 판단 "duration": 0 # 수동으로 duration 측정 필요 }) metrics = analyzer.analyze_execution("task_001", formatted_calls) print(f"Efficiency Score: {metrics['efficiency_score']}") 

#### 📍 extract_tool_calls_from_langchain() 구현

**위치** : agent_evaluator/helpers/taskresult_helpers.py:348-376

**기능** : LangChain의 intermediate_steps에서 Tool 호출 추출

  * intermediate_steps는 [(AgentAction, observation), ...] 형식
  * AgentAction.tool → tool 이름
  * AgentAction.tool_input → parameters
  * observation → Tool 실행 결과

#### OpenAI Function Calls 추출

from agent_evaluator import extract_tool_calls_from_openai_functions # OpenAI API 직접 호출 (Function Calling) response = openai.ChatCompletion.create( model="gpt-4", messages=[{"role": "user", "content": "Search for weather and file it"}], functions=[ {"name": "get_weather", "parameters": {...}}, {"name": "write_file", "parameters": {...}} ] ) # Function Call 추출 tool_calls = extract_tool_calls_from_openai_functions(response) # Returns: [ # {"tool": "get_weather", "input": {"location": "Seoul"}}, # {"tool": "write_file", "input": {"path": "weather.txt", "content": "..."}} # ] # Analyzer로 효율성 분석 analyzer = ToolCallAnalyzer() formatted_calls = [ { "tool_name": call["tool"], "parameters": call["input"], "success": True } for call in tool_calls ] metrics = analyzer.analyze_execution("task_openai", formatted_calls) 

#### 📍 extract_tool_calls_from_openai_functions() 구현

**위치** : agent_evaluator/helpers/taskresult_helpers.py:379-403

**지원 형식** :

  * OpenAI ChatCompletion 응답
  * response.choices[0].message.function_call
  * response.choices[0].message.tool_calls (최신 API)

#### 완전 수동 수집 (Custom Framework)

from agent_evaluator import ToolCallAnalyzer import time class CustomAgentWrapper: def __init__(self, agent): self.agent = agent self.analyzer = ToolCallAnalyzer() def run_with_tracking(self, task_id, query): """Tool Call을 수동으로 추적하며 실행""" tool_calls = [] # Agent 실행하며 Tool 호출 기록 for step in self.agent.execute(query): if step.get("type") == "tool_call": start_time = time.time() try: # Tool 실행 result = self._execute_tool( step["tool_name"], step["parameters"] ) success = True except Exception as e: result = str(e) success = False duration = time.time() - start_time # Tool Call 기록 tool_calls.append({ "tool_name": step["tool_name"], "parameters": step["parameters"], "success": success, "duration": duration, "result": result }) # 효율성 분석 metrics = self.analyzer.analyze_execution(task_id, tool_calls) return { "tool_calls": tool_calls, "efficiency_metrics": metrics } # 사용 agent = CustomAgent() wrapper = CustomAgentWrapper(agent) result = wrapper.run_with_tracking("task_001", "Process this data") print(f"Efficiency Score: {result['efficiency_metrics']['efficiency_score']}") print(f"Redundant Calls: {result['efficiency_metrics']['redundant_calls']}") 

### 방법 3: 프로덕션 환경 모니터링 📊

프로덕션에서는 모든 Tool 호출을 추적하고 주기적으로 효율성을 분석합니다.

from agent_evaluator import ToolCallAnalyzer import logging class ProductionEfficiencyMonitor: def __init__(self, sample_rate=0.1): self.analyzer = ToolCallAnalyzer() self.sample_rate = sample_rate # 10% 샘플링 self.logger = logging.getLogger(__name__) def track_execution(self, task_id, tool_calls): """Tool 호출 기록 및 샘플링 분석""" import random # 샘플링 (전체 트래픽의 10%만 분석) if random.random() > self.sample_rate: return None # 효율성 분석 metrics = self.analyzer.analyze_execution(task_id, tool_calls) # 비효율적인 경우 경고 if metrics["efficiency_score"] < 70: self.logger.warning( f"Low efficiency detected: Task {task_id} - " f"Score: {metrics['efficiency_score']}, " f"Redundant: {metrics['redundant_calls']}, " f"Failed: {metrics['failed_calls']}" ) return metrics def get_daily_report(self): """일간 효율성 리포트""" stats = self.analyzer.get_efficiency_stats() report = f""" 📊 Tool Call Efficiency Report ================================ Period: Last 24 hours (Sampled {self.sample_rate*100}%) Overall Metrics: \- Avg Efficiency Score: {stats['avg_efficiency_score']} \- Total Calls: {stats['total_calls']} \- Redundancy Rate: {stats['redundancy_rate']}% \- Failure Rate: {stats['failure_rate']}% \- Success Rate: {stats['success_rate']}% \- Avg Duration: {stats['avg_duration']}s Optimization Opportunities: \- {stats['total_redundant_calls']} redundant calls detected \- {stats['total_failed_calls']} failed calls to investigate \- Avg {stats['avg_calls_per_task']} calls per task """ return report # 프로덕션 사용 monitor = ProductionEfficiencyMonitor(sample_rate=0.1) # Agent 실행 후 추적 def execute_agent_task(task_id, query): tool_calls = agent.run(query) # 실제 Agent 실행 monitor.track_execution(task_id, tool_calls) return tool_calls # 일간 리포트 생성 (Cron Job 등으로 스케줄링) def generate_daily_report(): report = monitor.get_daily_report() print(report) # 또는 Slack/Email로 전송

#### ⚠️ 프로덕션 데이터 수집 시 주의사항

  * **성능 오버헤드** : 샘플링(10-20%)으로 부담 최소화
  * **Duration 측정** : time.time()보다 time.perf_counter() 사용 권장
  * **Parameters 크기** : 큰 데이터(파일 내용 등)는 해시로 대체
  * **성공/실패 판단** : 예외 발생 = 실패, 그 외 = 성공으로 기본 처리
  * **중복 정의** : 의도적인 재시도는 중복이 아님 (retry 로직과 구분)

## 🚨 실전 배포 시 주의사항

### 1\. Duration 정확도 개선

import time # ❌ 부정확: time.time() (시스템 시간 변경 영향) start = time.time() execute_tool() duration = time.time() - start # ✅ 권장: time.perf_counter() (단조 증가 시계) start = time.perf_counter() execute_tool() duration = time.perf_counter() - start 

### 2\. 대용량 Parameters 처리

import hashlib import json def normalize_parameters(params: dict) -> str: """Parameters를 중복 검사용으로 정규화""" # 큰 데이터는 해시로 대체 normalized = {} for key, value in params.items(): if isinstance(value, str) and len(value) > 1000: # 긴 문자열은 SHA256 해시로 normalized[key] = f"" elif isinstance(value, (list, dict)) and len(str(value)) > 1000: # 큰 객체도 해시로 normalized[key] = f"" else: normalized[key] = value return json.dumps(normalized, sort_keys=True) # Analyzer에서 사용 class ImprovedToolCallAnalyzer(ToolCallAnalyzer): def _count_redundant_calls(self, tool_calls): seen = set() redundant = 0 for call in tool_calls: tool_name = call.get("tool_name", "unknown") params_str = normalize_parameters(call.get("parameters", {})) key = (tool_name, params_str) if key in seen: redundant += 1 seen.add(key) return redundant 

### 3\. 의도적 재시도 vs 중복 구분

# Tool Call에 retry 정보 포함 tool_call = { "tool_name": "api_call", "parameters": {"endpoint": "/users"}, "success": True, "is_retry": True, # ✅ 재시도 표시 "retry_count": 2 } # Analyzer 수정: 재시도는 중복에서 제외 def _count_redundant_calls(self, tool_calls): seen = set() redundant = 0 for call in tool_calls: # 재시도는 중복이 아님 if call.get("is_retry", False): continue # 일반 중복 검사 key = (get_tool_name(call), get_params_str(call)) if key in seen: redundant += 1 seen.add(key) return redundant 

### 4\. 실시간 경고 시스템

from agent_evaluator import ToolCallAnalyzer import logging class RealTimeEfficiencyAlerts: def __init__(self, thresholds=None): self.analyzer = ToolCallAnalyzer() self.logger = logging.getLogger(__name__) self.thresholds = thresholds or { "efficiency_score": 70, # < 70: Warning "redundancy_rate": 15, # > 15%: Warning "failure_rate": 10, # > 10%: Critical "avg_duration": 5.0 # > 5s: Slow } def check_and_alert(self, task_id, tool_calls): """실시간 효율성 체크 및 경고""" metrics = self.analyzer.analyze_execution(task_id, tool_calls) alerts = [] # 효율성 점수 체크 if metrics["efficiency_score"] < self.thresholds["efficiency_score"]: alerts.append(f"🟡 Low efficiency: {metrics['efficiency_score']}") # 중복률 체크 if metrics["total_calls"] > 0: redundancy_rate = (metrics["redundant_calls"] / metrics["total_calls"]) * 100 if redundancy_rate > self.thresholds["redundancy_rate"]: alerts.append(f"🟡 High redundancy: {redundancy_rate:.1f}%") # 실패율 체크 if metrics["total_calls"] > 0: failure_rate = (metrics["failed_calls"] / metrics["total_calls"]) * 100 if failure_rate > self.thresholds["failure_rate"]: alerts.append(f"🔴 High failure rate: {failure_rate:.1f}%") # Duration 체크 if metrics["avg_call_duration"] > self.thresholds["avg_duration"]: alerts.append(f"🐢 Slow tools: {metrics['avg_call_duration']:.2f}s") # 경고 로깅 if alerts: self.logger.warning(f"Task {task_id} efficiency issues: {', '.join(alerts)}") return {"metrics": metrics, "alerts": alerts} # 사용 alerts = RealTimeEfficiencyAlerts() result = alerts.check_and_alert("task_001", tool_calls) if result["alerts"]: print("⚠️ Efficiency Issues Detected:") for alert in result["alerts"]: print(f" {alert}") 

#### 💡 배포 체크리스트

  * ✅ **샘플링 설정** : 10-20% 샘플링으로 성능 부담 최소화
  * ✅ **Duration 측정** : time.perf_counter() 사용
  * ✅ **Parameters 정규화** : 큰 데이터는 해시로 대체
  * ✅ **재시도 구분** : is_retry 플래그로 중복과 구분
  * ✅ **실시간 경고** : 임계값 기반 알림 시스템
  * ✅ **주기적 리포트** : 일간/주간 효율성 분석
  * ✅ **Tool별 통계** : get_tool_usage_patterns()로 개별 Tool 분석

## ⚙️ 핵심 알고리즘

#### 📊 Tool Call Efficiency 분석 흐름

graph TD A[tool_calls 리스트] --> B[Tool 이름 추출] B --> C1[total_calls  
전체 호출 수] B --> C2[unique_tools  
고유 Tool 수] A --> D[Redundancy 검사] D --> E[Tool + Parameters  
조합으로 중복 탐지] E --> F[redundant_calls] A --> G[Failure 검사] G --> H[success=False 카운트] H --> I[failed_calls] A --> J[Duration 계산] J --> K[평균 실행 시간] F --> L[Waste Rate 계산] I --> L C1 --> L L --> M[Efficiency Score  
100 - waste_rate × 100] M --> N[result 반환  
metrics] style A fill:#667eea,color:#fff style D fill:#ed8936,color:#fff style G fill:#e53e3e,color:#fff style L fill:#f59e0b,color:#fff style M fill:#48bb78,color:#fff style N fill:#3182ce,color:#fff 

### analyze_execution() 메서드

**위치** : Lines 1206-1247

**목적** : Task의 Tool Call을 분석하여 효율성 평가

def analyze_execution(self, task_id: str, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]: """Analyze tool calls for a task""" if not tool_calls: return { "task_id": task_id, "total_calls": 0, "efficiency_score": 100.0 } # Tool 이름 추출 (dict/string 모두 지원) tool_names = [] for call in tool_calls: if isinstance(call, str): tool_name = call elif isinstance(call, dict): tool_name = call.get("tool_name") or call.get("tool") or call.get("name", "unknown") else: tool_name = "unknown" tool_names.append(tool_name) # Duration 추출 (duration 있는 것만) durations = [call.get("duration", 0) for call in tool_calls if isinstance(call, dict) and "duration" in call] metrics = { "task_id": task_id, "total_calls": len(tool_calls), "unique_tools": len(set(tool_names)), "redundant_calls": self._count_redundant_calls(tool_calls), "failed_calls": sum(1 for call in tool_calls if isinstance(call, dict) and not call.get("success", True)), "avg_call_duration": statistics.mean(durations) if durations else 0 } # Efficiency Score 계산 if metrics["total_calls"] > 0: waste_rate = (metrics["redundant_calls"] + metrics["failed_calls"]) / metrics["total_calls"] metrics["efficiency_score"] = round(max(0, 100 - (waste_rate * 100)), 2) else: metrics["efficiency_score"] = 100.0 self.executions.append(metrics) return metrics 

### _count_redundant_calls() 메서드

**위치** : Lines 1249-1269

**목적** : 동일한 Tool + Parameters 조합의 중복 호출 탐지

def _count_redundant_calls(self, tool_calls: List) -> int: """Count redundant tool calls""" seen = set() redundant = 0 for call in tool_calls: if isinstance(call, str): # String tool call: 이름만 비교 key = (call, "{}") elif isinstance(call, dict): # Dict tool call: 이름 + Parameters 비교 tool_name = call.get("tool_name") or call.get("tool") or call.get("name", "unknown") key = (tool_name, json.dumps(call.get("parameters", {}), sort_keys=True)) else: continue if key in seen: redundant += 1 seen.add(key) return redundant 

#### 중복 탐지 로직

  * **Tool + Parameters 조합** : 동일한 Tool을 동일한 인자로 호출 → 중복
  * **Parameters 정규화** : JSON 직렬화 + sort_keys로 순서 무관하게 비교
  * **예시** : 
```Tool 1: read_file(path="/data/file.txt")
        Tool 2: read_file(path="/data/file.txt")  // 중복!
        Tool 3: read_file(path="/data/other.txt") // 중복 아님 (다른 파라미터)
                                
```

### get_efficiency_stats() 메서드

**위치** : Lines 1271-1294

**목적** : 여러 Task의 효율성 통계 집계

def get_efficiency_stats(self) -> Dict[str, Any]: """Get tool call efficiency statistics""" if not self.executions: return {} df = pd.DataFrame(self.executions) total_calls = int(df["total_calls"].sum()) return { "total_calls": total_calls, "success_rate": round((1 - df["failed_calls"].sum() / total_calls) * 100, 2) if total_calls > 0 else 0, "avg_duration": round(df["avg_call_duration"].mean(), 3), "avg_calls_per_task": round(df["total_calls"].mean(), 2), "avg_efficiency_score": round(df["efficiency_score"].mean(), 2), "total_redundant_calls": int(df["redundant_calls"].sum()), "total_failed_calls": int(df["failed_calls"].sum()), "redundancy_rate": round((df["redundant_calls"].sum() / total_calls) * 100, 2) if total_calls > 0 else 0, "failure_rate": round((df["failed_calls"].sum() / total_calls) * 100, 2) if total_calls > 0 else 0 } 

#### 통계 항목 설명

  * **total_calls** : 전체 Tool 호출 수
  * **success_rate** : 성공률 = (1 - failed/total) × 100
  * **avg_duration** : 평균 실행 시간
  * **avg_calls_per_task** : Task당 평균 Tool 호출 수
  * **avg_efficiency_score** : 평균 효율성 점수
  * **redundancy_rate** : 중복 비율 (%)
  * **failure_rate** : 실패 비율 (%)

## 💻 사용 예제

### 기본 사용법

from agent_evaluator import ToolCallAnalyzer # Analyzer 초기화 analyzer = ToolCallAnalyzer() # 시나리오 1: 효율적인 Tool 사용 efficient_calls = [ {"tool_name": "search", "parameters": {"query": "AI"}, "success": True, "duration": 0.5}, {"tool_name": "read_file", "parameters": {"path": "/data/1.txt"}, "success": True, "duration": 0.2}, {"tool_name": "write_file", "parameters": {"path": "/out.txt"}, "success": True, "duration": 0.3} ] result1 = analyzer.analyze_execution("task_001", efficient_calls) print(result1) # { # "total_calls": 3, # "unique_tools": 3, # "redundant_calls": 0, # "failed_calls": 0, # "efficiency_score": 100.0 // 완벽한 효율성 # } # 시나리오 2: 비효율적인 Tool 사용 (중복 + 실패) inefficient_calls = [ {"tool_name": "search", "parameters": {"query": "AI"}, "success": True}, {"tool_name": "search", "parameters": {"query": "AI"}, "success": True}, # 중복! {"tool_name": "read_file", "parameters": {"path": "/invalid"}, "success": False}, # 실패! {"tool_name": "write_file", "parameters": {"path": "/out.txt"}, "success": True} ] result2 = analyzer.analyze_execution("task_002", inefficient_calls) print(result2) # { # "total_calls": 4, # "redundant_calls": 1, # "failed_calls": 1, # "efficiency_score": 50.0 // waste_rate = 2/4 = 0.5 → 100 - 50 = 50 # } # 통계 조회 stats = analyzer.get_efficiency_stats() print(f"Avg Efficiency Score: {stats['avg_efficiency_score']}") print(f"Redundancy Rate: {stats['redundancy_rate']}%") print(f"Failure Rate: {stats['failure_rate']}%") 

### Usage Pattern 분석

from agent_evaluator import ToolCallAnalyzer analyzer = ToolCallAnalyzer() # 여러 Task 실행 for i in range(10): tool_calls = generate_tool_calls() # 실제 Agent 실행 analyzer.analyze_execution(f"task_{i}", tool_calls) # Usage Pattern 분석 patterns = analyzer.get_tool_usage_patterns() print(f"Total Tasks: {patterns['total_tasks']}") print(f"Total Tool Calls: {patterns['total_tool_calls']}") # Pattern Analysis pa = patterns['pattern_analysis'] print(f"Avg Tools per Task: {pa['avg_tools_per_task']}") print(f"Max Tools in Single Task: {pa['max_tools_in_single_task']}") print(f"Tasks with Redundancy: {pa['tasks_with_redundancy']}") # Usage Distribution dist = patterns['usage_distribution'] print(f"Tasks with 1-2 calls: {dist['1-2_calls']}") print(f"Tasks with 3-5 calls: {dist['3-5_calls']}") print(f"Tasks with 6-10 calls: {dist['6-10_calls']}") print(f"Tasks with 11+ calls: {dist['11+_calls']}") # Efficiency Distribution eff_dist = patterns['efficiency_distribution'] print(f"Excellent (90-100): {eff_dist['excellent_90-100']}") print(f"Good (75-89): {eff_dist['good_75-89']}") print(f"Fair (50-74): {eff_dist['fair_50-74']}") print(f"Poor (0-49): {eff_dist['poor_0-49']}") 

### 실시간 최적화 예제

from agent_evaluator import ToolCallAnalyzer class OptimizedAgentWrapper: def __init__(self, agent): self.agent = agent self.analyzer = ToolCallAnalyzer() self.tool_cache = {} # 중복 방지 캐시 def execute_with_optimization(self, task_id, query): """Tool 호출 최적화를 적용한 실행""" tool_calls = [] # Agent 실행 (Tool 호출 추적) for tool_call in self.agent.run(query): # 중복 검사 cache_key = (tool_call["tool_name"], json.dumps(tool_call["parameters"], sort_keys=True)) if cache_key in self.tool_cache: # 캐시된 결과 사용 (중복 호출 방지) print(f"✅ Using cached result for {tool_call['tool_name']}") tool_call["success"] = True tool_call["result"] = self.tool_cache[cache_key] else: # 실제 Tool 실행 result = self._execute_tool(tool_call) tool_call["result"] = result self.tool_cache[cache_key] = result tool_calls.append(tool_call) # 효율성 분석 metrics = self.analyzer.analyze_execution(task_id, tool_calls) if metrics["efficiency_score"] < 70: print(f"⚠️ Low efficiency: {metrics['efficiency_score']}") print(f"Redundant: {metrics['redundant_calls']}, Failed: {metrics['failed_calls']}") return tool_calls # 사용 agent = YourAgent() wrapper = OptimizedAgentWrapper(agent) result = wrapper.execute_with_optimization("task_001", "Analyze this data") 

## 📈 최적화 전략

### 문제별 해결책

문제 | 원인 | 해결책  
---|---|---  
높은 Redundancy Rate | 동일한 Tool 반복 호출 | 결과 캐싱, Agent Prompt 개선  
높은 Failure Rate | 잘못된 파라미터, 권한 부족 | Input Validation, Retry 로직  
긴 Avg Duration | 느린 Tool, 비효율적 구현 | Tool 최적화, 병렬 처리  
많은 Tool Calls | 비효율적 접근 방식 | Tool 통합, Workflow 재설계  
  
#### ⚠️ 주의사항

  * **캐싱 주의** : 시간 의존적 Tool은 캐싱 부적합 (예: get_current_time)
  * **Parameters 비교** : 복잡한 객체는 비교 어려움
  * **False Positive** : 의도적인 재시도를 중복으로 오인 가능
  * **성능 오버헤드** : 분석 자체가 약간의 시간 소요

## 🔗 관련 지표

관련 지표 | 관계 | 문서 링크  
---|---|---  
**Tool Selection Accuracy** | 올바른 Tool 선택 + 효율적 사용 | [Tool Selection 가이드](<11_TOOL_SELECTION.html>)  
**Latency Metrics** | Tool Duration이 전체 지연에 영향 | [Latency 가이드](<05_LATENCY_METRICS.html>)  
**Cost/Token Economy** | 불필요한 Tool 호출이 비용 증가 | [Cost 가이드](<06_COST_TOKEN_ECONOMY.html>)  
**Retry Count** | Failure Rate과 Retry 연관 | [Retry 가이드](<07_RETRY_COUNT.html>)  
  
## 📋 요약

**Tool Call Efficiency** 는 AI Agent의 Tool 사용 효율성을 평가하는 Layer 2 지표입니다. 

  * **Efficiency Score** : 100 - (Waste Rate × 100)
  * **Waste Rate** : (Redundancy + Failure) / Total
  * **3가지 측정** : Redundancy Rate, Failure Rate, Avg Duration
  * **중복 탐지** : Tool + Parameters 조합으로 판단
  * **목표** : Efficiency Score 90 이상, Redundancy < 10%, Failure < 5%

  
Layer 2 메트릭으로 Agent의 Tool 사용 최적화를 측정하며, 프로덕션 AI 시스템의 비용 절감과 성능 향상에 필수적입니다. 

## 📚 참고 자료

  * [Agent Evaluator 메인 문서](<../README.html>)
  * [종합 학습 가이드](<../LEARNING_GUIDE.html>)
  * [Tool Selection Accuracy](<11_TOOL_SELECTION.html>)
  * [Latency Metrics](<05_LATENCY_METRICS.html>)

**최종 업데이트** : 2026-03-17 | **버전** : Agent Evaluator v0.5.2

**문서** : Tool Call Efficiency 상세 가이드 (Layer 2 Metric)

© 2025 Agent Evaluator. All rights reserved.
