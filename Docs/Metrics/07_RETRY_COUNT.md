# 🔄 Retry Count

Retry and Self-Correction Tracking

Agent Evaluator v0.5.1 - Layer 1 Foundation Metric

## 📊 개요

**Retry Count** 는 AI 에이전트가 작업을 완료하기 위해 재시도한 횟수와 패턴을 추적하는 Layer 1 기본 메트릭입니다.   
  
AI 에이전트는 첫 시도에서 실패할 수 있으며, 자체 수정(self-correction) 능력을 통해 재시도합니다. 이 메트릭은 첫 시도 성공률, 재시도율, 최종 성공률, 그리고 실패 원인 패턴을 분석하여 에이전트의 신뢰성과 자체 수정 능력을 평가합니다. 

### ⚠️ 중요성

  * **신뢰성 지표** : 높은 첫 시도 성공률은 안정적인 에이전트를 의미
  * **자체 수정 능력** : 재시도 후 성공률로 에이전트의 학습/수정 능력 평가
  * **비용 영향** : 재시도는 토큰 사용량과 지연 시간을 증가시킴
  * **실패 패턴 식별** : 반복되는 실패 원인을 찾아 근본적 개선
  * **사용자 경험** : 과도한 재시도는 응답 지연으로 이어짐

## 📍 구현 위치

**파일:** `agent_evaluator/core/agent_evaluator.py`  
**클래스:** `RetryCorrectionTracker`  
**라인:** 1362-1437 (총 76줄) 

### 핵심 메서드

메서드 | 라인 | 기능  
---|---|---  
`track_attempts()` | 1368-1379 | 작업의 모든 시도 기록 및 분석  
`get_retry_metrics()` | 1381-1415 | 재시도 통계 및 성공률 계산  
`analyze_failure_patterns()` | 1417-1437 | 실패 원인 패턴 분석 및 빈도 계산  
  
## 📊 동작 흐름 다이어그램

#### Retry/Correction 추적 흐름

graph TD A[task 시작] --> B{첫 시도} B -->|성공| C[record_task  
retries=0] B -->|실패| D[record_retry] D --> E{재시도} E -->|성공| F[record_correction] E -->|또 실패| D F --> G[get_retry_stats 호출] C --> G G --> H[DataFrame 변환] H --> I1[total_retries 합산] H --> I2[correction_rate 계산  
성공/전체] H --> I3[avg_retries 평균] H --> I4[retry_distribution  
by_type] I1 --> J[통계 dict 반환] I2 --> J I3 --> J I4 --> J style A fill:#667eea,color:#fff style B fill:#ed8936,color:#fff style D fill:#e53e3e,color:#fff style F fill:#38a169,color:#fff style G fill:#48bb78,color:#fff style J fill:#3182ce,color:#fff 

## 📈 핵심 메트릭

#### First Attempt Success Rate

첫 번째 시도에서 성공한 작업의 비율

**목표:** 80% 이상

**의미:** 에이전트의 기본 성능

#### Retry Rate

재시도가 필요했던 작업의 비율

**목표:** 20% 이하

**의미:** 실패 빈도

#### Eventual Success Rate

재시도 포함 최종적으로 성공한 비율

**목표:** 95% 이상

**의미:** 전체 시스템 신뢰성

#### Correction Success Rate

재시도가 필요했던 작업 중 성공한 비율

**목표:** 75% 이상

**의미:** 자체 수정 능력

#### Avg Attempts per Task

작업당 평균 시도 횟수

**목표:** 1.5 이하

**의미:** 효율성 지표

#### Total Retry Time

재시도에 소요된 총 시간

**목표:** 최소화

**의미:** 재시도 비용

### 메트릭 계산 공식

First Attempt Success Rate

= (첫 시도 성공 작업 수 / 전체 작업 수) × 100 

Retry Rate

= (재시도가 필요한 작업 수 / 전체 작업 수) × 100 

Correction Success Rate

= (재시도 후 성공 작업 수 / 재시도가 필요했던 작업 수) × 100 

## 📝 시도 추적

각 작업의 모든 시도를 기록하고, 첫 시도 성공 여부, 최종 성공 여부, 재시도 원인 등을 분석합니다. 

### 시도 기록 메서드

def track_attempts(self, task_id: str, attempts_log: List[Dict[str, Any]]): """Track retry attempts for a task""" analysis = { "task_id": task_id, "total_attempts": len(attempts_log), "first_attempt_success": attempts_log[0].get("success", False), "final_success": attempts_log[-1].get("success", False), "retry_reasons": [ a.get("retry_reason", "unknown") for a in attempts_log if not a.get("success") ], "total_retry_time": sum(a.get("duration", 0) for a in attempts_log[1:]) } self.attempts.append(analysis) 

### 시도 로그 구조

# 각 시도는 다음 정보를 포함: attempt = { "success": True/False, # 시도 성공 여부 "retry_reason": "validation_error", # 실패 원인 "duration": 2.5, # 시도 소요 시간 (초) "output": "...", # 시도 결과 "error": "..." # 에러 메시지 (실패시) } # 작업의 전체 시도 로그 attempts_log = [ {"success": False, "retry_reason": "validation_error", "duration": 1.2}, {"success": False, "retry_reason": "format_error", "duration": 1.5}, {"success": True, "duration": 1.8} ] 

### 일반적인 재시도 원인

원인 | 설명 | 해결 방법  
---|---|---  
**validation_error** | 출력이 검증 규칙을 통과하지 못함 | 프롬프트에 검증 규칙 명시, 예시 추가  
**format_error** | JSON, YAML 등 형식 파싱 실패 | 출력 형식 예시 강화, 스키마 제공  
**api_error** | 외부 API 호출 실패 | Exponential backoff, 재시도 로직  
**timeout** | 응답 시간 초과 | 타임아웃 설정 조정, 모델 변경  
**tool_execution_error** | 도구 실행 중 에러 | 도구 입력 검증 강화, 에러 처리 개선  
**content_policy** | 콘텐츠 정책 위반 | 입력 필터링, 프롬프트 조정  
  
## 📊 재시도 통계

def get_retry_metrics(self) -> Dict[str, Any]: """Get retry statistics""" if not self.attempts: return {} df = pd.DataFrame(self.attempts) # Calculate metrics tasks_with_retries = (df["total_attempts"] > 1).sum() retry_rate = (df["total_attempts"] > 1).mean() * 100 first_attempt_success_rate = df["first_attempt_success"].mean() * 100 eventual_success_rate = df["final_success"].mean() * 100 # Retry success count: tasks that failed first but eventually succeeded retry_success_count = ((~df["first_attempt_success"]) & df["final_success"]).sum() # Correction success rate: of tasks that needed retries, how many succeeded tasks_needing_retry = (~df["first_attempt_success"]).sum() correction_success_rate = ( (retry_success_count / tasks_needing_retry * 100) if tasks_needing_retry > 0 else 0 ) return { "total_tasks_with_retries": int(tasks_with_retries), "retry_rate": round(retry_rate, 2), "first_attempt_success_rate": round(first_attempt_success_rate, 2), "eventual_success_rate": round(eventual_success_rate, 2), "retry_success_count": int(retry_success_count), "correction_success_rate": round(correction_success_rate, 2), "avg_attempts_per_task": round(df["total_attempts"].mean(), 2), "total_retry_time": round(df["total_retry_time"].sum(), 2), "avg_retry_time": round(df["total_retry_time"].mean(), 2) } 

### 메트릭 해석 가이드

메트릭 | 우수 | 양호 | 개선 필요  
---|---|---|---  
**First Attempt Success Rate** | ≥ 85% | 70-84% | < 70%  
**Retry Rate** | ≤ 15% | 16-30% | > 30%  
**Eventual Success Rate** | ≥ 95% | 85-94% | < 85%  
**Correction Success Rate** | ≥ 80% | 60-79% | < 60%  
**Avg Attempts per Task** | ≤ 1.3 | 1.3-1.8 | > 1.8  
  
## 🔍 실패 패턴 분석

반복되는 실패 원인을 식별하면 근본적인 문제를 해결하여 재시도율을 낮출 수 있습니다. 

def analyze_failure_patterns(self) -> Dict[str, Any]: """Analyze common failure patterns""" all_reasons = [] for attempt in self.attempts: all_reasons.extend(attempt["retry_reasons"]) if not all_reasons: return {"patterns": {}} # Count each failure reason reason_counts = defaultdict(int) for reason in all_reasons: reason_counts[reason] += 1 # Sort by frequency (most common first) return { "patterns": dict(sorted( reason_counts.items(), key=lambda x: x[1], reverse=True )), "most_common": max(reason_counts, key=reason_counts.get) if reason_counts else None } 

### 실패 패턴 사용 예시

# 실패 패턴 분석 patterns = tracker.analyze_failure_patterns() print("=== Failure Pattern Analysis ===") print(f"Most Common Failure: {patterns['most_common']}") print("\nFailure Frequency:") for reason, count in patterns["patterns"].items(): percentage = (count / sum(patterns["patterns"].values())) * 100 print(f" {reason}: {count} times ({percentage:.1f}%)") # 출력 예시: # === Failure Pattern Analysis === # Most Common Failure: validation_error # # Failure Frequency: # validation_error: 45 times (52.3%) # format_error: 28 times (32.6%) # api_error: 13 times (15.1%)

### 패턴 기반 개선 전략

실패 패턴 | 빈도 임계값 | 권장 조치  
---|---|---  
validation_error > 40% | 높음 | 프롬프트에 검증 규칙 상세 명시, Few-shot 예시 추가  
format_error > 30% | 높음 | JSON Schema 제공, 출력 형식 예시 강화  
api_error > 20% | 중간 | Exponential backoff, Circuit breaker 패턴 적용  
timeout > 15% | 중간 | 타임아웃 설정 조정, 더 빠른 모델 사용  
content_policy > 10% | 낮음 | 입력 사전 필터링, 프롬프트 안전성 검토  
  
## 💻 사용 예시

### 기본 사용법

from agent_evaluator import AgentEvaluator # Evaluator 초기화 evaluator = AgentEvaluator() # 작업 실행 및 재시도 로직 attempts_log = [] max_attempts = 3 for attempt in range(max_attempts): start_time = time.time() try: result = agent.execute(task) # Validate result if validate_output(result): attempts_log.append({ "success": True, "duration": time.time() - start_time, "output": result }) break else: attempts_log.append({ "success": False, "retry_reason": "validation_error", "duration": time.time() - start_time }) except JSONDecodeError: attempts_log.append({ "success": False, "retry_reason": "format_error", "duration": time.time() - start_time }) # Track attempts evaluator.track_attempts( task_id="task_001", attempts_log=attempts_log ) # Get metrics metrics = evaluator.get_retry_metrics() print(f"First Attempt Success Rate: {metrics['first_attempt_success_rate']:.1f}%") print(f"Retry Rate: {metrics['retry_rate']:.1f}%") 

### 자체 수정 에이전트 구현

def execute_with_self_correction(agent, task, evaluator, max_attempts=3): """Execute task with self-correction capability""" attempts_log = [] previous_errors = [] for attempt_num in range(max_attempts): start_time = time.time() # Build prompt with error feedback prompt = build_prompt(task) if previous_errors: prompt += f"\n\nPrevious attempts failed with errors: {previous_errors}" prompt += "\nPlease correct these issues in your response." try: result = agent.execute(prompt) # Validate validation_result = validate_comprehensive(result) if validation_result["valid"]: attempts_log.append({ "success": True, "duration": time.time() - start_time, "output": result }) break else: error_msg = validation_result["error"] previous_errors.append(error_msg) attempts_log.append({ "success": False, "retry_reason": "validation_error", "duration": time.time() - start_time, "error": error_msg }) except Exception as e: previous_errors.append(str(e)) attempts_log.append({ "success": False, "retry_reason": "execution_error", "duration": time.time() - start_time, "error": str(e) }) # Track all attempts evaluator.track_attempts( task_id=task["id"], attempts_log=attempts_log ) return attempts_log[-1] if attempts_log[-1]["success"] else None

### 실패 패턴 기반 알림

def check_failure_alerts(evaluator, threshold=0.3): """Check if any failure pattern exceeds threshold""" patterns = evaluator.analyze_failure_patterns() if not patterns["patterns"]: return total_failures = sum(patterns["patterns"].values()) for reason, count in patterns["patterns"].items(): rate = count / total_failures if rate > threshold: print(f"⚠️ ALERT: {reason} failure rate is {rate*100:.1f}%") print(f" Occurred {count} times out of {total_failures} failures") print(f" Recommended action: {get_recommendation(reason)}") # Send notification send_alert(f"High failure rate for {reason}: {rate*100:.1f}%") def get_recommendation(reason): """Get recommendation based on failure reason""" recommendations = { "validation_error": "Add more detailed validation rules to prompt", "format_error": "Provide JSON schema or format examples", "api_error": "Implement exponential backoff and circuit breaker", "timeout": "Increase timeout or use faster model" } return recommendations.get(reason, "Review and optimize agent logic") 

## 🤖 평가 데이터 자동 처리 방안

**실전 적용 시 핵심 과제:**  
Retry Count 평가는 **재시도 발생 시점, 실패 원인, 재시도 패턴을 자동으로 수집** 해야 합니다. 실제 프로젝트에서는 API 실패, 네트워크 오류, Rate Limit, Timeout 등 다양한 실패 상황을 자동으로 감지하고 추적해야 합니다.   
  
이 섹션에서는 **재시도 자동 추적, 실패 패턴 자동 분석, Circuit Breaker 통합** 을 위한 5단계 자동화 전략을 제공합니다. 

### 📊 자동화 전략 개요

Level | 방법 | 자동화 범위 | 성능 | 난이도  
---|---|---|---|---  
**1** | Try-Catch 기반 자동 추적 | 예외 발생 시 자동 기록 | ⚡⚡⚡⚡⚡ | ⭐  
**2** | Decorator 기반 Retry | 자동 재시도 + 추적 | ⚡⚡⚡⚡ | ⭐⭐  
**3** | Retry 라이브러리 통합 | tenacity, backoff 활용 | ⚡⚡⚡⚡⚡ | ⭐⭐  
**4** | Circuit Breaker 패턴 | 장애 전파 방지 + 추적 | ⚡⚡⚡ | ⭐⭐⭐  
**5** | 통합 Resilience 시스템 | 전체 안정성 관리 | ⚡⚡⚡⚡⚡ | ⭐⭐⭐⭐  
  
### Level 1: Try-Catch 기반 자동 추적

가장 기본적인 방법으로, 예외가 발생할 때마다 자동으로 재시도 횟수를 기록합니다.

from agent_evaluator import PerformanceMonitor import time class SimpleRetryTracker: """Try-Catch 기반 재시도 추적""" def __init__(self, monitor: PerformanceMonitor, max_retries: int = 3): self.monitor = monitor self.max_retries = max_retries def execute_with_retry(self, task_id: str, func, *args, **kwargs): """재시도 로직 + 자동 추적""" retry_count = 0 last_error = None for attempt in range(self.max_retries + 1): try: print(f"🔄 시도 {attempt + 1}/{self.max_retries + 1}: {task_id}") result = func(*args, **kwargs) # ✅ 성공 시 재시도 횟수 기록 self.monitor.record_task( task_id=task_id, retry_count=retry_count, success=True ) print(f"✅ 성공! (재시도: {retry_count}회)") return result except Exception as e: retry_count += 1 last_error = e print(f"❌ 실패: {str(e)}") if attempt < self.max_retries: # 지수 백오프 wait_time = 2 ** attempt print(f"⏳ {wait_time}초 후 재시도...") time.sleep(wait_time) else: # ✅ 최종 실패 기록 self.monitor.record_task( task_id=task_id, retry_count=retry_count, success=False, error_message=str(last_error) ) print(f"💥 최종 실패 (총 재시도: {retry_count}회)") raise last_error # 사용 예시 import random def unstable_api_call(): """불안정한 API 시뮬레이션 (50% 실패율)""" if random.random() < 0.5: raise Exception("API Error: Rate limit exceeded") return "Success!" monitor = PerformanceMonitor() tracker = SimpleRetryTracker(monitor, max_retries=3) # 여러 작업 실행 for i in range(10): task_id = f"task_{i+1}" try: result = tracker.execute_with_retry(task_id, unstable_api_call) except Exception: pass # 최종 실패는 이미 기록됨 # 📊 재시도 통계 retry_stats = monitor.retry_evaluator.get_retry_stats() print(f"\n📊 재시도 통계:") print(f" 평균 재시도 횟수: {retry_stats['average_retries']:.2f}") print(f" 최대 재시도 횟수: {retry_stats['max_retries']}") print(f" 재시도율: {retry_stats['retry_rate']:.2f}%") 

**⚡ 장점:**

  * 구현 간단, 즉시 적용 가능
  * 모든 예외 자동 추적
  * 지수 백오프 자동 적용

**⚠️ 한계:**

  * 각 함수마다 명시적으로 래핑 필요
  * 재시도 로직이 반복적

### Level 2: Decorator 기반 자동 재시도

Decorator를 사용하여 기존 함수에 자동 재시도 및 추적 기능을 주입합니다.

from functools import wraps import time import traceback def auto_retry(monitor: PerformanceMonitor, max_retries: int = 3, backoff: float = 2.0, exceptions: tuple = (Exception,)): """자동 재시도 Decorator""" def decorator(func): @wraps(func) def wrapper(*args, **kwargs): task_id = f"{func.__name__}_{int(time.time() * 1000)}" retry_count = 0 last_error = None for attempt in range(max_retries + 1): try: result = func(*args, **kwargs) # ✅ 성공 시 기록 monitor.record_task( task_id=task_id, retry_count=retry_count, success=True ) return result except exceptions as e: retry_count += 1 last_error = e if attempt < max_retries: wait_time = backoff ** attempt print(f"⚠️ {func.__name__} 실패 (재시도 {retry_count}/{max_retries}), {wait_time:.1f}초 후 재시도") time.sleep(wait_time) else: # ✅ 최종 실패 기록 monitor.record_task( task_id=task_id, retry_count=retry_count, success=False, error_message=str(last_error) ) raise return wrapper return decorator # 사용 예시 monitor = PerformanceMonitor() # ✅ Decorator로 자동 재시도 + 추적 @auto_retry(monitor, max_retries=3, backoff=2.0) def fetch_data_from_api(url: str): """API 호출 (불안정)""" import random if random.random() < 0.6: raise ConnectionError("Network timeout") return f"Data from {url}" @auto_retry(monitor, max_retries=5, backoff=1.5, exceptions=(ValueError, KeyError)) def process_data(data: dict): """데이터 처리 (특정 예외만 재시도)""" import random if random.random() < 0.4: raise ValueError("Invalid data format") return "Processed" # 자동 재시도 + 추적 (코드 수정 없이) for i in range(20): try: data = fetch_data_from_api(f"https://api.example.com/data/{i}") result = process_data({"value": i}) except Exception: pass # 📊 통계 확인 retry_stats = monitor.retry_evaluator.get_retry_stats() print(f"\n평균 재시도: {retry_stats['average_retries']:.2f}") print(f"재시도율: {retry_stats['retry_rate']:.1f}%") 

**💡 Pro Tip:** Decorator 패턴은 기존 코드를 수정하지 않고도 재시도 로직을 적용할 수 있는 가장 우아한 방법입니다. 

### Level 3: Retry 라이브러리 통합 (tenacity)

Production-grade retry 라이브러리인 `tenacity`를 PerformanceMonitor와 통합합니다.

from tenacity import ( retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log, after_log ) import logging class TenacityRetryTracker: """Tenacity 라이브러리 + PerformanceMonitor 통합""" def __init__(self, monitor: PerformanceMonitor): self.monitor = monitor self.logger = logging.getLogger(__name__) def create_retry_decorator(self, max_attempts: int = 3, min_wait: int = 1, max_wait: int = 10, task_prefix: str = "task"): """재시도 Decorator 생성 (통계 자동 기록)""" def decorator(func): # Tenacity retry 설정 @retry( stop=stop_after_attempt(max_attempts), wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait), retry=retry_if_exception_type(Exception), before_sleep=before_sleep_log(self.logger, logging.WARNING), reraise=True ) @wraps(func) def wrapper(*args, **kwargs): task_id = f"{task_prefix}_{func.__name__}_{int(time.time() * 1000)}" retry_count = 0 # Tenacity 내부 통계 추적을 위한 래퍼 try: result = func(*args, **kwargs) # ✅ 성공 시 재시도 횟수 계산 # (Tenacity는 성공까지 시도한 횟수를 직접 제공하지 않음) self.monitor.record_task( task_id=task_id, retry_count=retry_count, # 추후 개선 가능 success=True ) return result except Exception as e: # ✅ 최종 실패 기록 self.monitor.record_task( task_id=task_id, retry_count=max_attempts, # 최대 시도 횟수 success=False, error_message=str(e) ) raise return wrapper return decorator # 사용 예시 import logging logging.basicConfig(level=logging.INFO) monitor = PerformanceMonitor() retry_tracker = TenacityRetryTracker(monitor) # ✅ Tenacity 기반 자동 재시도 @retry_tracker.create_retry_decorator(max_attempts=5, min_wait=1, max_wait=10, task_prefix="api") def call_external_api(endpoint: str): import random if random.random() < 0.7: raise ConnectionError(f"Failed to connect to {endpoint}") return f"Response from {endpoint}" @retry_tracker.create_retry_decorator(max_attempts=3, task_prefix="db") def query_database(query: str): import random if random.random() < 0.5: raise Exception("Database timeout") return "Query result" # 자동 재시도 실행 for i in range(50): try: call_external_api(f"/api/v1/users/{i}") query_database(f"SELECT * FROM users WHERE id={i}") except Exception: pass # 📊 통계 retry_stats = monitor.retry_evaluator.get_retry_stats() print(f"재시도율: {retry_stats['retry_rate']:.1f}%") print(f"평균 재시도: {retry_stats['average_retries']:.2f}") 

**✅ Tenacity 장점:**

  * Production-grade: 실전 검증된 라이브러리
  * 다양한 재시도 전략: 지수 백오프, 고정 대기, Jitter 등
  * 조건부 재시도: 특정 예외만 재시도
  * 로깅 통합: 재시도 과정 자동 로깅

### Level 4: Circuit Breaker 패턴 통합

Circuit Breaker 패턴을 적용하여 반복적인 실패 시 자동으로 요청을 차단합니다.

from enum import Enum from datetime import datetime, timedelta import threading class CircuitState(Enum): CLOSED = "CLOSED" # 정상 작동 OPEN = "OPEN" # 차단 (요청 거부) HALF_OPEN = "HALF_OPEN" # 테스트 중 class CircuitBreaker: """Circuit Breaker 패턴 + 재시도 추적""" def __init__(self, monitor: PerformanceMonitor, failure_threshold: int = 5, timeout: int = 60, name: str = "default"): self.monitor = monitor self.name = name self.failure_threshold = failure_threshold self.timeout = timeout self.state = CircuitState.CLOSED self.failure_count = 0 self.last_failure_time = None self.lock = threading.Lock() def call(self, func, *args, **kwargs): """Circuit Breaker를 통한 함수 호출""" with self.lock: if self.state == CircuitState.OPEN: if self._should_attempt_reset(): self.state = CircuitState.HALF_OPEN print(f"🔄 Circuit [{self.name}] HALF_OPEN (테스트 중)") else: # ✅ Circuit Open 상태 기록 task_id = f"circuit_blocked_{int(time.time() * 1000)}" self.monitor.record_task( task_id=task_id, retry_count=0, success=False, error_message=f"Circuit breaker [{self.name}] is OPEN" ) raise Exception(f"Circuit breaker [{self.name}] is OPEN") # 함수 실행 task_id = f"circuit_{self.name}_{int(time.time() * 1000)}" try: result = func(*args, **kwargs) self._on_success() # ✅ 성공 기록 self.monitor.record_task( task_id=task_id, retry_count=0, success=True ) return result except Exception as e: self._on_failure() # ✅ 실패 기록 self.monitor.record_task( task_id=task_id, retry_count=0, success=False, error_message=str(e) ) raise def _should_attempt_reset(self): if self.last_failure_time is None: return False return datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout) def _on_success(self): with self.lock: self.failure_count = 0 if self.state == CircuitState.HALF_OPEN: self.state = CircuitState.CLOSED print(f"✅ Circuit [{self.name}] CLOSED (정상화)") def _on_failure(self): with self.lock: self.failure_count += 1 self.last_failure_time = datetime.now() if self.failure_count >= self.failure_threshold: self.state = CircuitState.OPEN print(f"🚨 Circuit [{self.name}] OPEN (차단됨, {self.timeout}초 후 재시도)") # 사용 예시 monitor = PerformanceMonitor() api_circuit = CircuitBreaker(monitor, failure_threshold=3, timeout=10, name="external_api") def unreliable_service(): import random if random.random() < 0.8: # 80% 실패율 raise Exception("Service unavailable") return "Success" # Circuit Breaker를 통한 호출 for i in range(20): try: result = api_circuit.call(unreliable_service) print(f"✅ 요청 {i+1}: {result}") except Exception as e: print(f"❌ 요청 {i+1}: {e}") time.sleep(1) # 📊 통계 (Circuit Breaker가 막은 요청도 포함) retry_stats = monitor.retry_evaluator.get_retry_stats() print(f"\n총 작업: {retry_stats['total_tasks']}") print(f"성공률: {retry_stats.get('success_rate', 0):.1f}%") 

**💡 Circuit Breaker 핵심:**

  * **CLOSED** : 정상 작동, 모든 요청 허용
  * **OPEN** : 장애 감지, 모든 요청 차단 (Fast Fail)
  * **HALF_OPEN** : 일부 요청 허용하여 복구 테스트

Circuit Breaker는 연쇄 장애(Cascade Failure)를 방지하는 핵심 패턴입니다. 

### Level 5: 통합 Resilience 시스템 (Production-Ready)

재시도, Circuit Breaker, Timeout, Fallback을 모두 통합한 완전한 안정성 관리 시스템입니다.

from typing import Optional, Callable import signal class TimeoutException(Exception): pass class ResilienceSystem: """통합 안정성 관리 시스템""" def __init__(self, monitor: PerformanceMonitor): self.monitor = monitor self.circuit_breakers = {} def get_circuit_breaker(self, name: str, **kwargs): """Circuit Breaker 가져오기 (없으면 생성)""" if name not in self.circuit_breakers: self.circuit_breakers[name] = CircuitBreaker( self.monitor, name=name, **kwargs ) return self.circuit_breakers[name] def execute(self, func: Callable, task_id: str, max_retries: int = 3, backoff: float = 2.0, timeout: Optional[int] = None, circuit_breaker: Optional[str] = None, fallback: Optional[Callable] = None, *args, **kwargs): """ 통합 실행: \- 재시도 (Retry) \- 타임아웃 (Timeout) \- Circuit Breaker \- Fallback """ retry_count = 0 last_error = None # Circuit Breaker 선택 cb = self.get_circuit_breaker(circuit_breaker) if circuit_breaker else None for attempt in range(max_retries + 1): try: # Circuit Breaker 체크 if cb: result = cb.call(self._execute_with_timeout, func, timeout, *args, **kwargs) else: result = self._execute_with_timeout(func, timeout, *args, **kwargs) # ✅ 성공 self.monitor.record_task( task_id=task_id, retry_count=retry_count, success=True ) return result except Exception as e: retry_count += 1 last_error = e if attempt < max_retries: wait_time = backoff ** attempt print(f"⚠️ [{task_id}] 재시도 {retry_count}/{max_retries} ({wait_time:.1f}초 후)") time.sleep(wait_time) # ✅ 최종 실패 - Fallback 시도 if fallback: try: print(f"🔄 [{task_id}] Fallback 실행") result = fallback(*args, **kwargs) self.monitor.record_task( task_id=task_id, retry_count=retry_count, success=True, error_message=f"Fallback used after {retry_count} retries" ) return result except Exception as fallback_error: last_error = fallback_error # ✅ 완전 실패 self.monitor.record_task( task_id=task_id, retry_count=retry_count, success=False, error_message=str(last_error) ) raise last_error def _execute_with_timeout(self, func, timeout, *args, **kwargs): """타임아웃 포함 실행""" if timeout is None: return func(*args, **kwargs) def timeout_handler(signum, frame): raise TimeoutException(f"Function timed out after {timeout} seconds") # 타임아웃 설정 (Unix 계열만) try: signal.signal(signal.SIGALRM, timeout_handler) signal.alarm(timeout) result = func(*args, **kwargs) signal.alarm(0) # 타임아웃 취소 return result except AttributeError: # Windows에서는 signal.SIGALRM 미지원 return func(*args, **kwargs) def get_statistics(self): """전체 통계""" retry_stats = self.monitor.retry_evaluator.get_retry_stats() circuit_stats = { name: { "state": cb.state.value, "failure_count": cb.failure_count } for name, cb in self.circuit_breakers.items() } return { "retry_stats": retry_stats, "circuit_breakers": circuit_stats } # ============================================ # 완전 자동화 실사용 예시 # ============================================ monitor = PerformanceMonitor() resilience = ResilienceSystem(monitor) # 불안정한 서비스들 def primary_service(data): import random if random.random() < 0.7: raise Exception("Primary service failed") return f"Primary result: {data}" def fallback_service(data): """Fallback: 캐시된 데이터 반환""" return f"Fallback result (cached): {data}" # ✅ 통합 Resilience 실행 for i in range(30): task_id = f"resilient_task_{i+1}" try: result = resilience.execute( primary_service, task_id=task_id, max_retries=3, backoff=1.5, timeout=5, circuit_breaker="primary_api", fallback=fallback_service, data=f"item_{i}" ) print(f"✅ {task_id}: {result}") except Exception as e: print(f"❌ {task_id}: {e}") time.sleep(0.5) # 📊 최종 통계 stats = resilience.get_statistics() print(f"\n📊 Resilience 시스템 통계:") print(f" 총 작업: {stats['retry_stats']['total_tasks']}") print(f" 평균 재시도: {stats['retry_stats']['average_retries']:.2f}") print(f" 재시도율: {stats['retry_stats']['retry_rate']:.1f}%") print(f"\n🔌 Circuit Breaker 상태:") for name, cb_stats in stats["circuit_breakers"].items(): print(f" {name}: {cb_stats['state']} (실패: {cb_stats['failure_count']})") 

**🎯 Production-Ready Resilience!**  
Level 5 시스템을 사용하면: 

  * ✅ 자동 재시도 + 지수 백오프
  * ✅ Circuit Breaker로 장애 전파 방지
  * ✅ Timeout으로 무한 대기 방지
  * ✅ Fallback으로 서비스 연속성 보장
  * ✅ 모든 재시도 패턴 자동 추적

### 🎯 자동화 전략 선택 가이드

사용 사례 | 추천 Level | 이유  
---|---|---  
단순한 API 호출 | **Level 1-2** | Try-Catch 또는 Decorator로 충분  
복잡한 재시도 정책 | **Level 3** | Tenacity로 세밀한 제어  
외부 서비스 의존성 | **Level 4** | Circuit Breaker로 장애 격리  
Mission-Critical 시스템 | **Level 5** | 완전한 안정성 보장  
  
### ⚠️ 자동화 시 주의사항

  1. **무한 재시도 방지** : 반드시 max_retries 설정
  2. **Thundering Herd 방지** : Jitter 추가 (랜덤 대기 시간)
  3. **Idempotency** : 재시도해도 안전한 작업인지 확인 (멱등성)
  4. **비용 고려** : 재시도마다 비용 발생 (API 호출료 등)
  5. **모니터링** : 재시도율이 높으면 근본 원인 해결 필요

### 🔗 관련 라이브러리

**💡 추천 라이브러리:**

  * **tenacity** : Production-grade retry 라이브러리
  * **backoff** : Decorator 기반 간단한 재시도
  * **pybreaker** : Circuit Breaker 구현
  * **resilience4j (Java)** : 종합 Resilience 라이브러리
  * **Polly (.NET)** : .NET용 Resilience 프레임워크

## 🔧 프레임워크 통합

### LangChain 통합

from langchain.chains import LLMChain from langchain.output_parsers import PydanticOutputParser from agent_evaluator import AgentEvaluator import time def execute_with_retry_tracking(chain: LLMChain, input_text: str, evaluator: AgentEvaluator, max_retries=3): attempts_log = [] for attempt in range(max_retries): start_time = time.time() try: result = chain.run(input_text) # Validate output if parser.parse(result): attempts_log.append({ "success": True, "duration": time.time() - start_time }) break except Exception as e: attempts_log.append({ "success": False, "retry_reason": type(e).__name__, "duration": time.time() - start_time, "error": str(e) }) # Track attempts evaluator.track_attempts( task_id=f"langchain_{int(time.time())}", attempts_log=attempts_log ) return result if attempts_log[-1]["success"] else None

### CrewAI 통합

from crewai import Agent, Task from agent_evaluator import AgentEvaluator import time class RetryTrackingAgent(Agent): def __init__(self, *args, evaluator: AgentEvaluator, **kwargs): super().__init__(*args, **kwargs) self.evaluator = evaluator def execute_task(self, task: Task, max_attempts=3): attempts_log = [] for attempt in range(max_attempts): start_time = time.time() try: result = super().execute_task(task) # Check if result meets criteria if self.validate_result(result, task): attempts_log.append({ "success": True, "duration": time.time() - start_time }) break else: attempts_log.append({ "success": False, "retry_reason": "validation_failed", "duration": time.time() - start_time }) except Exception as e: attempts_log.append({ "success": False, "retry_reason": "execution_error", "duration": time.time() - start_time }) # Track all attempts self.evaluator.track_attempts( task_id=task.id, attempts_log=attempts_log ) return result if attempts_log[-1]["success"] else None

## ✨ Best Practices

**1\. 최대 재시도 횟수 제한**  
무한 재시도를 방지하기 위해 최대 시도 횟수(일반적으로 3회)를 설정하세요. 

**2\. 구체적인 실패 원인 기록**  
단순히 "failed"가 아닌 구체적인 실패 원인을 기록하여 패턴 분석이 가능하도록 하세요. 

**3\. 에러 피드백 제공**  
재시도 시 이전 시도의 에러 정보를 프롬프트에 포함하여 자체 수정을 유도하세요. 

**4\. Exponential Backoff**  
API 에러 등 일시적 문제의 경우, 재시도 간격을 점진적으로 늘리는 exponential backoff를 사용하세요. 

**5\. 재시도 비용 모니터링**  
재시도는 토큰과 시간을 추가로 소비하므로, `total_retry_time`과 토큰 사용량을 함께 모니터링하세요. 

**6\. 정기적인 패턴 분석**  
주기적으로 `analyze_failure_patterns()`를 실행하여 반복되는 문제를 식별하고 해결하세요. 

**7\. 임계값 기반 알림**  
특정 실패 원인이 30% 이상 발생하면 자동 알림을 보내도록 설정하세요. 

**8\. 첫 시도 성공률 최적화 우선**  
재시도 성공률보다 첫 시도 성공률을 높이는 것이 비용 효율적입니다. 

## ⚠️ 주의사항

#### 1\. 재시도 루프 방지

반드시 `max_attempts`를 설정하여 무한 재시도를 방지하세요. 재시도 로직에 버그가 있으면 비용이 급증할 수 있습니다. 

#### 2\. 비용 증가 고려

재시도는 토큰 사용량과 API 호출 비용을 증가시킵니다. 재시도율이 30%를 초과하면 비용이 크게 증가하므로 근본 원인을 해결해야 합니다. 

#### 3\. 사용자 경험 저하

재시도가 많으면 응답 시간이 길어져 사용자 경험이 저하됩니다. 실시간 응답이 필요한 경우 재시도 횟수를 최소화하세요. 

#### 4\. 일시적 vs 영구적 오류 구분

API 타임아웃 등 일시적 오류는 재시도가 유효하지만, 프롬프트 오류 등 영구적 문제는 재시도해도 해결되지 않습니다. 

#### 5\. 컨텍스트 누적 주의

재시도 시 이전 에러를 프롬프트에 포함하면 컨텍스트가 누적되어 토큰이 증가합니다. 핵심 에러 메시지만 간결하게 포함하세요. 

## 🔗 관련 메트릭

메트릭 | 관계 | 설명  
---|---|---  
**Task Completion Rate** | 직접 영향 | 재시도 성공으로 완료율 향상 가능  
**Latency Metrics** | 직접 영향 | 재시도는 총 응답 시간을 증가시킴  
**Cost/Token Economy** | 직접 영향 | 재시도는 토큰 사용량과 비용 증가  
**Quality Score** | 간접 영향 | 재시도 후 품질이 향상될 수 있음  
**Self-Correction Rate (Layer 2)** | 밀접 관련 | Retry Count는 자체 수정 능력의 기초 지표  
  
## 🚀 재시도율 최적화 전략

### 1\. 프롬프트 개선

  * **명확한 출력 형식 지정** : JSON Schema, Pydantic 모델 등 구조화된 형식 제공
  * **Few-shot 예시 추가** : 성공적인 출력 예시를 2-3개 포함
  * **검증 규칙 명시** : 출력이 만족해야 할 조건을 명확히 설명
  * **에러 가능성 사전 경고** : 흔한 실수와 주의사항을 프롬프트에 포함

### 2\. 검증 로직 강화

  * **단계적 검증** : 형식 → 내용 → 비즈니스 규칙 순으로 검증
  * **부분 수용** : 완벽하지 않아도 사용 가능한 부분은 수용
  * **자동 수정** : 간단한 형식 오류는 자동으로 수정
  * **구체적 피드백** : 무엇이 잘못되었는지 명확히 전달

### 3\. 모델 선택

  * **고성능 모델 사용** : 복잡한 작업은 GPT-4, Claude Opus 등 사용
  * **Instruction-tuned 모델** : 지시 따르기에 최적화된 모델 선택
  * **Fine-tuning** : 반복적인 작업은 fine-tuned 모델 고려

### 4\. 에러 처리 개선

  * **Circuit Breaker** : 반복 실패 시 일시적으로 다른 방법 시도
  * **Fallback 전략** : 실패 시 더 간단한 작업으로 대체
  * **Graceful Degradation** : 완전 실패보다 부분 성공 선택

### 재시도 최적화 결정 트리

def should_retry(error_type: str, attempt: int, max_attempts: int) -> bool: """Decide whether to retry based on error type""" if attempt >= max_attempts: return False # Transient errors - always retry if error_type in ["api_error", "timeout", "rate_limit"]: return True # Correctable errors - retry with feedback if error_type in ["validation_error", "format_error"]: return attempt < 2 # Max 2 attempts for these # Permanent errors - don't retry if error_type in ["content_policy", "invalid_input"]: return False # Unknown errors - retry once return attempt == 0

## 📋 요약

**Retry Count** 는 AI 에이전트의 신뢰성과 자체 수정 능력을 평가하는 핵심 메트릭입니다. 

  * **첫 시도 성공률** : 에이전트의 기본 성능 지표
  * **재시도율** : 실패 빈도를 나타내는 핵심 지표
  * **자체 수정 능력** : 재시도 후 성공률로 평가
  * **실패 패턴 분석** : 반복되는 문제를 식별하여 근본 해결
  * **비용 영향 추적** : 재시도로 인한 추가 토큰 및 시간 비용

  
Layer 1 네이티브 메트릭으로 외부 의존성 없이 재시도 패턴을 추적하며, 첫 시도 성공률 80% 이상, 최종 성공률 95% 이상을 목표로 해야 합니다.
