# 💰 Cost/Token Economy

Token Usage and Cost Tracking for AI Agents

Agent Evaluator v0.5.1 - Layer 1 Foundation Metric

## 📊 개요

**Cost/Token Economy** 는 AI 에이전트의 토큰 사용량과 비용을 추적하고 분석하는 Layer 1 기본 메트릭입니다.   
  
LLM API 사용 비용은 프로덕션 AI 시스템 운영의 주요 비용 항목입니다. 이 메트릭은 입력/출력 토큰을 별도 추적하고, 작업 유형별/모델별 비용을 분석하여 비용 최적화와 예산 관리를 지원합니다. 

### ⚠️ 중요성

  * **비용 투명성** : 실시간으로 API 사용 비용을 정확히 파악
  * **예산 관리** : 월간 예상 비용을 산출하여 예산 초과 방지
  * **최적화 기회 식별** : 비효율적인 토큰 사용 패턴 발견
  * **모델 선택** : 비용 대비 성능을 고려한 모델 선택 지원
  * **ROI 계산** : AI 에이전트의 비용 대비 효과 측정

## 📍 구현 위치

**파일:** `agent_evaluator/core/agent_evaluator.py`  
**클래스:** `TokenEconomyTracker`  
**라인:** 1065-1188 (총 124줄) 

### 핵심 메서드

메서드 | 라인 | 기능  
---|---|---  
`__init__(pricing)` | 1068-1074 | 모델의 입력/출력 토큰 가격 설정  
`track_usage()` | 1076-1091 | 각 작업의 토큰 사용량과 비용 기록  
`_calculate_cost()` | 1093-1097 | 입력/출력 토큰 기반 비용 계산  
`get_usage_stats()` | 1099-1128 | 전체 토큰 사용량 및 비용 통계  
`get_usage_by_type()` | 1130-1141 | 작업 유형별 사용량 및 비용 분석  
`get_cost_breakdown_by_model()` | 1143-1188 | 모델별 상세 비용 분석  
  
## 📊 동작 흐름 다이어그램

#### Token Economy 비용 계산 흐름

graph TD A[input_tokens, output_tokens] --> B[_calculate_cost] B --> C[input_cost =   
input_tokens/1000 × price] B --> D[output_cost =   
output_tokens/1000 × price] C --> E[total_cost 반환] D --> E F[usage_log List] --> G{get_usage_stats} G --> H[DataFrame 변환] H --> I1[total_tokens 합산] H --> I2[total_cost 합산] H --> I3[avg/task 계산] H --> I4[token_distribution  
입출력 비율] H --> I5[cost_percentiles  
P50/P90/P95] I1 --> J[통계 dict 반환] I2 --> J I3 --> J I4 --> J I5 --> J style A fill:#667eea,color:#fff style B fill:#48bb78,color:#fff style E fill:#38a169,color:#fff style F fill:#667eea,color:#fff style G fill:#48bb78,color:#fff style J fill:#3182ce,color:#fff 

## 💵 비용 계산

LLM API는 일반적으로 입력 토큰(Input)과 출력 토큰(Output)에 대해 **서로 다른 가격** 을 책정합니다. 출력 토큰이 입력 토큰보다 2-3배 비싼 경우가 많습니다. 

### 비용 계산 공식

총 비용 = 입력 비용 + 출력 비용

Cost = (Input Tokens / 1000) × Input Price + (Output Tokens / 1000) × Output Price 

def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float: """Calculate cost based on token usage""" # 입력 토큰 비용 (1000개당 가격) input_cost = (input_tokens / 1000) * self.pricing["input"] # 출력 토큰 비용 (1000개당 가격) output_cost = (output_tokens / 1000) * self.pricing["output"] return input_cost + output_cost 

### 주요 LLM 모델 가격 (2024년 기준)

모델 | 입력 (per 1M tokens) | 출력 (per 1M tokens) | 출력/입력 비율  
---|---|---|---  
**GPT-4 Turbo** | $10.00 | $30.00 | 3.0x  
**GPT-3.5 Turbo** | $0.50 | $1.50 | 3.0x  
**Claude 3 Opus** | $15.00 | $75.00 | 5.0x  
**Claude 3 Sonnet** | $3.00 | $15.00 | 5.0x  
**Claude 3.5 Sonnet** | $3.00 | $15.00 | 5.0x  
**Claude 3 Haiku** | $0.25 | $1.25 | 5.0x  
**Gemini 1.5 Pro** | $3.50 | $10.50 | 3.0x  
**Llama 3 70B (Groq)** | $0.59 | $0.79 | 1.3x  
  
#### ⚠️ 가격 변동 주의

LLM 모델 가격은 자주 변경됩니다. 최신 가격은 각 제공사의 공식 문서를 확인하세요: 

  * OpenAI: https://openai.com/pricing
  * Anthropic: https://www.anthropic.com/pricing
  * Google: https://cloud.google.com/vertex-ai/pricing

## 📈 사용량 추적

### 토큰 사용량 기록

def track_usage(self, task_id: str, input_tokens: int, output_tokens: int, task_type: str, model: str = "default"): """Track token usage for a task""" total_tokens = input_tokens + output_tokens cost = self._calculate_cost(input_tokens, output_tokens) self.usage_log.append({ "task_id": task_id, "task_type": task_type, "model": model, "input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens, "cost": cost, "timestamp": datetime.now() }) 

### 전체 사용량 통계

def get_usage_stats(self) -> Dict[str, Any]: """Get token usage statistics""" if not self.usage_log: return {} df = pd.DataFrame(self.usage_log) total_input = int(df["input_tokens"].sum()) total_output = int(df["output_tokens"].sum()) total_tokens = int(df["total_tokens"].sum()) return { "total_tasks": len(df), "total_tokens": total_tokens, "total_input_tokens": total_input, "total_output_tokens": total_output, "total_cost": round(df["cost"].sum(), 4), "avg_tokens_per_task": round(df["total_tokens"].mean(), 2), "avg_cost_per_task": round(df["cost"].mean(), 4), "estimated_monthly_cost": round(df["cost"].sum() * 30, 2), "token_distribution": { "input_ratio": round(total_input / total_tokens, 3) if total_tokens > 0 else 0, "output_ratio": round(total_output / total_tokens, 3) if total_tokens > 0 else 0 }, "cost_percentiles": { "p50": round(df["cost"].quantile(0.5), 4), "p90": round(df["cost"].quantile(0.9), 4), "p95": round(df["cost"].quantile(0.95), 4) } } 

### 주요 통계 지표

#### Total Tokens

전체 사용된 토큰 수 (입력 + 출력)

**용도:** 전체 사용량 파악

#### Total Cost

누적 총 비용 (달러)

**용도:** 실제 지출 금액 추적

#### Avg Tokens per Task

작업당 평균 토큰 사용량

**용도:** 효율성 벤치마크

#### Avg Cost per Task

작업당 평균 비용

**용도:** 단위 비용 모니터링

#### Estimated Monthly Cost

현재 사용량 기반 월간 예상 비용

**용도:** 예산 계획

#### Token Distribution

입력/출력 토큰 비율

**용도:** 사용 패턴 분석

#### Cost Percentiles

비용 분포 (P50, P90, P95)

**용도:** 비용 변동성 파악

## 📊 작업 유형별 분석

작업 유형(QA, Code Generation, Summarization 등)에 따라 토큰 사용량과 비용이 크게 다릅니다. `get_usage_by_type()`는 각 작업 유형별 통계를 제공합니다. 

def get_usage_by_type(self) -> Dict[str, Dict[str, float]]: """Get usage breakdown by task type""" if not self.usage_log: return {} df = pd.DataFrame(self.usage_log) # Group by task type and aggregate grouped = df.groupby("task_type").agg({ "total_tokens": ["sum", "mean"], "cost": ["sum", "mean"] }).round(2) return grouped.to_dict() 

### 사용 예시

# 작업 유형별 비용 분석 usage_by_type = tracker.get_usage_by_type() for task_type, stats in usage_by_type.items(): print(f"\nTask Type: {task_type}") print(f" Total Tokens: {stats[('total_tokens', 'sum')]}") print(f" Avg Tokens: {stats[('total_tokens', 'mean')]}") print(f" Total Cost: ${stats[('cost', 'sum')]:.4f}") print(f" Avg Cost: ${stats[('cost', 'mean')]:.4f}") # 출력 예시: # Task Type: qa # Total Tokens: 125000 # Avg Tokens: 833.33 # Total Cost: $0.1875 # Avg Cost: $0.0013 # # Task Type: code_generation # Total Tokens: 450000 # Avg Tokens: 6000.00 # Total Cost: $1.3500 # Avg Cost: $0.0180

### 작업 유형별 비용 특성

작업 유형 | 일반적인 토큰 사용 | 비용 특성 | 최적화 방법  
---|---|---|---  
**QA** | 낮음 (500-2000) | 입력 비중 높음 | 컨텍스트 최소화, 캐싱  
**Code Generation** | 높음 (3000-8000) | 출력 비중 높음 | Few-shot 예시 최적화  
**Summarization** | 중간 (2000-5000) | 입력 매우 높음 | 청크 크기 조정, 스트리밍  
**Reasoning** | 높음 (4000-10000) | 출력 비중 높음 | Chain-of-thought 길이 제한  
**Classification** | 낮음 (200-800) | 출력 매우 낮음 | 배치 처리, 간단한 모델  
  
## 🤖 모델별 비용 분석

여러 LLM 모델을 함께 사용하는 경우, 각 모델의 비용 기여도를 파악하는 것이 중요합니다. `get_cost_breakdown_by_model()`는 모델별 상세 통계를 제공합니다. 

def get_cost_breakdown_by_model(self) -> Dict[str, Dict[str, Any]]: """Get detailed cost breakdown by model""" if not self.usage_log: return {} # Group by model model_data = defaultdict(lambda: { "input_tokens": [], "output_tokens": [], "total_tokens": [], "costs": [], "task_count": 0 }) for entry in self.usage_log: model = entry.get("model", "default") model_data[model]["input_tokens"].append(entry["input_tokens"]) model_data[model]["output_tokens"].append(entry["output_tokens"]) model_data[model]["total_tokens"].append(entry["total_tokens"]) model_data[model]["costs"].append(entry["cost"]) model_data[model]["task_count"] += 1 # Calculate statistics for each model breakdown = {} for model, data in model_data.items(): costs = data["costs"] total_tokens = data["total_tokens"] input_tokens = data["input_tokens"] output_tokens = data["output_tokens"] breakdown[model] = { "total_cost": round(sum(costs), 4), "avg_cost_per_task": round(statistics.mean(costs), 4), "median_cost": round(statistics.median(costs), 4), "min_cost": round(min(costs), 4), "max_cost": round(max(costs), 4), "std_cost": round(statistics.stdev(costs), 4) if len(costs) > 1 else 0.0, "total_tasks": data["task_count"], "total_tokens": sum(total_tokens), "total_input_tokens": sum(input_tokens), "total_output_tokens": sum(output_tokens), "avg_tokens_per_task": round(statistics.mean(total_tokens), 2), "cost_per_1k_tokens": round((sum(costs) / sum(total_tokens) * 1000), 4) if sum(total_tokens) > 0 else 0.0 } return breakdown 

### 사용 예시

# 모델별 비용 분석 model_breakdown = tracker.get_cost_breakdown_by_model() for model, stats in model_breakdown.items(): print(f"\n=== Model: {model} ===") print(f"Total Tasks: {stats['total_tasks']}") print(f"Total Cost: ${stats['total_cost']:.4f}") print(f"Avg Cost/Task: ${stats['avg_cost_per_task']:.4f}") print(f"Total Tokens: {stats['total_tokens']:,}") print(f"Cost per 1K tokens: ${stats['cost_per_1k_tokens']:.4f}") print(f"Input/Output: {stats['total_input_tokens']:,} / {stats['total_output_tokens']:,}") 

## 💻 사용 예시

### 기본 사용법

from agent_evaluator import AgentEvaluator # GPT-4 Turbo 가격 설정 (per 1M tokens) pricing = { "input": 10.00 / 1000, # $10 per 1M = $0.01 per 1K "output": 30.00 / 1000 # $30 per 1M = $0.03 per 1K } # Evaluator 초기화 evaluator = AgentEvaluator(pricing=pricing) # LLM 호출 후 토큰 사용량 기록 response = llm.generate(prompt) evaluator.track_usage( task_id="task_001", input_tokens=response.usage.prompt_tokens, output_tokens=response.usage.completion_tokens, task_type="qa", model="gpt-4-turbo" ) # 통계 조회 stats = evaluator.get_usage_stats() print(f"Total Cost: ${stats['total_cost']:.4f}") print(f"Estimated Monthly: ${stats['estimated_monthly_cost']:.2f}") 

### 다중 모델 추적

# 서로 다른 모델 가격 설정 gpt4_pricing = {"input": 0.01, "output": 0.03} # per 1K tokens gpt35_pricing = {"input": 0.0005, "output": 0.0015} # 작업에 따라 다른 모델 사용 if task_complexity == "high": response = gpt4.generate(prompt) tracker = AgentEvaluator(pricing=gpt4_pricing) model_name = "gpt-4-turbo" else: response = gpt35.generate(prompt) tracker = AgentEvaluator(pricing=gpt35_pricing) model_name = "gpt-3.5-turbo" tracker.track_usage( task_id=task_id, input_tokens=response.usage.prompt_tokens, output_tokens=response.usage.completion_tokens, task_type=task_type, model=model_name ) # 모델별 비용 비교 breakdown = tracker.get_cost_breakdown_by_model() for model, stats in breakdown.items(): print(f"{model}: ${stats['total_cost']:.4f} ({stats['total_tasks']} tasks)") 

### 월간 비용 예측 및 알림

def check_budget_alert(evaluator: AgentEvaluator, monthly_budget: float): """Check if estimated monthly cost exceeds budget""" stats = evaluator.get_usage_stats() estimated_monthly = stats.get("estimated_monthly_cost", 0) if estimated_monthly > monthly_budget: print(f"⚠️ WARNING: Estimated monthly cost ${estimated_monthly:.2f} exceeds budget ${monthly_budget:.2f}") print(f" Current usage: ${stats['total_cost']:.4f}") print(f" Avg cost per task: ${stats['avg_cost_per_task']:.4f}") # Send alert (email, Slack, etc.) send_alert(f"Budget Alert: ${estimated_monthly:.2f} / ${monthly_budget:.2f}") return True return False # 사용 check_budget_alert(evaluator, monthly_budget=500.0) 

## 🤖 평가 데이터 자동 처리 방안

**실전 적용 시 핵심 과제:**  
Cost/Token Economy 평가는 **Token 사용량과 비용 데이터 수집** 이 필수입니다. 실제 프로젝트에서는 여러 모델, 여러 작업 유형, 다양한 API 호출을 자동으로 추적하고 집계해야 합니다.   
  
이 섹션에서는 **Token 사용량 자동 수집, 비용 자동 계산, 실시간 모니터링** 을 위한 5단계 자동화 전략을 제공합니다. 

### 📊 자동화 전략 개요

Level | 방법 | 자동화 범위 | 성능 | 난이도  
---|---|---|---|---  
**1** | API 응답 자동 파싱 | Token 사용량 자동 추출 | ⚡⚡⚡⚡⚡ | ⭐  
**2** | Decorator 기반 자동 추적 | 함수 레벨 비용 추적 | ⚡⚡⚡⚡ | ⭐⭐  
**3** | Context Manager 기반 | 작업 단위 비용 추적 | ⚡⚡⚡⚡ | ⭐⭐  
**4** | 실시간 대시보드 | 실시간 모니터링 + 알림 | ⚡⚡⚡ | ⭐⭐⭐  
**5** | 통합 자동화 시스템 | 전체 파이프라인 자동화 | ⚡⚡⚡⚡⚡ | ⭐⭐⭐⭐  
  
### Level 1: API 응답 자동 파싱

가장 기본적인 방법으로, LLM API 응답에서 Token 사용량을 자동으로 추출합니다.

from agent_evaluator import PerformanceMonitor import openai class AutoTokenTracker: """API 응답에서 Token 사용량 자동 추출""" def __init__(self, monitor: PerformanceMonitor): self.monitor = monitor self.task_counter = 0 def call_llm_and_track(self, prompt: str, model: str = "gpt-4"): """LLM 호출 + 자동 Token 추적""" self.task_counter += 1 task_id = f"task_{self.task_counter}" # LLM 호출 response = openai.ChatCompletion.create( model=model, messages=[{"role": "user", "content": prompt}] ) # ✅ Token 사용량 자동 추출 usage = response["usage"] input_tokens = usage["prompt_tokens"] output_tokens = usage["completion_tokens"] # ✅ 자동 기록 self.monitor.record_task( task_id=task_id, model_name=model, input_tokens=input_tokens, output_tokens=output_tokens, success=True ) return response["choices"][0]["message"]["content"] # 사용 예시 monitor = PerformanceMonitor() tracker = AutoTokenTracker(monitor) # 자동으로 Token 추적됨 answer1 = tracker.call_llm_and_track("대한민국의 수도는?", model="gpt-4") answer2 = tracker.call_llm_and_track("프랑스의 수도는?", model="gpt-3.5-turbo") answer3 = tracker.call_llm_and_track("일본의 수도는?", model="gpt-4") # 📊 비용 통계 자동 집계 cost_stats = monitor.cost_evaluator.get_cost_stats() print(f"총 비용: ${cost_stats['total_cost']:.4f}") print(f"평균 작업당 비용: ${cost_stats['average_cost_per_task']:.4f}") 

**⚡ 장점:**

  * 구현 간단, 즉시 적용 가능
  * 모든 API 호출에서 Token 자동 추출
  * 실시간 비용 계산

**⚠️ 한계:**

  * 각 LLM 호출마다 명시적으로 메서드 호출 필요
  * 기존 코드 수정 필요

### Level 2: Decorator 기반 자동 추적

Decorator를 사용하여 기존 함수에 자동 Token 추적 기능을 주입합니다.

from functools import wraps import time def track_cost(monitor: PerformanceMonitor, task_type: str = "default"): """비용 추적 Decorator""" def decorator(func): @wraps(func) def wrapper(*args, **kwargs): task_id = f"{task_type}_{int(time.time() * 1000)}" # 원본 함수 실행 result = func(*args, **kwargs) # ✅ 결과에서 Token 정보 자동 추출 if isinstance(result, dict) and "usage" in result: usage = result["usage"] monitor.record_task( task_id=task_id, input_tokens=usage.get("prompt_tokens", 0), output_tokens=usage.get("completion_tokens", 0), model_name=kwargs.get("model", "gpt-4"), task_type=task_type, success=True ) return result return wrapper return decorator # 사용 예시 monitor = PerformanceMonitor() # ✅ Decorator로 자동 추적 @track_cost(monitor, task_type="qa") def ask_question(question: str, model: str = "gpt-4"): response = openai.ChatCompletion.create( model=model, messages=[{"role": "user", "content": question}] ) return response # usage 정보 포함된 전체 응답 반환 @track_cost(monitor, task_type="summarization") def summarize_text(text: str, model: str = "gpt-3.5-turbo"): response = openai.ChatCompletion.create( model=model, messages=[{"role": "user", "content": f"요약: {text}"}] ) return response # 자동 추적됨 (코드 수정 없이) ask_question("서울의 인구는?", model="gpt-4") ask_question("도쿄의 인구는?", model="gpt-4") summarize_text("긴 텍스트...", model="gpt-3.5-turbo") # 📊 작업 유형별 비용 분석 cost_by_type = monitor.cost_evaluator.get_cost_by_task_type() for task_type, cost in cost_by_type.items(): print(f"{task_type}: ${cost:.4f}") 

**💡 Pro Tip:** Decorator 패턴은 기존 코드를 최소한으로 수정하면서 자동 추적을 적용할 수 있는 가장 우아한 방법입니다. 

### Level 3: Context Manager 기반 자동 추적

Context Manager를 사용하여 작업 단위로 비용을 추적합니다.

class CostTrackingContext: """작업 단위 비용 추적 Context Manager""" def __init__(self, monitor: PerformanceMonitor, task_id: str, task_type: str = "default"): self.monitor = monitor self.task_id = task_id self.task_type = task_type self.total_input_tokens = 0 self.total_output_tokens = 0 self.model_name = None def __enter__(self): print(f"🟢 비용 추적 시작: {self.task_id}") return self def __exit__(self, exc_type, exc_val, exc_tb): # ✅ Context 종료 시 자동 기록 if self.total_input_tokens > 0 or self.total_output_tokens > 0: self.monitor.record_task( task_id=self.task_id, input_tokens=self.total_input_tokens, output_tokens=self.total_output_tokens, model_name=self.model_name or "gpt-4", task_type=self.task_type, success=exc_type is None ) print(f"🔴 비용 추적 완료: {self.task_id} (Input: {self.total_input_tokens}, Output: {self.total_output_tokens})") return False def add_usage(self, response, model: str = "gpt-4"): """API 응답에서 Token 사용량 누적""" if "usage" in response: usage = response["usage"] self.total_input_tokens += usage.get("prompt_tokens", 0) self.total_output_tokens += usage.get("completion_tokens", 0) self.model_name = model # 사용 예시: 복잡한 Multi-step 작업 monitor = PerformanceMonitor() with CostTrackingContext(monitor, "multi_step_task_001", task_type="research") as ctx: # Step 1: 검색 쿼리 생성 response1 = openai.ChatCompletion.create( model="gpt-4", messages=[{"role": "user", "content": "검색 쿼리 생성"}] ) ctx.add_usage(response1, model="gpt-4") # Step 2: 정보 수집 response2 = openai.ChatCompletion.create( model="gpt-4", messages=[{"role": "user", "content": "정보 수집"}] ) ctx.add_usage(response2, model="gpt-4") # Step 3: 요약 생성 response3 = openai.ChatCompletion.create( model="gpt-3.5-turbo", messages=[{"role": "user", "content": "요약 생성"}] ) ctx.add_usage(response3, model="gpt-3.5-turbo") # ✅ Context 종료 시 전체 작업의 Token 사용량 자동 기록됨 # 📊 통계 확인 cost_stats = monitor.cost_evaluator.get_cost_stats() print(f"총 비용: ${cost_stats['total_cost']:.4f}") 

**✅ 장점:**

  * Multi-step 작업의 전체 비용 추적 용이
  * 자동 집계 (여러 API 호출 통합)
  * 예외 발생 시에도 안전하게 기록

### Level 4: 실시간 대시보드 + 예산 알림

실시간으로 비용을 모니터링하고, 예산 초과 시 자동 알림을 발송합니다.

import threading import time from datetime import datetime class RealTimeCostMonitor: """실시간 비용 모니터링 + 예산 알림""" def __init__(self, monitor: PerformanceMonitor, daily_budget: float = 50.0, monthly_budget: float = 1000.0): self.monitor = monitor self.daily_budget = daily_budget self.monthly_budget = monthly_budget self.daily_cost = 0.0 self.monthly_cost = 0.0 self.alert_sent = False self.monitoring = False self.monitor_thread = None def start_monitoring(self, interval: int = 60): """실시간 모니터링 시작 (interval: 초)""" self.monitoring = True self.monitor_thread = threading.Thread( target=self._monitor_loop, args=(interval,), daemon=True ) self.monitor_thread.start() print(f"🟢 실시간 비용 모니터링 시작 (예산: Daily ${self.daily_budget}, Monthly ${self.monthly_budget})") def stop_monitoring(self): """모니터링 중지""" self.monitoring = False if self.monitor_thread: self.monitor_thread.join(timeout=5) print("🔴 실시간 비용 모니터링 중지") def _monitor_loop(self, interval: int): """모니터링 루프""" while self.monitoring: self._check_budget() time.sleep(interval) def _check_budget(self): """예산 확인 및 알림""" cost_stats = self.monitor.cost_evaluator.get_cost_stats() current_total = cost_stats.get("total_cost", 0.0) # 예산 초과 체크 if current_total >= self.daily_budget and not self.alert_sent: self._send_alert("DAILY", current_total, self.daily_budget) self.alert_sent = True if current_total >= self.monthly_budget: self._send_alert("MONTHLY", current_total, self.monthly_budget) self.monitoring = False # 월 예산 초과 시 중지 # 실시간 로그 print(f"[{datetime.now().strftime('%H:%M:%S')}] 💰 현재 비용: ${current_total:.4f} / ${self.daily_budget:.2f} (일일)") def _send_alert(self, alert_type: str, current: float, budget: float): """알림 발송""" print(f"🚨 {alert_type} 예산 초과 알림!") print(f" 현재 비용: ${current:.4f}") print(f" 예산: ${budget:.4f}") print(f" 초과액: ${(current - budget):.4f}") # 실제로는 이메일, Slack, SMS 등으로 알림 발송 # send_email(...) # send_slack_message(...) def get_dashboard_data(self): """대시보드 데이터 반환""" cost_stats = self.monitor.cost_evaluator.get_cost_stats() cost_by_model = self.monitor.cost_evaluator.get_cost_by_model() cost_by_type = self.monitor.cost_evaluator.get_cost_by_task_type() return { "summary": cost_stats, "by_model": cost_by_model, "by_type": cost_by_type, "budget_status": { "daily_budget": self.daily_budget, "monthly_budget": self.monthly_budget, "current_cost": cost_stats.get("total_cost", 0.0), "daily_remaining": max(0, self.daily_budget - cost_stats.get("total_cost", 0.0)), "monthly_remaining": max(0, self.monthly_budget - cost_stats.get("total_cost", 0.0)) } } # 사용 예시 monitor = PerformanceMonitor() real_time_monitor = RealTimeCostMonitor( monitor, daily_budget=10.0, monthly_budget=200.0 ) # 🟢 실시간 모니터링 시작 (60초마다 체크) real_time_monitor.start_monitoring(interval=60) # 작업 실행 (자동으로 모니터링됨) tracker = AutoTokenTracker(monitor) for i in range(100): tracker.call_llm_and_track(f"질문 {i+1}", model="gpt-4") time.sleep(5) # 예시를 위한 대기 # 📊 대시보드 데이터 가져오기 dashboard_data = real_time_monitor.get_dashboard_data() print("📊 실시간 대시보드:") print(f" 총 비용: ${dashboard_data['summary']['total_cost']:.4f}") print(f" 일일 잔여 예산: ${dashboard_data['budget_status']['daily_remaining']:.4f}") # 🔴 모니터링 중지 real_time_monitor.stop_monitoring() 

**💡 Production Tip:** 실제 프로덕션 환경에서는 Prometheus, Grafana, Datadog 등의 모니터링 도구와 연동하여 더 강력한 대시보드를 구축하세요. 

### Level 5: 통합 자동화 시스템 (Production-Ready)

모든 레벨을 통합한 완전 자동화 시스템입니다.

class CostAutomationSystem: """통합 비용 자동화 시스템""" def __init__(self, daily_budget: float = 50.0, monthly_budget: float = 1000.0, alert_email: str = None, enable_realtime: bool = True): self.monitor = PerformanceMonitor() self.tracker = AutoTokenTracker(self.monitor) self.real_time_monitor = RealTimeCostMonitor( self.monitor, daily_budget=daily_budget, monthly_budget=monthly_budget ) self.alert_email = alert_email self.enable_realtime = enable_realtime if self.enable_realtime: self.real_time_monitor.start_monitoring(interval=60) def track_llm_call(self, prompt: str, model: str = "gpt-4", task_type: str = "default"): """LLM 호출 + 자동 추적 + 실시간 모니터링""" return self.tracker.call_llm_and_track(prompt, model) def track_context(self, task_id: str, task_type: str = "default"): """Context Manager 반환""" return CostTrackingContext(self.monitor, task_id, task_type) def get_cost_report(self): """비용 보고서 생성""" cost_stats = self.monitor.cost_evaluator.get_cost_stats() cost_by_model = self.monitor.cost_evaluator.get_cost_by_model() cost_by_type = self.monitor.cost_evaluator.get_cost_by_task_type() report = { "summary": { "total_cost": cost_stats.get("total_cost", 0.0), "total_tasks": cost_stats.get("total_tasks", 0), "average_cost_per_task": cost_stats.get("average_cost_per_task", 0.0), "total_input_tokens": cost_stats.get("total_input_tokens", 0), "total_output_tokens": cost_stats.get("total_output_tokens", 0) }, "by_model": cost_by_model, "by_type": cost_by_type, "budget_status": self.real_time_monitor.get_dashboard_data()["budget_status"] } return report def export_to_dashboard(self, output_path: str = "cost_report.json"): """대시보드용 JSON 파일 생성""" import json report = self.get_cost_report() with open(output_path, "w", encoding="utf-8") as f: json.dump(report, f, indent=2, ensure_ascii=False) print(f"📊 비용 보고서 저장: {output_path}") def shutdown(self): """시스템 종료""" if self.enable_realtime: self.real_time_monitor.stop_monitoring() print("🔴 비용 자동화 시스템 종료") # ============================================ # 완전 자동화 실사용 예시 # ============================================ from agent_evaluator import PerformanceMonitor # 🟢 시스템 초기화 cost_system = CostAutomationSystem( daily_budget=20.0, monthly_budget=500.0, alert_email="admin@example.com", enable_realtime=True ) try: # ✅ 간단한 LLM 호출 (자동 추적) answer1 = cost_system.track_llm_call("파이썬이란?", model="gpt-4") answer2 = cost_system.track_llm_call("자바란?", model="gpt-3.5-turbo") # ✅ 복잡한 Multi-step 작업 (Context Manager) with cost_system.track_context("research_task_001", task_type="research") as ctx: # 여러 API 호출 response1 = openai.ChatCompletion.create( model="gpt-4", messages=[{"role": "user", "content": "1단계"}] ) ctx.add_usage(response1, model="gpt-4") response2 = openai.ChatCompletion.create( model="gpt-4", messages=[{"role": "user", "content": "2단계"}] ) ctx.add_usage(response2, model="gpt-4") # 작업 실행 중 실시간 모니터링 자동 진행... time.sleep(120) # 2분 대기 (모니터링 간격) # 📊 최종 보고서 생성 final_report = cost_system.get_cost_report() print("\n📊 최종 비용 보고서:") print(f" 총 비용: ${final_report['summary']['total_cost']:.4f}") print(f" 총 작업 수: {final_report['summary']['total_tasks']}") print(f" 평균 작업당 비용: ${final_report['summary']['average_cost_per_task']:.4f}") print(f" 일일 잔여 예산: ${final_report['budget_status']['daily_remaining']:.4f}") print("\n📊 모델별 비용:") for model, cost in final_report["by_model"].items(): print(f" {model}: ${cost:.4f}") print("\n📊 작업 유형별 비용:") for task_type, cost in final_report["by_type"].items(): print(f" {task_type}: ${cost:.4f}") # 📁 대시보드 JSON 생성 cost_system.export_to_dashboard("cost_dashboard.json") finally: # 🔴 시스템 종료 cost_system.shutdown() 

**🎯 완전 자동화 달성!**  
Level 5 시스템을 사용하면: 

  * ✅ 모든 LLM 호출의 Token 사용량 자동 추적
  * ✅ 실시간 비용 모니터링 및 예산 초과 알림
  * ✅ 작업 유형별, 모델별 비용 분석
  * ✅ 대시보드용 JSON 자동 생성
  * ✅ Zero Configuration (단 3줄로 시작)

### 🎯 자동화 전략 선택 가이드

사용 사례 | 추천 Level | 이유  
---|---|---  
프로토타입 개발 | **Level 1** | 빠른 구현, 최소 코드 변경  
기존 코드에 추가 | **Level 2** | Decorator로 기존 함수에 비침투적 적용  
복잡한 Multi-step 작업 | **Level 3** | 여러 API 호출 통합 추적  
운영 환경 모니터링 | **Level 4** | 실시간 예산 관리 필요  
Production 환경 | **Level 5** | 완전 자동화 + 대시보드 통합  
  
### ⚠️ 자동화 시 주의사항

  1. **API 응답 형식 변경** : OpenAI API 응답 구조가 변경될 수 있으므로, 에러 핸들링 필수
  2. **Thread Safety** : 멀티스레드 환경에서는 Lock 사용 고려
  3. **메모리 관리** : 장기 실행 시 메모리 누수 방지 (주기적 로그 파일 저장)
  4. **예산 초과 방지** : Hard Limit 설정 및 자동 중단 메커니즘 구현
  5. **로깅** : 모든 비용 추적 이벤트를 로그에 기록 (감사 추적)

### 🔗 관련 도구 통합

**💡 추가 통합 옵션:**

  * **LangSmith** : LangChain 작업의 비용 추적
  * **Weights & Biases**: ML 실험과 비용 연계
  * **Prometheus + Grafana** : 시계열 비용 데이터 시각화
  * **Datadog** : 통합 모니터링 플랫폼
  * **PagerDuty** : 예산 초과 시 On-call 알림

## 🔧 프레임워크 통합

### LangChain 통합

from langchain.callbacks import BaseCallbackHandler from agent_evaluator import AgentEvaluator class TokenEconomyCallbackHandler(BaseCallbackHandler): def __init__(self, evaluator: AgentEvaluator): self.evaluator = evaluator self.task_counter = 0 def on_llm_end(self, response, **kwargs): self.task_counter += 1 # Extract token usage from response token_usage = response.llm_output.get("token_usage", {}) input_tokens = token_usage.get("prompt_tokens", 0) output_tokens = token_usage.get("completion_tokens", 0) # Track usage self.evaluator.track_usage( task_id=f"langchain_{self.task_counter}", input_tokens=input_tokens, output_tokens=output_tokens, task_type="langchain", model=response.llm_output.get("model_name", "default") ) # 사용 pricing = {"input": 0.01, "output": 0.03} evaluator = AgentEvaluator(pricing=pricing) callback = TokenEconomyCallbackHandler(evaluator) chain.run(input_text, callbacks=[callback]) # 비용 확인 stats = evaluator.get_usage_stats() print(f"Total Cost: ${stats['total_cost']:.4f}") 

### OpenAI API 직접 통합

from openai import OpenAI from agent_evaluator import AgentEvaluator client = OpenAI() # GPT-4 Turbo 가격 pricing = {"input": 0.01, "output": 0.03} evaluator = AgentEvaluator(pricing=pricing) # API 호출 response = client.chat.completions.create( model="gpt-4-turbo", messages=[{"role": "user", "content": prompt}] ) # 토큰 사용량 추적 evaluator.track_usage( task_id="openai_001", input_tokens=response.usage.prompt_tokens, output_tokens=response.usage.completion_tokens, task_type="qa", model="gpt-4-turbo" ) print(f"Cost: ${evaluator.get_usage_stats()['total_cost']:.4f}") 

### Anthropic Claude 통합

from anthropic import Anthropic from agent_evaluator import AgentEvaluator client = Anthropic() # Claude 3.5 Sonnet 가격 pricing = {"input": 0.003, "output": 0.015} # per 1K tokens evaluator = AgentEvaluator(pricing=pricing) # API 호출 response = client.messages.create( model="claude-3-5-sonnet-20241022", max_tokens=1024, messages=[{"role": "user", "content": prompt}] ) # 토큰 사용량 추적 evaluator.track_usage( task_id="claude_001", input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens, task_type="reasoning", model="claude-3-5-sonnet" ) print(f"Cost: ${evaluator.get_usage_stats()['total_cost']:.4f}") 

## 💡 비용 최적화 전략

### 1\. 모델 선택 최적화

  * **작업 난이도 매칭** : 간단한 작업은 저렴한 모델 (GPT-3.5, Claude Haiku) 사용
  * **Cascade Pattern** : 저렴한 모델로 시도 후 실패시 고급 모델 사용
  * **라우팅** : 작업 유형별로 최적 모델 자동 선택
  * **로컬 모델 혼용** : 민감하지 않은 작업은 Llama 등 로컬 모델 활용

### 2\. 프롬프트 최적화

  * **토큰 절약** : 불필요한 단어, 반복, 공백 제거
  * **Few-shot 예시 최소화** : 꼭 필요한 예시만 포함
  * **컨텍스트 압축** : 긴 문서는 요약 후 전달
  * **시스템 프롬프트 최적화** : 간결하면서도 명확하게 작성

### 3\. 캐싱 전략

  * **응답 캐싱** : 동일한 입력에 대한 응답 재사용
  * **Embedding 캐싱** : 벡터 임베딩 결과 저장
  * **Partial Caching** : 시스템 프롬프트 등 공통 부분 캐싱 (Anthropic Prompt Caching)
  * **TTL 설정** : 시간 경과 후 자동 무효화

### 4\. 출력 길이 제어

  * **max_tokens 설정** : 불필요하게 긴 응답 방지
  * **Stop Sequences** : 특정 패턴에서 생성 중단
  * **Temperature 조정** : 낮은 temperature로 간결한 응답 유도
  * **출력 형식 지정** : JSON, YAML 등 구조화된 형식으로 토큰 절약

### 5\. 배치 처리

  * **요청 묶기** : 여러 독립 요청을 하나로 결합
  * **Batch API** : OpenAI Batch API 등 활용 (50% 할인)
  * **비동기 처리** : 실시간 응답 불필요시 배치로 처리

### 6\. 스트리밍 활용

  * **조기 종료** : 충분한 정보 획득 시 스트림 중단
  * **점진적 처리** : 전체 응답 대기 없이 부분 처리
  * **사용자 경험 개선** : 빠른 첫 토큰으로 체감 속도 향상

### 비용 최적화 결정 트리

def select_optimal_model(task_complexity: str, budget_constraint: str): """Select the most cost-effective model""" if budget_constraint == "strict": if task_complexity == "low": return "gpt-3.5-turbo", {"input": 0.0005, "output": 0.0015} elif task_complexity == "medium": return "claude-3-haiku", {"input": 0.00025, "output": 0.00125} else: return "claude-3-sonnet", {"input": 0.003, "output": 0.015} elif budget_constraint == "moderate": if task_complexity == "high": return "gpt-4-turbo", {"input": 0.01, "output": 0.03} else: return "claude-3-5-sonnet", {"input": 0.003, "output": 0.015} else: # flexible budget if task_complexity == "critical": return "claude-3-opus", {"input": 0.015, "output": 0.075} else: return "gpt-4-turbo", {"input": 0.01, "output": 0.03} 

## ✨ Best Practices

**1\. 항상 토큰 사용량 추적**  
모든 LLM API 호출에 대해 토큰 사용량을 기록하여 정확한 비용 파악이 가능하도록 하세요. 

**2\. 월간 예산 설정 및 모니터링**  
예상 월간 비용을 정기적으로 확인하고, 예산 초과 위험시 알림을 받도록 설정하세요. 

**3\. 작업 유형별 벤치마크**  
각 작업 유형의 평균 토큰 사용량과 비용을 벤치마크로 설정하고 지속적으로 모니터링하세요. 

**4\. 입력/출력 비율 분석**  
출력 토큰이 입력 토큰보다 비싸므로, 불필요하게 긴 응답을 생성하지 않도록 주의하세요. 

**5\. 모델별 비용 효율성 평가**  
정기적으로 `get_cost_breakdown_by_model()`로 각 모델의 비용 기여도를 분석하세요. 

**6\. 비용 Percentile 모니터링**  
P95 비용을 확인하여 비용 급증 사례를 조기에 발견하세요. 

**7\. 캐싱으로 중복 비용 제거**  
동일한 입력에 대해 반복적으로 API를 호출하지 않도록 캐싱을 적극 활용하세요. 

**8\. 정기적인 가격 업데이트**  
LLM 모델 가격은 자주 변경되므로, pricing 설정을 주기적으로 업데이트하세요. 

## ⚠️ 주의사항

#### 1\. 가격 불일치 위험

`pricing` 설정이 실제 모델 가격과 다르면 비용 추정이 부정확해집니다. 정기적으로 공식 가격 페이지를 확인하고 업데이트하세요. 

#### 2\. 메모리 사용량

모든 사용 기록을 메모리에 유지하면 메모리 부족이 발생할 수 있습니다. 주기적으로 오래된 데이터를 파일이나 데이터베이스에 저장하고 메모리에서 제거하세요. 

#### 3\. 실시간 vs 배치 가격 차이

일부 제공사(OpenAI)는 Batch API에 대해 할인된 가격을 제공합니다. 실시간/배치 API를 구분하여 추적하세요. 

#### 4\. 숨겨진 비용

Fine-tuning, Embedding, Image generation 등 다른 API 사용 비용도 고려해야 합니다. LLM 텍스트 생성만이 유일한 비용이 아닙니다. 

#### 5\. 월간 예상 비용의 한계

`estimated_monthly_cost`는 현재 사용 패턴을 30배한 값으로, 트래픽 변동을 반영하지 못합니다. 참고용으로만 사용하고, 실제 예산 계획은 더 정교하게 수립하세요. 

## 🔗 관련 메트릭

메트릭 | 관계 | 설명  
---|---|---  
**Latency Metrics** | 상충 관계 | 빠른 모델은 비싸고, 저렴한 모델은 느린 경향  
**Quality Score** | 균형 필요 | 고급 모델은 품질이 높지만 비용도 높음  
**Retry Count** | 직접 영향 | 재시도가 많으면 토큰 사용량과 비용 증가  
**Task Completion Rate** | 효율성 지표 | 실패한 작업도 비용이 발생하므로 완료율 중요  
**Tool Usage (Layer 2)** | 간접 영향 | 도구 사용이 많으면 컨텍스트 토큰 증가  
  
## 📋 요약

**Cost/Token Economy** 는 AI 에이전트의 재정적 지속가능성을 보장하는 핵심 메트릭입니다. 

  * **정확한 비용 추적** : 입력/출력 토큰 별도 계산으로 정밀한 비용 산출
  * **월간 예산 관리** : 현재 사용 패턴 기반 월간 비용 예측
  * **작업 유형별 분석** : 어떤 작업이 비용을 많이 소모하는지 파악
  * **모델별 비교** : 여러 모델 사용시 각 모델의 비용 기여도 분석
  * **최적화 기회 식별** : 비효율적인 토큰 사용 패턴 발견 및 개선

  
Layer 1 네이티브 메트릭으로 외부 의존성 없이 실시간 비용 추적이 가능하며, 프로덕션 AI 시스템의 비용 효율성과 ROI 최적화에 필수적입니다.
