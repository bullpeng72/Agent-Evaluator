# 🎯 Tool Selection Accuracy

AI Agent Tool Selection Precision and Recall Analysis

Agent Evaluator v0.5.2 - Layer 2 Advanced Metric

## 🎯 개요

**Tool Selection Accuracy (도구 선택 정확도)** 는 AI Agent가 주어진 작업을 수행하기 위해 올바른 도구를 선택했는지 평가하는 Layer 2 Advanced Metric입니다. 

  * **측정 대상** : 예상 도구 vs 실제 선택 도구의 일치율
  * **평가 방식** : Precision, Recall, F1-Score 기반 정량 평가
  * **적용 대상** : AutoGen, LangChain, CrewAI 등 Tool-using Agents
  * **구현 위치** : `agent_evaluator/core/agent_evaluator.py` (Lines 1444-1508)

#### ⚠️ Tool Selection이 중요한 이유

  * **작업 성공률 직결** : 올바른 도구 선택 → 작업 성공
  * **효율성** : 불필요한 도구 호출 감소 → 비용/시간 절감
  * **에러 감소** : 잘못된 도구 사용 → 예상치 못한 에러 발생
  * **사용자 신뢰** : 정확한 도구 사용 → 사용자 만족도 향상

#### 🏗️ 구현 특징

  * **클래스** : `ToolSelectionTracker` (agent_evaluator.py:1444-1508)
  * **평가 메트릭** : Precision, Recall, F1-Score (Information Retrieval 표준)
  * **Layer 2 분류** : Agent 행동 분석 (Framework-specific)
  * **외부 의존성** : 없음 (pandas만 사용)

## 📊 핵심 평가 메트릭

### 3가지 평가 지표

메트릭 | 정의 | 계산식 | 의미  
---|---|---|---  
Precision | 정밀도 - 선택한 도구 중 올바른 비율 | TP / (TP + FP) | 불필요한 도구 호출 감소  
Recall | 재현율 - 필요한 도구 중 선택한 비율 | TP / (TP + FN) | 필수 도구 누락 방지  
F1-Score | 조화 평균 - Precision & Recall의 균형 | 2 × (P × R) / (P + R) | 종합 평가 지표  
  
#### 용어 정의

  * **TP (True Positive)** : 예상 도구 ∩ 실제 선택 도구 (올바르게 선택)
  * **FP (False Positive)** : 실제 선택했지만 불필요한 도구 (과잉 선택)
  * **FN (False Negative)** : 선택하지 않았지만 필요한 도구 (누락)

### 예제로 이해하기

# 시나리오: "오늘 서울 날씨를 알려주고 파일에 저장해줘" # 예상 도구 (Expected Tools) expected_tools = ["get_weather", "write_file"] # Agent가 실제 선택한 도구 (Actual Tools) actual_tools = ["get_weather", "write_file", "search_web"] # 평가 결과 # TP (True Positive) = 2 (get_weather, write_file - 올바르게 선택) # FP (False Positive) = 1 (search_web - 불필요하게 선택) # FN (False Negative) = 0 (누락된 도구 없음) # 계산 Precision = 2 / (2 + 1) = 66.67% # 선택한 3개 중 2개만 필요 Recall = 2 / (2 + 0) = 100% # 필요한 2개를 모두 선택 F1-Score = 2 × (0.667 × 1.0) / (0.667 + 1.0) = 80.00% 

## ⚙️ 핵심 알고리즘

#### 📊 Tool Selection 평가 흐름

graph TD A[expected_tools, actual_tools] --> B{evaluate_selection} B --> C1[Set 변환  
expected_set, actual_set] C1 --> D1[TP 계산  
expected ∩ actual] C1 --> D2[FP 계산  
actual - expected] C1 --> D3[FN 계산  
expected - actual] D1 --> E1[Precision  
TP / actual_set] D1 --> E2[Recall  
TP / expected_set] E1 --> F{Precision + Recall > 0?} E2 --> F F -->|Yes| G[F1-Score  
2 × P × R / P + R] F -->|No| H[F1-Score = 0] G --> I[result 반환] H --> I style A fill:#667eea,color:#fff style C1 fill:#48bb78,color:#fff style D1 fill:#38a169,color:#fff style D2 fill:#ed8936,color:#fff style D3 fill:#e53e3e,color:#fff style G fill:#3182ce,color:#fff style I fill:#667eea,color:#fff 

### evaluate_selection() 메서드

**위치** : Lines 1450-1490

**목적** : 예상 도구와 실제 선택 도구를 비교하여 Precision, Recall, F1 계산

def evaluate_selection( self, task_id: str, expected_tools: List[str], actual_tools: List[str] ) -> Dict[str, Any]: """Evaluate if correct tools were selected""" # 예외 처리: expected_tools가 없으면 100% 정확도 if not expected_tools: return { "task_id": task_id, "accuracy": 100.0, "note": "No expected tools defined" } # Set 변환 (중복 제거 + 빠른 집합 연산) expected_set = set(expected_tools) actual_set = set(actual_tools) # TP, FP, FN 계산 true_positives = len(expected_set & actual_set) # 교집합 false_positives = len(actual_set - expected_set) # actual만 있는 것 false_negatives = len(expected_set - actual_set) # expected만 있는 것 # Precision, Recall 계산 (Zero Division 방지) precision = true_positives / len(actual_set) if actual_set else 0 recall = true_positives / len(expected_set) if expected_set else 0 # F1-Score 계산 f1_score = (2 * precision * recall) / (precision + recall) \ if (precision + recall) > 0 else 0 result = { "task_id": task_id, "expected_tools": expected_tools, "actual_tools": actual_tools, "true_positives": true_positives, "false_positives": false_positives, "false_negatives": false_negatives, "precision": round(precision * 100, 2), "recall": round(recall * 100, 2), "f1_score": round(f1_score * 100, 2), "accuracy": round(f1_score * 100, 2) # F1을 accuracy로 사용 } self.selections.append(result) return result 

### get_accuracy_stats() 메서드

**위치** : Lines 1492-1508

**목적** : 여러 평가 결과를 집계하여 평균 통계 제공

def get_accuracy_stats(self) -> Dict[str, Any]: """Get tool selection accuracy statistics""" if not self.selections: return {} df = pd.DataFrame(self.selections) return { "total_evaluations": len(self.selections), "avg_accuracy": round(df["accuracy"].mean(), 2), "avg_precision": round(df["precision"].mean(), 2), "avg_recall": round(df["recall"].mean(), 2), "avg_f1_score": round(df["f1_score"].mean(), 2), "total_true_positives": int(df["true_positives"].sum()), "total_false_positives": int(df["false_positives"].sum()), "total_false_negatives": int(df["false_negatives"].sum()) } 

#### 통계 항목 설명

  * **total_evaluations** : 평가 횟수
  * **avg_accuracy** : 평균 F1-Score (종합 정확도)
  * **avg_precision** : 평균 정밀도
  * **avg_recall** : 평균 재현율
  * **total_true_positives** : 전체 올바른 선택 수
  * **total_false_positives** : 전체 과잉 선택 수
  * **total_false_negatives** : 전체 누락 수

## 🔍 데이터 수집 방법 (실전 가이드)

#### ⚡ Tool Selection 평가의 핵심: 데이터 수집

Tool Selection Accuracy를 측정하려면 **2가지 데이터** 가 필요합니다:

  * **actual_tools** : Agent가 실제로 호출한 도구 목록 (자동 수집 가능)
  * **expected_tools** : 작업에 필요한 정답 도구 목록 (수동 정의 필요)

### 1\. 프레임워크별 actual_tools 자동 수집

#### LangChain Agent 통합

from agent_evaluator.integrations import LangChainEvaluator from langchain.agents import AgentExecutor, create_react_agent # LangChain Agent 생성 agent = create_react_agent(llm, tools, prompt) agent_executor = AgentExecutor(agent=agent, tools=tools) # Evaluator로 래핑 (자동으로 tool calls 추적) evaluator = LangChainEvaluator( agent_executor, enable_layer2=True # Tool Selection 자동 추적 ) # 실행 시 expected_tools 지정 result = evaluator.run( query="오늘 서울 날씨를 알려주고 파일에 저장해줘", ground_truth="서울: 맑음, 15도", expected_tools=["get_weather", "write_file"] # ✅ 정답 도구 정의 ) # actual_tools는 자동으로 수집됨 report = evaluator.generate_report() print(report.agentic_metrics["tool_selection"]) 

#### AutoGen Agent 통합

from agent_evaluator.integrations import AutoGenEvaluator from autogen import AssistantAgent, UserProxyAgent # AutoGen Agent 생성 assistant = AssistantAgent( name="assistant", llm_config={"model": "gpt-4"}, system_message="You are a helpful assistant." ) # Evaluator로 래핑 evaluator = AutoGenEvaluator( assistant, enable_layer2=True ) # evaluator.agent를 일반 agent처럼 사용 user_proxy.initiate_chat( evaluator.agent, message="Search for AI trends and summarize" ) # Tool calls는 자동으로 추적됨 report = evaluator.generate_report() 

#### CrewAI Agent 통합

from agent_evaluator.integrations import CrewAIEvaluator from crewai import Crew, Agent, Task # CrewAI Crew 생성 crew = Crew( agents=[researcher, writer], tasks=[research_task, writing_task], process=Process.sequential ) # Evaluator로 래핑 evaluator = CrewAIEvaluator( crew, enable_layer2=True ) # 평가와 함께 실행 result = evaluator.kickoff( inputs={"topic": "AI trends"}, ground_truth="Expected output...", expected_tools=["search", "analysis", "write"] ) # Tool Selection 자동 평가 report = evaluator.generate_report() 

#### 수동 Tool Calls 추출 (Helper Functions)

from agent_evaluator import ( extract_tool_calls_from_langchain, extract_tool_calls_from_openai_functions ) # LangChain intermediate_steps에서 추출 langchain_result = agent_executor.invoke({"input": query}) tool_calls = extract_tool_calls_from_langchain(langchain_result) # Returns: [{"tool": "tool_name", "input": {...}, "output": "..."}] actual_tools = [call["tool"] for call in tool_calls] # OpenAI Function Calling 응답에서 추출 openai_response = openai.chat.completions.create( model="gpt-4", messages=messages, tools=tools ) tool_calls = extract_tool_calls_from_openai_functions(openai_response) actual_tools = [call["tool"] for call in tool_calls] 

### 2\. expected_tools 정의 전략

#### ⚠️ Ground Truth 정의의 중요성

**expected_tools** 는 자동 수집이 불가능하며, 도메인 전문가가 수동으로 정의해야 합니다.

#### 전략 1: 작업별 Expected Tools 매핑

# 작업 유형별 필수 도구 정의 TASK_TOOL_MAPPING = { "weather_query": ["get_weather"], "weather_with_save": ["get_weather", "write_file"], "web_search": ["search_web"], "data_analysis": ["read_csv", "calculate", "visualize"], "email_send": ["read_contacts", "send_email"] } # 작업 분류 → Expected Tools 자동 매핑 def classify_task(query: str) -> str: if "날씨" in query and "저장" in query: return "weather_with_save" elif "날씨" in query: return "weather_query" elif "검색" in query: return "web_search" return "unknown" # 사용 예제 query = "오늘 서울 날씨를 알려주고 파일에 저장해줘" task_type = classify_task(query) expected_tools = TASK_TOOL_MAPPING.get(task_type, []) 

#### 전략 2: Test Case Dataset 구축

# test_cases.json test_cases = [ { "task_id": "TC001", "query": "오늘 서울 날씨 알려줘", "expected_tools": ["get_weather"], "ground_truth": "서울: 맑음, 15도" }, { "task_id": "TC002", "query": "AI 트렌드 검색해서 요약해줘", "expected_tools": ["search_web", "summarize"], "ground_truth": "Expected summary..." }, { "task_id": "TC003", "query": "sales.csv 읽고 총합 계산해줘", "expected_tools": ["read_csv", "calculate"], "ground_truth": "Total: $12,345" } ] # Batch Evaluation tracker = ToolSelectionTracker() for test_case in test_cases: # Agent 실행 result = agent.run(test_case["query"]) actual_tools = extract_tools_from_result(result) # 평가 tracker.evaluate_selection( task_id=test_case["task_id"], expected_tools=test_case["expected_tools"], actual_tools=actual_tools ) # 전체 통계 stats = tracker.get_accuracy_stats() print(f"Overall F1-Score: {stats['avg_f1_score']}%") 

#### 전략 3: 온라인 학습 (Human-in-the-Loop)

import json # 1. Agent 실행 + Tool Calls 기록 actual_tools = agent.run_and_log_tools(query) # 2. 전문가에게 Expected Tools 입력 요청 print(f"Query: {query}") print(f"Agent used: {actual_tools}") expected_input = input("Expected tools (comma-separated): ") expected_tools = [t.strip() for t in expected_input.split(",")] # 3. 평가 및 저장 result = tracker.evaluate_selection( task_id=f"task_{len(labeled_data)}", expected_tools=expected_tools, actual_tools=actual_tools ) # 4. Labeled Data 축적 labeled_data.append({ "query": query, "expected_tools": expected_tools, "actual_tools": actual_tools, "precision": result["precision"], "recall": result["recall"], "f1_score": result["f1_score"] }) with open("tool_selection_dataset.json", "w") as f: json.dump(labeled_data, f, indent=2) 

### 3\. 프로덕션 통합 예제

from agent_evaluator import PerformanceMonitor from agent_evaluator import ToolSelectionTracker from agent_evaluator.integrations import LangChainEvaluator # 1. 모니터 및 트래커 초기화 monitor = PerformanceMonitor() tool_tracker = monitor.tool_selection_tracker # ✅ 내장 트래커 사용 # 2. LangChain Agent + Evaluator evaluator = LangChainEvaluator( agent_executor, monitor=monitor, enable_layer2=True ) # 3. Expected Tools 매핑 로드 with open("task_tool_mapping.json") as f: task_mapping = json.load(f) # 4. 프로덕션 실행 for request in production_requests: # 작업 분류 task_type = classify_task(request["query"]) expected_tools = task_mapping.get(task_type, []) # Agent 실행 (Tool Selection 자동 추적) result = evaluator.run( query=request["query"], expected_tools=expected_tools, # ✅ Expected Tools 제공 ground_truth=request.get("ground_truth") ) # 실시간 모니터링 if request["task_id"] % 100 == 0: stats = tool_tracker.get_accuracy_stats() print(f"Tool Selection F1: {stats['avg_f1_score']:.1f}%") # 5. 최종 보고서 report = monitor.generate_report() monitor.save_to_file("production_report.json") 

## 💻 사용 예제 (기본)

### 독립 실행 모드

from agent_evaluator import ToolSelectionTracker # 트래커 초기화 tracker = ToolSelectionTracker() # 작업 1: 날씨 조회 및 저장 result1 = tracker.evaluate_selection( task_id="task_001", expected_tools=["get_weather", "write_file"], actual_tools=["get_weather", "write_file"] ) print(result1) # { # "precision": 100.0, # 선택한 2개 모두 필요 # "recall": 100.0, # 필요한 2개 모두 선택 # "f1_score": 100.0, # 완벽한 선택 # "true_positives": 2, # "false_positives": 0, # "false_negatives": 0 # } # 작업 2: 검색 필요 없는데 선택함 result2 = tracker.evaluate_selection( task_id="task_002", expected_tools=["get_weather"], actual_tools=["get_weather", "search_web"] ) print(result2) # { # "precision": 50.0, # 선택한 2개 중 1개만 필요 # "recall": 100.0, # 필요한 1개는 선택 # "f1_score": 66.67, # 과잉 선택으로 점수 하락 # "true_positives": 1, # "false_positives": 1, # "false_negatives": 0 # } # 통계 조회 stats = tracker.get_accuracy_stats() print(stats) # { # "total_evaluations": 2, # "avg_accuracy": 83.34, # "avg_precision": 75.0, # "avg_recall": 100.0 # }

### 다양한 시나리오

from agent_evaluator import ToolSelectionTracker tracker = ToolSelectionTracker() # 시나리오 1: 완벽한 선택 tracker.evaluate_selection( task_id="perfect", expected_tools=["A", "B"], actual_tools=["A", "B"] ) # Precision: 100%, Recall: 100%, F1: 100% # 시나리오 2: 과잉 선택 (FP 발생) tracker.evaluate_selection( task_id="over_selection", expected_tools=["A"], actual_tools=["A", "B", "C"] ) # Precision: 33.33% (1/3), Recall: 100%, F1: 50% # 시나리오 3: 누락 발생 (FN 발생) tracker.evaluate_selection( task_id="missing", expected_tools=["A", "B", "C"], actual_tools=["A"] ) # Precision: 100%, Recall: 33.33% (1/3), F1: 50% # 시나리오 4: 완전 불일치 tracker.evaluate_selection( task_id="mismatch", expected_tools=["A", "B"], actual_tools=["C", "D"] ) # Precision: 0%, Recall: 0%, F1: 0% # 전체 통계 stats = tracker.get_accuracy_stats() print(f"Average F1-Score: {stats['avg_f1_score']}%") 

## 📈 성능 해석 가이드

지표 조합 | 의미 | 문제점 | 개선 방안  
---|---|---|---  
High Precision  
High Recall | ✅ 이상적 - 정확하고 완전한 선택 | 없음 | 현 상태 유지  
Low Precision  
High Recall | ⚠️ 과잉 선택 - 불필요한 도구 많이 호출 | 비용/시간 낭비, 에러 위험 | Tool 필터링 로직 강화  
High Precision  
Low Recall | ⚠️ 누락 발생 - 필요한 도구 선택 안함 | 작업 실패, 불완전한 결과 | Tool 탐색 범위 확대  
Low Precision  
Low Recall | ❌ 심각 - 도구 선택 능력 부족 | 작업 실패율 높음 | Prompt 재설계, 모델 교체  
  
#### ⚠️ 주의사항

  * **Ground Truth 필요** : expected_tools를 정확히 정의해야 함
  * **도구 이름 일치** : 대소문자, 공백 등 정확히 매칭
  * **중복 제거** : Set 변환으로 자동 처리
  * **F1 vs Accuracy** : 이 구현에서는 F1-Score를 accuracy로 사용

## 🚨 실전 배포 시 주의사항

### 1\. 도구 이름 정규화 문제

#### 문제: 프레임워크마다 도구 이름 형식이 다름

  * **LangChain** : `get_weather` (snake_case)
  * **OpenAI Functions** : `getWeather` (camelCase)
  * **CrewAI** : `Get Weather` (Title Case with spaces)

#### 해결 방법: 정규화 함수 적용

def normalize_tool_name(tool_name: str) -> str: """도구 이름을 표준 형식(snake_case)으로 정규화""" # 1. 소문자 변환 tool_name = tool_name.lower() # 2. 공백/하이픈을 언더스코어로 tool_name = tool_name.replace(" ", "_").replace("-", "_") # 3. camelCase → snake_case import re tool_name = re.sub(r'([a-z])([A-Z])', r'\1_\2', tool_name) return tool_name.lower() # 평가 시 자동 정규화 expected_tools_normalized = [normalize_tool_name(t) for t in expected_tools] actual_tools_normalized = [normalize_tool_name(t) for t in actual_tools] result = tracker.evaluate_selection( task_id=task_id, expected_tools=expected_tools_normalized, actual_tools=actual_tools_normalized ) 

### 2\. Expected Tools 불일치 문제

#### 문제: 작업에 따라 여러 정답이 가능한 경우

예: "서울 날씨 알려줘" → `["get_weather"]` 또는 `["search_web", "extract_info"]` 모두 가능

#### 해결 방법: Alternative Tools 지원

def evaluate_with_alternatives( task_id: str, expected_tools_list: List[List[str]], # 여러 정답 가능 actual_tools: List[str], tracker: ToolSelectionTracker ) -> Dict[str, Any]: """여러 정답 중 최고 점수 반환""" best_result = None best_f1 = 0.0 for expected_tools in expected_tools_list: result = tracker.evaluate_selection( task_id=task_id, expected_tools=expected_tools, actual_tools=actual_tools ) if result["f1_score"] > best_f1: best_f1 = result["f1_score"] best_result = result return best_result # 사용 예제 result = evaluate_with_alternatives( task_id="task_001", expected_tools_list=[ ["get_weather"], # 방법 1 ["search_web", "extract_info"] # 방법 2 ], actual_tools=actual_tools, tracker=tracker ) 

### 3\. 프로덕션 모니터링 패턴

#### ✅ 권장 패턴: 샘플링 + 주기적 리뷰

모든 요청에 대해 expected_tools를 정의하는 것은 비현실적입니다. 다음 패턴을 권장합니다:

import random class ProductionToolSelectionMonitor: def __init__(self, sampling_rate: float = 0.05): self.tracker = ToolSelectionTracker() self.sampling_rate = sampling_rate self.pending_review = [] # Expected Tools 미정의 케이스 self.task_tool_mapping = load_mapping("task_tool_mapping.json") def evaluate_request(self, task_id, query, actual_tools): # 1. 작업 분류 시도 task_type = classify_task(query) expected_tools = self.task_tool_mapping.get(task_type) if expected_tools: # Expected Tools가 있으면 즉시 평가 result = self.tracker.evaluate_selection( task_id=task_id, expected_tools=expected_tools, actual_tools=actual_tools ) return result else: # 2. 매핑 없으면 샘플링하여 리뷰 대기열에 추가 if random.random() < self.sampling_rate: self.pending_review.append({ "task_id": task_id, "query": query, "actual_tools": actual_tools, "timestamp": datetime.now() }) return None def export_for_review(self, output_path: str): """주간 리뷰용 데이터 내보내기""" with open(output_path, "w") as f: json.dump(self.pending_review, f, indent=2, default=str) print(f"📊 {len(self.pending_review)} cases exported for review") self.pending_review = [] # 사용 monitor = ProductionToolSelectionMonitor(sampling_rate=0.05) # 5% 샘플링 for request in production_requests: actual_tools = agent.run_and_extract_tools(request["query"]) monitor.evaluate_request( task_id=request["task_id"], query=request["query"], actual_tools=actual_tools ) # 주간 리뷰 내보내기 monitor.export_for_review("weekly_review_2025_w03.json") 

### 4\. 성능 최적화 팁

#### 💡 대규모 프로덕션 환경에서의 최적화

  * **Batch Evaluation** : 100개씩 묶어서 평가 (pandas DataFrame 활용)
  * **캐싱** : 동일 task_type은 expected_tools 캐싱
  * **비동기 처리** : Tool Selection 평가를 별도 스레드에서 처리
  * **집계 간격** : 실시간 대신 1시간마다 통계 계산

import pandas as pd from concurrent.futures import ThreadPoolExecutor def batch_evaluate_tool_selection( evaluations: List[Dict], # [{"task_id": ..., "expected": ..., "actual": ...}] tracker: ToolSelectionTracker ) -> pd.DataFrame: """대량 평가를 병렬 처리""" def evaluate_single(eval_item): return tracker.evaluate_selection( task_id=eval_item["task_id"], expected_tools=eval_item["expected"], actual_tools=eval_item["actual"] ) # 병렬 평가 with ThreadPoolExecutor(max_workers=10) as executor: results = list(executor.map(evaluate_single, evaluations)) return pd.DataFrame(results) # 사용 evaluations = [...] # 수집된 평가 데이터 df_results = batch_evaluate_tool_selection(evaluations, tracker) # 통계 출력 print(df_results[["precision", "recall", "f1_score"]].describe()) 

## 🔗 관련 지표

관련 지표 | 관계 | 문서 링크  
---|---|---  
**Task Completion Rate** | Tool Selection이 높으면 TCR도 향상 | [Task Completion 가이드](<01_TASK_COMPLETION_RATE.html>)  
**Tool Authorization** | 선택된 도구의 권한 검증 | [Tool Authorization 가이드](<10_TOOL_AUTHORIZATION.html>)  
**Latency Metrics** | 불필요한 Tool 호출이 지연 유발 | [Latency 가이드](<05_LATENCY_METRICS.html>)  
**Cost/Token Economy** | 과잉 Tool 선택이 비용 증가 | [Cost 가이드](<06_COST_TOKEN_ECONOMY.html>)  
  
## 📋 요약

**Tool Selection Accuracy** 는 AI Agent의 도구 선택 능력을 평가하는 핵심 Layer 2 지표입니다. 

  * **Precision** : 선택한 도구 중 올바른 비율 (과잉 선택 방지)
  * **Recall** : 필요한 도구 중 선택한 비율 (누락 방지)
  * **F1-Score** : 두 지표의 조화 평균 (종합 평가)
  * **적용 대상** : AutoGen, LangChain, CrewAI 등 Tool-using Agents
  * **목표** : F1-Score 90% 이상

  
Layer 2 메트릭으로 Agent의 의사결정 품질을 측정하며, 프로덕션 AI 시스템의 효율성과 신뢰성 향상에 필수적입니다. 

## 📚 참고 자료

  * [Agent Evaluator 메인 문서](<../README.html>)
  * [종합 학습 가이드](<../LEARNING_GUIDE.html>)
  * [Wikipedia: Precision and Recall](<https://en.wikipedia.org/wiki/Precision_and_recall>)
  * [Wikipedia: F1-Score](<https://en.wikipedia.org/wiki/F-score>)

**최종 업데이트** : 2026-03-17 | **버전** : Agent Evaluator v0.5.2

**문서** : Tool Selection Accuracy 상세 가이드 (Layer 2 Metric)

© 2025 Agent Evaluator. All rights reserved.
