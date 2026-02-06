# 🤝 Agent Coordination Quality

Multi-Agent System Interaction Pattern Analysis

Agent Evaluator v0.5.0 - Layer 2 Advanced Metric

## 🎯 개요

**Agent Coordination Quality (에이전트 협업 품질)** 는 Multi-Agent 시스템에서 에이전트 간 상호작용의 효율성과 패턴을 분석하는 Layer 2 Advanced Metric입니다. 

  * **측정 대상** : Agent-to-Agent 상호작용 (delegation, communication, collaboration)
  * **분석 항목** : Success Rate, Interaction Pattern (Hub/Chain/Mesh), Agent Roles
  * **적용 대상** : CrewAI, AutoGen 등 Multi-Agent Systems
  * **구현 위치** : `agent_evaluator/core/agent_evaluator.py` (Lines 1515-1745)

#### ⚠️ Agent Coordination이 중요한 이유

  * **복잡한 작업 해결** : 여러 Agent가 협력하여 단일 Agent로 불가능한 작업 수행
  * **효율성** : 올바른 Coordination Pattern → 병렬 처리, 중복 제거
  * **확장성** : Agent 추가 시 성능 선형 증가 가능
  * **신뢰성** : 단일 Agent 실패 시 다른 Agent가 보완

#### 🏗️ 구현 특징

  * **클래스** : `AgentCoordinationTracker` (agent_evaluator.py:1515-1745)
  * **분석 방식** : Graph Theory 기반 상호작용 패턴 탐지
  * **3가지 패턴** : Hub (중앙 집중), Chain (순차 처리), Mesh (완전 연결)
  * **Layer 2 분류** : Multi-Agent Behavior Analysis

## 🔄 3가지 Coordination 패턴

### 1\. Hub Pattern (중앙 집중형)

Hub Pattern

**특징** : 중앙 Agent가 모든 상호작용의 50% 이상 처리

**구조** : Star Topology - 한 Agent가 Hub 역할

  * **강점** : 
    * 명확한 지휘 체계
    * 작업 분배 효율적
    * 디버깅 용이 (중앙 집중)
  * **약점** : 
    * 단일 실패 지점 (Hub Agent 실패 시 전체 마비)
    * Hub Agent 병목 현상
    * 확장성 제한
  * **적용 시나리오** : Manager-Worker 패턴, Task Distribution

### 2\. Chain Pattern (순차 처리형)

Chain Pattern

**특징** : Agent들이 순차적으로 작업 전달 (Pipeline)

**구조** : Linear Topology - A → B → C → D

  * **강점** : 
    * 간단한 워크플로우
    * 명확한 의존성
    * 디버깅 쉬움
  * **약점** : 
    * 순차 병목 (앞 단계 지연 시 전체 지연)
    * 병렬화 불가
    * 확장성 낮음
  * **적용 시나리오** : ETL Pipeline, Sequential Processing

### 3\. Mesh Pattern (완전 연결형)

Mesh Pattern

**특징** : 모든 Agent가 서로 직접 통신 (50% 이상 연결)

**구조** : Fully Connected Graph

  * **강점** : 
    * 높은 중복성 (Redundancy)
    * 유연한 라우팅
    * 단일 실패 지점 없음
  * **약점** : 
    * 복잡한 조정 필요
    * 충돌 가능성 높음
    * 통신 오버헤드
  * **적용 시나리오** : Consensus Systems, Distributed Decision Making

## 🔍 데이터 수집 방법 (실전 가이드)

#### 💡 데이터 수집 핵심 원칙

Agent Coordination Quality 측정을 위해서는 **Agent 간 상호작용 기록** 이 필요합니다:

  * **필수 데이터** : from_agent, to_agent, interaction_type, success
  * **권장 데이터** : task_id, timestamp, context (상호작용 세부 정보)
  * **수집 방법** : Framework Integration (자동) 또는 Manual Tracking (수동)

### 방법 1: CrewAI Integration (자동 수집) 🚀

가장 권장하는 방법입니다. CrewAIEvaluator가 Agent 간 상호작용을 자동으로 추적합니다.

#### CrewAI 자동 추적 예제

from agent_evaluator.integrations import CrewAIEvaluator from crewai import Crew, Agent, Task, Process # Agents 정의 researcher = Agent( role="Researcher", goal="Research comprehensive information", backstory="Expert researcher with deep analytical skills", verbose=True ) writer = Agent( role="Writer", goal="Write engaging content", backstory="Skilled content creator", verbose=True ) editor = Agent( role="Editor", goal="Review and improve content", backstory="Meticulous editor with keen eye for detail", verbose=True ) # Tasks 정의 research_task = Task( description="Research {topic} thoroughly", agent=researcher, expected_output="Comprehensive research report" ) write_task = Task( description="Write article based on research", agent=writer, expected_output="Well-written article" ) edit_task = Task( description="Review and edit the article", agent=editor, expected_output="Polished final article" ) # Crew 생성 crew = Crew( agents=[researcher, writer, editor], tasks=[research_task, write_task, edit_task], process=Process.sequential # Chain Pattern ) # Evaluator로 감싸기 (Agent Coordination 자동 추적) evaluator = CrewAIEvaluator( crew, enable_layer2=True, # ✅ Agent Coordination 자동 추적 verbose=True ) # 실행 (Agent 간 상호작용이 자동으로 추적됨) result = evaluator.kickoff( inputs={"topic": "AI in Healthcare 2024"}, ground_truth="Expected comprehensive article about AI in healthcare", expected_agents=["Researcher", "Writer", "Editor"] ) # Agent Coordination 분석 coordination_score = evaluator.monitor.coordination_tracker.calculate_coordination_score() print(f"Coordination Score: {coordination_score['score']}/10") print(f"Success Rate: {coordination_score['success_rate']}%") print(f"Unique Agents: {coordination_score['unique_agents']}") # Interaction Pattern 분석 patterns = evaluator.monitor.coordination_tracker.get_interaction_patterns() print(f"\nPattern Type: {patterns['pattern_type']}") print(f"Pattern Confidence: {patterns['pattern_confidence']}%") if patterns['pattern_type'] == 'hub': print(f"Hub Agent: {patterns['hub_agent']}") # Agent 역할 분석 print(f"\nAgent Roles:") for agent, info in patterns['agent_roles'].items(): print(f" {agent}: {info['role']}") print(f" - Sends: {info['sends']}, Receives: {info['receives']}") 

#### 🔧 CrewAI에서 자동 수집되는 데이터

  * **from_agent** : 작업을 위임하거나 통신하는 Agent
  * **to_agent** : 작업을 받거나 응답하는 Agent
  * **interaction_type** : delegation (작업 위임), communication (정보 공유), collaboration (협업)
  * **success** : 상호작용 성공 여부
  * **task_id** : 전체 Crew 작업 ID
  * **context** : Task 정보, 결과 등

**구현 위치** : agent_evaluator/integrations/crewai_integration.py

#### CrewAI Process 별 Pattern

# Sequential Process → Chain Pattern crew_sequential = Crew( agents=[agent1, agent2, agent3], tasks=[task1, task2, task3], process=Process.sequential # A → B → C (Chain) ) # Hierarchical Process → Hub Pattern crew_hierarchical = Crew( agents=[manager, worker1, worker2, worker3], tasks=[...], process=Process.hierarchical, # Manager가 Hub manager_llm=llm ) # 평가 후 패턴 확인 evaluator_seq = CrewAIEvaluator(crew_sequential, enable_layer2=True) result_seq = evaluator_seq.kickoff(inputs={...}) patterns_seq = evaluator_seq.monitor.coordination_tracker.get_interaction_patterns() print(f"Sequential Crew Pattern: {patterns_seq['pattern_type']}") # Expected: "chain" evaluator_hier = CrewAIEvaluator(crew_hierarchical, enable_layer2=True) result_hier = evaluator_hier.kickoff(inputs={...}) patterns_hier = evaluator_hier.monitor.coordination_tracker.get_interaction_patterns() print(f"Hierarchical Crew Pattern: {patterns_hier['pattern_type']}") # Expected: "hub" print(f"Hub Agent: {patterns_hier['hub_agent']}") # Manager Agent

### 방법 2: AutoGen Integration (자동 수집) 🤖

AutoGen Multi-Agent 대화에서 Agent 간 상호작용을 자동으로 추적합니다.

#### AutoGen 자동 추적 예제

from agent_evaluator.integrations import AutoGenEvaluator from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager # Agents 정의 researcher = AssistantAgent( name="Researcher", system_message="You are a researcher. Research topics thoroughly.", llm_config={"model": "gpt-4"} ) analyst = AssistantAgent( name="Analyst", system_message="You are an analyst. Analyze data and provide insights.", llm_config={"model": "gpt-4"} ) writer = AssistantAgent( name="Writer", system_message="You are a writer. Create compelling content.", llm_config={"model": "gpt-4"} ) user_proxy = UserProxyAgent( name="User", human_input_mode="NEVER", code_execution_config={"work_dir": "workspace"} ) # GroupChat 설정 (Multi-Agent Coordination) groupchat = GroupChat( agents=[researcher, analyst, writer, user_proxy], messages=[], max_round=10 ) manager = GroupChatManager( groupchat=groupchat, llm_config={"model": "gpt-4"} ) # Evaluator로 감싸기 evaluator = AutoGenEvaluator( manager, enable_layer2=True # Agent Coordination 추적 ) # 대화 시작 (Agent 간 상호작용 자동 추적) user_proxy.initiate_chat( evaluator.agent, message="Research AI trends, analyze the data, and write a summary" ) # Coordination 분석 coordination = evaluator.monitor.coordination_tracker.calculate_coordination_score() patterns = evaluator.monitor.coordination_tracker.get_interaction_patterns() print(f"Coordination Score: {coordination['score']}/10") print(f"Pattern: {patterns['pattern_type']}") print(f"Total Agents: {patterns['total_agents']}") print(f"Total Interactions: {patterns['total_interactions']}") 

#### 📍 AutoGen에서 자동 추적되는 상호작용

  * **Agent → Agent 메시지** : generate_reply() 호출 시 추적
  * **GroupChat 내 발언** : 각 Agent의 발언이 다른 Agent에게 전달될 때
  * **작업 위임** : 특정 Agent에게 직접 요청 시 "delegation"으로 분류
  * **정보 공유** : 일반 대화는 "communication"으로 분류

**구현 위치** : agent_evaluator/integrations/autogen_integration.py

### 방법 3: 완전 수동 추적 (Custom Framework) 🔧

Framework Integration을 사용할 수 없는 경우 AgentCoordinationTracker를 직접 사용합니다.

#### 수동 Interaction 추적

from agent_evaluator import AgentCoordinationTracker class CustomMultiAgentSystem: def __init__(self): self.tracker = AgentCoordinationTracker() self.agents = {} def add_agent(self, name: str, agent): """Agent 등록""" self.agents[name] = agent def delegate_task(self, task_id: str, from_agent: str, to_agent: str, task_data): """작업 위임 및 추적""" try: # 작업 위임 result = self.agents[to_agent].execute(task_data) success = True except Exception as e: result = None success = False # ✅ Interaction 추적 self.tracker.track_interaction( task_id=task_id, from_agent=from_agent, to_agent=to_agent, interaction_type="delegation", success=success, context={ "task_type": task_data.get("type"), "result": str(result)[:100] if result else None } ) return result def communicate(self, task_id: str, from_agent: str, to_agent: str, message: str): """Agent 간 통신 및 추적""" try: # 메시지 전달 response = self.agents[to_agent].receive_message(from_agent, message) success = True except Exception as e: response = None success = False # ✅ Interaction 추적 self.tracker.track_interaction( task_id=task_id, from_agent=from_agent, to_agent=to_agent, interaction_type="communication", success=success, context={ "message": message[:50], # 첫 50자만 "response": str(response)[:50] if response else None } ) return response def collaborate(self, task_id: str, agents: List[str], shared_task): """여러 Agent 협업 및 추적""" results = {} for i, agent_name in enumerate(agents): try: result = self.agents[agent_name].contribute(shared_task, results) results[agent_name] = result success = True except Exception as e: success = False # ✅ Collaboration 추적 (모든 Agent 쌍) for other_agent in agents[:i]: self.tracker.track_interaction( task_id=task_id, from_agent=agent_name, to_agent=other_agent, interaction_type="collaboration", success=success, context={"shared_task": shared_task.get("name")} ) return results def get_coordination_analysis(self): """Coordination 분석 결과 반환""" score = self.tracker.calculate_coordination_score() patterns = self.tracker.get_interaction_patterns() return { "coordination_score": score, "patterns": patterns, "delegation_success_rate": self.tracker.get_delegation_success_rate() } # 사용 예제 system = CustomMultiAgentSystem() # Agents 등록 system.add_agent("Manager", ManagerAgent()) system.add_agent("Worker1", WorkerAgent()) system.add_agent("Worker2", WorkerAgent()) # Hub Pattern 시나리오 system.delegate_task("task_001", "Manager", "Worker1", {"type": "analyze"}) system.delegate_task("task_001", "Manager", "Worker2", {"type": "process"}) system.communicate("task_001", "Worker1", "Manager", "Analysis complete") system.communicate("task_001", "Worker2", "Manager", "Processing done") # 분석 analysis = system.get_coordination_analysis() print(f"Pattern: {analysis['patterns']['pattern_type']}") # Expected: "hub" print(f"Hub Agent: {analysis['patterns']['hub_agent']}") # Expected: "Manager"

#### Decorator 패턴으로 자동 추적

from functools import wraps def track_agent_interaction( tracker: AgentCoordinationTracker, task_id: str, interaction_type: str = "communication" ): """Agent 상호작용 추적 Decorator""" def decorator(func): @wraps(func) def wrapper(from_agent: str, to_agent: str, *args, **kwargs): success = True result = None try: result = func(from_agent, to_agent, *args, **kwargs) except Exception as e: success = False raise finally: # ✅ Interaction 자동 추적 tracker.track_interaction( task_id=task_id, from_agent=from_agent, to_agent=to_agent, interaction_type=interaction_type, success=success, context={"result": str(result)[:100] if result else None} ) return result return wrapper return decorator # 사용 예제 tracker = AgentCoordinationTracker() @track_agent_interaction(tracker, "task_001", "delegation") def assign_task(from_agent: str, to_agent: str, task_data): # 작업 할당 로직 return agents[to_agent].execute(task_data) @track_agent_interaction(tracker, "task_001", "communication") def send_message(from_agent: str, to_agent: str, message: str): # 메시지 전송 로직 return agents[to_agent].receive(message) # 실행 (자동으로 추적됨) assign_task("Manager", "Worker", {"type": "analyze"}) send_message("Worker", "Manager", "Task complete") # 분석 score = tracker.calculate_coordination_score() 

### 방법 4: 프로덕션 환경 모니터링 📊

프로덕션에서는 모든 Agent 상호작용을 추적하고 패턴을 분석합니다.

from agent_evaluator import AgentCoordinationTracker import logging from datetime import datetime, timedelta class ProductionCoordinationMonitor: def __init__(self, sample_rate=0.1): self.tracker = AgentCoordinationTracker() self.sample_rate = sample_rate # 10% 샘플링 self.logger = logging.getLogger(__name__) self.alert_thresholds = { "coordination_score": 6.0, # < 6.0: Warning "success_rate": 85, # < 85%: Warning "min_agents": 2 # < 2: Not multi-agent } def track_interaction(self, task_id, from_agent, to_agent, interaction_type, success, context=None): """상호작용 추적 및 샘플링 분석""" import random # Interaction 기록 self.tracker.track_interaction( task_id=task_id, from_agent=from_agent, to_agent=to_agent, interaction_type=interaction_type, success=success, context=context ) # 샘플링된 경우만 상세 분석 if random.random() < self.sample_rate: self._analyze_and_alert(task_id) def _analyze_and_alert(self, task_id: str): """Coordination 분석 및 경고""" score_data = self.tracker.calculate_coordination_score(task_id) patterns = self.tracker.get_interaction_patterns() alerts = [] # Coordination Score 체크 if score_data["score"] < self.alert_thresholds["coordination_score"]: alerts.append( f"🟡 Low coordination score: {score_data['score']}/10" ) # Success Rate 체크 if score_data["success_rate"] < self.alert_thresholds["success_rate"]: alerts.append( f"🔴 Low interaction success rate: {score_data['success_rate']}%" ) # Agent Diversity 체크 if score_data["unique_agents"] < self.alert_thresholds["min_agents"]: alerts.append( f"⚠️ Insufficient agent diversity: {score_data['unique_agents']} agents" ) # Pattern 특정 경고 if patterns["pattern_type"] == "hub": # Hub Pattern: Hub Agent 과부하 체크 hub_agent = patterns["hub_agent"] hub_interactions = patterns["agent_roles"][hub_agent]["total_interactions"] hub_ratio = hub_interactions / patterns["total_interactions"] * 100 if hub_ratio > 70: alerts.append( f"🐢 Hub agent '{hub_agent}' overload: {hub_ratio:.0f}% of interactions" ) elif patterns["pattern_type"] == "chain": # Chain Pattern: 병목 가능성 alerts.append( f"⚠️ Chain pattern detected - potential for sequential bottlenecks" ) # 경고 로깅 if alerts: self.logger.warning(f"Task {task_id} coordination issues: {', '.join(alerts)}") def generate_daily_report(self) -> str: """일간 Agent Coordination 리포트""" score = self.tracker.calculate_coordination_score() patterns = self.tracker.get_interaction_patterns() delegation_success = self.tracker.get_delegation_success_rate() report = f""" 📊 Agent Coordination Report {'='*50} Period: Last 24 hours (Sampled {self.sample_rate*100:.0f}%) Coordination Metrics: \- Coordination Score: {score['score']}/10 \- Success Rate: {score['success_rate']}% \- Delegation Success: {delegation_success:.1f}% \- Total Interactions: {score['total_interactions']} \- Unique Agents: {score['unique_agents']} Interaction Pattern: \- Pattern Type: {patterns['pattern_type'].upper()} \- Confidence: {patterns['pattern_confidence']:.1f}% \- Total Agents: {patterns['total_agents']} """ if patterns["pattern_type"] == "hub": report += f"- Hub Agent: {patterns['hub_agent']}\n" report += f""" Agent Roles: """ for agent, info in patterns["agent_roles"].items(): report += f""" {agent}: {info['role'].upper()} \- Sends: {info['sends']}, Receives: {info['receives']} """ report += f""" Top Agent Pairs: """ for pair_info in patterns["top_agent_pairs"][:3]: report += f" {pair_info['pair']}: {pair_info['count']} interactions\n" report += f""" Pattern Characteristics: \- {patterns['pattern_characteristics']['description']} \- Recommendation: {patterns['pattern_characteristics']['recommendation']} """ return report # 프로덕션 사용 monitor = ProductionCoordinationMonitor(sample_rate=0.1) # Multi-Agent 시스템에서 사용 def agent_interaction_handler(task_id, from_agent, to_agent, interaction_type, success): monitor.track_interaction( task_id=task_id, from_agent=from_agent, to_agent=to_agent, interaction_type=interaction_type, success=success ) # 일간 리포트 (Cron으로 스케줄링) def daily_report_job(): report = monitor.generate_daily_report() print(report) # 또는 Slack/Email 전송

#### ⚠️ 프로덕션 데이터 수집 시 주의사항

  * **성능 오버헤드** : 샘플링(10-20%)으로 부담 최소화
  * **Agent 이름 일관성** : 동일 Agent는 항상 같은 이름 사용
  * **Context 크기** : 큰 데이터는 요약하거나 제외
  * **Interaction Type 분류** : 명확한 기준으로 delegation/communication/collaboration 구분
  * **Success 판단** : 예외 발생 = 실패, 정상 응답 = 성공

## 🚨 실전 배포 시 주의사항

### 1\. Interaction Type 명확한 정의

# Interaction Type 분류 기준 # 1. Delegation: 작업 위임 # - Manager → Worker 작업 할당 # - 명확한 작업 요청과 결과 기대 tracker.track_interaction( task_id="task_001", from_agent="Manager", to_agent="Worker", interaction_type="delegation", # ✅ 작업 위임 success=True ) # 2. Communication: 정보 공유 # - 상태 업데이트, 질문/응답, 정보 교환 tracker.track_interaction( task_id="task_001", from_agent="Worker", to_agent="Manager", interaction_type="communication", # ✅ 상태 보고 success=True, context={"message_type": "status_update"} ) # 3. Collaboration: 공동 작업 # - 여러 Agent가 동일 목표를 위해 협력 # - Peer-to-peer 협업 tracker.track_interaction( task_id="task_001", from_agent="Analyst", to_agent="Researcher", interaction_type="collaboration", # ✅ 협업 success=True, context={"shared_goal": "data_analysis"} ) 

### 2\. Pattern별 최적화 전략

def optimize_coordination_pattern(tracker, task_id): """Pattern에 따른 최적화 제안""" patterns = tracker.get_interaction_patterns() pattern_type = patterns["pattern_type"] if pattern_type == "hub": hub_agent = patterns["hub_agent"] hub_load = patterns["agent_roles"][hub_agent]["total_interactions"] total = patterns["total_interactions"] if hub_load / total > 0.7: print(f"⚠️ Hub Pattern Overload Detected!") print(f"Optimization Strategies:") print(f" 1. Add Sub-Hubs to distribute load") print(f" 2. Implement load balancing") print(f" 3. Enable direct peer-to-peer for simple tasks") elif pattern_type == "chain": print(f"⚠️ Chain Pattern Detected!") print(f"Optimization Strategies:") print(f" 1. Identify independent steps for parallelization") print(f" 2. Split into multiple parallel chains") print(f" 3. Add shortcuts for common patterns") elif pattern_type == "mesh": success_rate = patterns["success_rate"] if success_rate < 85: print(f"⚠️ Mesh Pattern with Low Success Rate!") print(f"Optimization Strategies:") print(f" 1. Implement consensus mechanism") print(f" 2. Add conflict resolution protocol") print(f" 3. Establish priority system") 

### 3\. Agent Role 균형 분석

def analyze_agent_role_balance(tracker): """Agent 역할 균형 분석""" patterns = tracker.get_interaction_patterns() agent_roles = patterns["agent_roles"] # 역할별 집계 role_counts = {"producer": 0, "consumer": 0, "coordinator": 0} for agent, info in agent_roles.items(): role = info["role"] if role in role_counts: role_counts[role] += 1 total_agents = len(agent_roles) print(f"Agent Role Distribution:") for role, count in role_counts.items(): percentage = (count / total_agents) * 100 if total_agents > 0 else 0 print(f" {role.capitalize()}: {count} ({percentage:.1f}%)") # 불균형 경고 if role_counts["producer"] > total_agents * 0.7: print(f"⚠️ Too many Producers - need more Consumers") elif role_counts["consumer"] > total_agents * 0.7: print(f"⚠️ Too many Consumers - need more Coordinators") elif role_counts["coordinator"] < 1: print(f"⚠️ No Coordinators - may lack orchestration") else: print(f"✅ Balanced agent role distribution") 

### 4\. 실시간 Coordination 최적화

class RealTimeCoordinationOptimizer: def __init__(self, tracker: AgentCoordinationTracker): self.tracker = tracker self.optimization_history = [] def analyze_and_optimize(self) -> List[str]: """실시간 분석 및 최적화 제안""" score = self.tracker.calculate_coordination_score() patterns = self.tracker.get_interaction_patterns() suggestions = [] # 1. Score 기반 제안 if score["score"] < 6.0: suggestions.append(f"🔴 Low coordination score ({score['score']}/10) - Review agent design") # 2. Success Rate 제안 if score["success_rate"] < 90: suggestions.append(f"⚠️ Interaction success rate {score['success_rate']}% - Add retry logic") # 3. Diversity 제안 if score["unique_agents"] < 3: suggestions.append(f"💡 Only {score['unique_agents']} agents - Consider adding more for complex tasks") # 4. Pattern 특정 제안 if patterns["pattern_type"] == "hub": hub_agent = patterns["hub_agent"] hub_info = patterns["agent_roles"][hub_agent] if hub_info["total_interactions"] > 20: suggestions.append( f"🐢 Hub agent '{hub_agent}' handling {hub_info['total_interactions']} interactions - Consider load balancing" ) # 5. Type Balance 제안 type_counts = score["interaction_types"] if len(type_counts) == 1: suggestions.append( f"⚠️ Only {list(type_counts.keys())[0]} interactions - Diversify interaction types" ) self.optimization_history.append({ "timestamp": datetime.now(), "suggestions": suggestions }) return suggestions # 사용 optimizer = RealTimeCoordinationOptimizer(tracker) suggestions = optimizer.analyze_and_optimize() if suggestions: print("\n🎯 Coordination Optimization Suggestions:") for suggestion in suggestions: print(f" {suggestion}") 

#### 💡 배포 체크리스트

  * ✅ **자동 추적** : CrewAI/AutoGen Integration 사용
  * ✅ **Agent 이름 일관성** : 동일 Agent는 항상 같은 이름
  * ✅ **Interaction Type 명확화** : delegation/communication/collaboration 기준 정의
  * ✅ **샘플링** : 프로덕션에서 10-20% 샘플링
  * ✅ **경고 시스템** : Score, Success Rate, Pattern별 임계값 설정
  * ✅ **주기적 분석** : 일간/주간 패턴 분석 및 최적화
  * ✅ **Role 균형** : Producer/Consumer/Coordinator 비율 모니터링

## ⚙️ 핵심 알고리즘

#### 📊 Coordination Score 계산 흐름

graph TD A[interactions 리스트] --> B{calculate_coordination_score} B --> C1[Success Rate  
성공/전체 × 100] B --> C2[Agent Diversity  
unique_agents / 5] B --> C3[Type Balance  
types / 3] C1 --> D[Score 계산  
50% + 30% + 20%] C2 --> D C3 --> D D --> E[result 반환  
score, success_rate  
unique_agents] style A fill:#667eea,color:#fff style C1 fill:#48bb78,color:#fff style C2 fill:#ed8936,color:#fff style C3 fill:#f59e0b,color:#fff style D fill:#3182ce,color:#fff style E fill:#667eea,color:#fff 

#### 📊 Interaction Pattern 탐지 흐름

graph TD A[interactions 리스트] --> B[Agent 통신 분석] B --> C1[각 Agent의  
send/receive 카운트] B --> C2[Agent Pair  
빈도 계산] C1 --> D{패턴 탐지} C2 --> D D -->|중앙 Agent가  
50% 이상 처리| E1[Hub Pattern] D -->|각 Agent가  
1-2개와만 통신| E2[Chain Pattern] D -->|연결 밀도  
50% 이상| E3[Mesh Pattern] D -->|해당 없음| E4[Unknown Pattern] E1 --> F[Hub Agent 식별] E2 --> G[Chain 순서 분석] E3 --> H[Connection Density 계산] E4 --> I[혼합 패턴 분석] F --> J[Pattern 특성 반환] G --> J H --> J I --> J style A fill:#667eea,color:#fff style D fill:#f59e0b,color:#fff style E1 fill:#fed7d7,color:#742a2a style E2 fill:#bee3f8,color:#2c5282 style E3 fill:#c6f6d5,color:#22543d style J fill:#3182ce,color:#fff 

### track_interaction() 메서드

**위치** : Lines 1521-1542

**목적** : Agent 간 상호작용을 기록

def track_interaction( self, task_id: str, from_agent: str, to_agent: str, interaction_type: str, # delegation, communication, collaboration success: bool, context: Optional[Dict[str, Any]] = None ) -> Dict[str, Any]: """Track agent-to-agent interaction""" interaction = { "task_id": task_id, "from_agent": from_agent, "to_agent": to_agent, "interaction_type": interaction_type, "success": success, "timestamp": datetime.now(), "context": context or {} } self.interactions.append(interaction) return interaction 

### calculate_coordination_score() 메서드

**위치** : Lines 1544-1584

**목적** : 협업 품질 점수 계산 (0-10 scale)

def calculate_coordination_score(self, task_id: Optional[str] = None) -> Dict[str, Any]: """Calculate agent coordination quality score""" # 필터링 (특정 task_id만) interactions = self.interactions if task_id: interactions = [i for i in interactions if i["task_id"] == task_id] if not interactions: return {"score": 0, "total_interactions": 0} # 1. Success Rate (50% 가중치) success_rate = sum(1 for i in interactions if i["success"]) / len(interactions) * 100 # 2. Agent Diversity (30% 가중치) agents = set() for i in interactions: agents.add(i["from_agent"]) agents.add(i["to_agent"]) diversity_score = min(len(agents) / 5, 1.0) * 10 # 5+ agents = ideal # 3. Interaction Type Balance (20% 가중치) type_counts = defaultdict(int) for i in interactions: type_counts[i["interaction_type"]] += 1 balance_score = (len(type_counts) / 3) * 10 # 3 types = ideal # 최종 점수 계산 (0-10 scale) coordination_score = ( success_rate * 0.5 / 10 + # 50% diversity_score * 0.3 + # 30% balance_score * 0.2 # 20% ) return { "score": round(coordination_score, 2), "success_rate": round(success_rate, 2), "total_interactions": len(interactions), "unique_agents": len(agents), "interaction_types": dict(type_counts) } 

### get_interaction_patterns() 메서드

**위치** : Lines 1593-1714

**목적** : Interaction Pattern (Hub/Chain/Mesh) 탐지 및 분석

def get_interaction_patterns(self) -> Dict[str, Any]: """Analyze agent interaction patterns (Hub, Chain, Mesh)""" if not self.interactions: return { "pattern_type": "none", "total_interactions": 0 } # Agent별 통신 횟수 카운트 agent_send_counts = defaultdict(int) # 송신 agent_receive_counts = defaultdict(int) # 수신 agent_pairs = defaultdict(int) # Pair 빈도 for interaction in self.interactions: from_agent = interaction["from_agent"] to_agent = interaction["to_agent"] agent_send_counts[from_agent] += 1 agent_receive_counts[to_agent] += 1 agent_pairs[f"{from_agent}->{to_agent}"] += 1 all_agents = set(list(agent_send_counts.keys()) + list(agent_receive_counts.keys())) total_agents = len(all_agents) total_interactions = len(self.interactions) # 패턴 탐지 pattern_type = "unknown" pattern_confidence = 0.0 # Hub Pattern: 한 Agent가 50% 이상 처리 max_sends = max(agent_send_counts.values()) if agent_send_counts else 0 max_receives = max(agent_receive_counts.values()) if agent_receive_counts else 0 hub_threshold = total_interactions * 0.5 if max_sends >= hub_threshold or max_receives >= hub_threshold: pattern_type = "hub" pattern_confidence = min((max(max_sends, max_receives) / total_interactions) * 100, 100) # Chain Pattern: 각 Agent가 1-2개와만 통신 elif total_agents >= 3: chain_like = sum(1 for agent in all_agents if agent_send_counts.get(agent, 0) <= 2 and agent_receive_counts.get(agent, 0) <= 2) if chain_like / total_agents >= 0.7: pattern_type = "chain" pattern_confidence = (chain_like / total_agents) * 100 # Mesh Pattern: 연결 밀도 50% 이상 unique_pairs = len(agent_pairs) max_possible_pairs = total_agents * (total_agents - 1) if max_possible_pairs > 0: connection_density = unique_pairs / max_possible_pairs if connection_density >= 0.5: pattern_type = "mesh" pattern_confidence = connection_density * 100 # Hub Agent 식별 hub_agent = None if pattern_type == "hub": agent_totals = { agent: agent_send_counts.get(agent, 0) + agent_receive_counts.get(agent, 0) for agent in all_agents } hub_agent = max(agent_totals.items(), key=lambda x: x[1])[0] if agent_totals else None # Agent 역할 분석 agent_roles = {} for agent in all_agents: sends = agent_send_counts.get(agent, 0) receives = agent_receive_counts.get(agent, 0) total = sends + receives if total > 0: send_ratio = sends / total if send_ratio > 0.7: role = "producer" # 주로 송신 elif send_ratio < 0.3: role = "consumer" # 주로 수신 else: role = "coordinator" # 균형 else: role = "inactive" agent_roles[agent] = { "role": role, "sends": sends, "receives": receives, "total_interactions": total } return { "pattern_type": pattern_type, "pattern_confidence": round(pattern_confidence, 2), "hub_agent": hub_agent, "agent_roles": agent_roles, "total_agents": total_agents, "total_interactions": total_interactions } 

#### Agent 역할 분류

  * Producer: 송신 비율 > 70% (주로 작업 분배)
  * Consumer: 수신 비율 > 70% (주로 작업 수행)
  * Coordinator: 송수신 균형 (중재 역할)

## 💻 사용 예제

### 기본 사용법

from agent_evaluator import AgentCoordinationTracker # 트래커 초기화 tracker = AgentCoordinationTracker() # 상호작용 기록 tracker.track_interaction( task_id="task_001", from_agent="ManagerAgent", to_agent="WorkerAgent1", interaction_type="delegation", success=True ) tracker.track_interaction( task_id="task_001", from_agent="ManagerAgent", to_agent="WorkerAgent2", interaction_type="delegation", success=True ) # Coordination Score 계산 score = tracker.calculate_coordination_score() print(f"Coordination Score: {score['score']}/10") print(f"Success Rate: {score['success_rate']}%") # Interaction Pattern 분석 patterns = tracker.get_interaction_patterns() print(f"Pattern Type: {patterns['pattern_type']}") print(f"Confidence: {patterns['pattern_confidence']}%") 

### CrewAI 통합 예제

from crewai import Crew, Agent, Task from agent_evaluator import AgentCoordinationTracker # Agents 정의 researcher = Agent(role="Researcher", goal="Research topics") writer = Agent(role="Writer", goal="Write content") editor = Agent(role="Editor", goal="Edit content") # Tracker 초기화 tracker = AgentCoordinationTracker() # Agent 상호작용 추적 (커스텀 콜백) def on_agent_communication(from_agent, to_agent, success): tracker.track_interaction( task_id="content_creation", from_agent=from_agent, to_agent=to_agent, interaction_type="collaboration", success=success ) # Crew 실행 후 분석 # ... crew.kickoff() ... # 협업 품질 평가 score = tracker.calculate_coordination_score() patterns = tracker.get_interaction_patterns() print(f"Pattern: {patterns['pattern_type']}") if patterns['pattern_type'] == 'hub': print(f"Hub Agent: {patterns['hub_agent']}") for agent, info in patterns['agent_roles'].items(): print(f"{agent}: {info['role']} (sends: {info['sends']}, receives: {info['receives']})") 

## 📈 성능 해석 가이드

Coordination Score | 의미 | 권장 조치  
---|---|---  
8.0 - 10.0 | ✅ 우수 - 효율적인 협업 | 현 상태 유지  
6.0 - 7.9 | ⚠️ 양호 - 개선 가능 | 패턴 최적화 검토  
4.0 - 5.9 | ⚠️ 보통 - 문제 있음 | Agent 역할 재정의  
< 4.0 | ❌ 불량 - 심각한 문제 | 구조 재설계 필요  
  
### 패턴별 최적화 전략

패턴 | 문제 증상 | 최적화 방안  
---|---|---  
Hub | Hub Agent 과부하 | Sub-hub 추가, Load Balancing  
Chain | 순차 병목 | 병렬 Chain, 독립 단계 분리  
Mesh | 충돌 발생 | Consensus 메커니즘, Priority 도입  
  
## 🔗 관련 지표

관련 지표 | 관계 | 문서 링크  
---|---|---  
**Task Completion Rate** | 좋은 Coordination → 높은 TCR | [Task Completion 가이드](<01_TASK_COMPLETION_RATE.html>)  
**Workflow Execution** | Coordination 패턴이 Workflow 효율 결정 | [Workflow 가이드](<13_WORKFLOW_EXECUTION.html>)  
**Latency Metrics** | 비효율적 Coordination이 지연 유발 | [Latency 가이드](<05_LATENCY_METRICS.html>)  
  
## 📋 요약

**Agent Coordination Quality** 는 Multi-Agent 시스템의 협업 효율성을 평가하는 핵심 Layer 2 지표입니다. 

  * **3가지 패턴** : Hub (중앙 집중), Chain (순차 처리), Mesh (완전 연결)
  * **Coordination Score** : Success Rate (50%) + Diversity (30%) + Balance (20%)
  * **Agent 역할** : Producer, Consumer, Coordinator 자동 분류
  * **적용 대상** : CrewAI, AutoGen 등 Multi-Agent Frameworks
  * **목표** : Coordination Score 8.0 이상

  
Layer 2 메트릭으로 Multi-Agent 시스템의 협업 패턴을 분석하며, 복잡한 작업 수행과 확장 가능한 AI 시스템 구축에 필수적입니다. 

## 📚 참고 자료

  * [Agent Evaluator 메인 문서](<../README.html>)
  * [종합 학습 가이드](<../LEARNING_GUIDE.html>)
  * [Wikipedia: Multi-Agent System](<https://en.wikipedia.org/wiki/Multi-agent_system>)
  * [CrewAI Documentation](<https://www.crewai.com/>)

**최종 업데이트** : 2025-12-18 | **버전** : Agent Evaluator v0.5.0

**문서** : Agent Coordination Quality 상세 가이드 (Layer 2 Metric)

© 2025 Agent Evaluator. All rights reserved.
