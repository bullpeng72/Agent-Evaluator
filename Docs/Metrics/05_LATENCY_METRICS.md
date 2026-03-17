# ⚡ Latency Metrics

Performance and Response Time Analysis

Agent Evaluator v0.5.2 - Layer 1 Foundation Metric

## 📊 개요

**Latency Metrics** 는 AI 에이전트의 응답 시간과 성능을 측정하고 분석하는 Layer 1 기본 메트릭입니다.   
  
총 응답 시간을 추적할 뿐만 아니라, 각 구성 요소별 시간을 분석하여 성능 병목 지점을 식별하고, 통계적 분석(평균, 중앙값, P95, P99)을 통해 시스템의 SLA 준수 여부를 모니터링합니다. 

### ⚠️ 중요성

  * **사용자 경험 (UX)** : 응답 시간이 사용자 만족도에 직접적인 영향을 미침
  * **성능 최적화** : 병목 지점을 식별하여 시스템 개선 우선순위 결정
  * **SLA 관리** : 서비스 수준 협약 준수 여부를 지속적으로 모니터링
  * **용량 계획** : P95/P99 메트릭을 통해 워스트 케이스 시나리오 대비
  * **비용 최적화** : 불필요하게 긴 처리 시간을 식별하여 리소스 낭비 방지

## 📍 구현 위치

**파일:** `agent_evaluator/core/agent_evaluator.py`  
**클래스:** `LatencyTracker`  
**라인:** 928-1058 (총 131줄) 

### 핵심 메서드

메서드 | 라인 | 기능  
---|---|---  
`record_latency()` | 934-943 | 작업의 응답 시간과 구성 요소별 시간 기록  
`get_latency_stats()` | 945-965 | 통계적 분석 (평균, 중앙값, P50/P95/P99, 표준편차)  
`analyze_bottlenecks()` | 967-999 | 성능 병목 지점 식별 및 분석  
`get_latency_by_type()` | 1001-1032 | 작업 유형별 지연 시간 통계 제공  
`check_sla_compliance()` | 1034-1058 | SLA 목표 대비 준수율 계산  
  
## ⚙️ 핵심 측정 알고리즘

**이 섹션에서는** `LatencyTracker` 클래스의 핵심 메서드들이 **어떻게 동작하는지** 상세히 설명합니다.

### 1️⃣ get_latency_stats() - 통계 계산 메서드

**목적** : 응답 시간 데이터로부터 8가지 통계 지표 계산

**위치** : Lines 945-965

def get_latency_stats(self, task_type: Optional[str] = None) -> Dict[str, float]: """8가지 통계 지표 계산""" # === 1. 데이터 필터링 === (Lines 947-949) latencies = self.latencies if task_type: latencies = [l for l in latencies if l["task_type"] == task_type] if not latencies: return {} # === 2. 시간 값 추출 === (Line 954) times = [l["total_time"] for l in latencies] # === 3. 8가지 통계 지표 계산 === (Lines 956-964) return { "mean": round(statistics.mean(times), 3), # 평균 "median": round(statistics.median(times), 3), # 중앙값 "p50": round(np.percentile(times, 50), 3), # 50th percentile "p95": round(np.percentile(times, 95), 3), # 95th percentile "p99": round(np.percentile(times, 99), 3), # 99th percentile "min": round(min(times), 3), # 최소값 "max": round(max(times), 3), # 최대값 "std": round(statistics.stdev(times) if len(times) > 1 else 0, 3) # 표준편차 } 

#### 📊 8가지 통계 지표 상세

지표 | 계산 방법 | 의미  
---|---|---  
**mean** | `sum(times) / len(times)` | 전체 평균 응답 시간 (이상치에 민감)  
**median** | 정렬 후 중간값 | 일반적인 사용자 경험 (이상치에 강건)  
**p50** | 50th percentile (median과 동일) | 50%의 요청이 이 시간 이하  
**p95** | 95th percentile | 95%의 요청이 이 시간 이하 (SLA 기준)  
**p99** | 99th percentile | 99%의 요청이 이 시간 이하 (워스트 케이스)  
**min** | 최소값 | 가장 빠른 응답 시간  
**max** | 최대값 | 가장 느린 응답 시간  
**std** | 표준편차 `√(Σ(x-μ)²/n)` | 응답 시간 변동성 (일관성 지표)  
  
**주의사항** :

  * **단일 데이터 처리** : len(times) == 1인 경우 표준편차는 0으로 반환
  * **소수점 정밀도** : 모든 값은 소수점 3자리로 반올림 (밀리초 단위)
  * **Percentile 계산** : NumPy의 `np.percentile()` 사용 (선형 보간)

### 2️⃣ analyze_bottlenecks() - 병목 지점 식별

**목적** : 구성 요소별 평균 시간을 계산하여 가장 느린 병목 지점 식별

**위치** : Lines 967-999

def analyze_bottlenecks(self) -> Dict[str, Any]: """병목 지점 분석 알고리즘""" if not self.latencies: return {} # === 1. 구성 요소별 시간 집계 === (Lines 973-982) breakdown_totals = defaultdict(float) breakdown_counts = defaultdict(int) for latency in self.latencies: # breakdown이 없거나 None이면 스킵 if not latency.get("breakdown"): continue for component, time in latency["breakdown"].items(): breakdown_totals[component] += time breakdown_counts[component] += 1 # === 2. breakdown 데이터가 없으면 빈 결과 반환 === (Lines 984-986) if not breakdown_totals: return {"breakdown_averages": {}, "bottleneck": None} # === 3. 구성 요소별 평균 계산 === (Lines 988-991) breakdown_avgs = { component: breakdown_totals[component] / breakdown_counts[component] for component in breakdown_totals } # === 4. 가장 느린 구성 요소 식별 === (Line 993) bottleneck = max(breakdown_avgs, key=breakdown_avgs.get) # === 5. 결과 반환 === (Lines 995-999) return { "breakdown_averages": {k: round(v, 3) for k, v in breakdown_avgs.items()}, "bottleneck": bottleneck, "bottleneck_avg_time": round(breakdown_avgs[bottleneck], 3) } 

#### ✅ 병목 분석 핵심 포인트

  1. **구성 요소 (Component) 예시** : 
     * `"llm_call"`: LLM API 호출 시간
     * `"retrieval"`: 문서 검색 시간
     * `"preprocessing"`: 입력 전처리 시간
     * `"postprocessing"`: 출력 후처리 시간
  2. **평균 계산 방식** : 각 구성 요소의 총 시간 / 발생 횟수
  3. **병목 식별** : `max(breakdown_avgs, key=breakdown_avgs.get)` \- 평균이 가장 큰 구성 요소
  4. **None 처리** : breakdown 데이터가 없으면 bottleneck=None 반환

#### ⚠️ 구현 한계 및 개선 방안

  * **메모리 제한 없음** : 
    * 모든 latency 데이터를 메모리에 저장 (리스트 크기 무제한)
    * **개선** : 순환 버퍼 (Circular Buffer) 또는 스트리밍 통계 사용
  * **Percentile 정확도** : 
    * 작은 샘플 크기에서 percentile이 부정확할 수 있음
    * **개선** : T-Digest 알고리즘 또는 HdrHistogram 도입
  * **시간 창 (Time Window) 부재** : 
    * 모든 과거 데이터를 포함하여 통계 계산
    * **개선** : 슬라이딩 윈도우 (예: 최근 1시간) 지원
  * **실시간 집계 부재** : 
    * 매번 전체 데이터를 순회하여 계산 (O(n) 복잡도)
    * **개선** : 증분 통계 업데이트 (Incremental Statistics)

#### 📊 Latency 통계 계산 흐름

graph TD A[latency_log List] --> B{get_latency_stats} B --> C[DataFrame 변환] C --> D[times 리스트 추출] D --> E1[mean 평균] D --> E2[median 중앙값] D --> E3[p50/p95/p99  
percentile] D --> E4[min/max] D --> E5[std 표준편차] E1 --> F[통계 dict 반환] E2 --> F E3 --> F E4 --> F E5 --> F A --> G{analyze_bottlenecks} G --> H[breakdown별 그룹화] H --> I[각 component 평균 계산] I --> J[max 찾기] J --> K[bottleneck 반환] style A fill:#667eea,color:#fff style B fill:#48bb78,color:#fff style G fill:#48bb78,color:#fff style F fill:#3182ce,color:#fff style K fill:#e53e3e,color:#fff 

## 📈 통계적 메트릭

#### Mean (평균)

모든 응답 시간의 산술 평균

**용도:** 전반적인 시스템 성능 이해

**주의:** 이상치(outlier)에 민감함

#### Median (중앙값)

정렬된 응답 시간의 중간값 (P50과 동일)

**용도:** 일반적인 사용자 경험 대표

**장점:** 이상치에 강건함

#### P95 (95th Percentile)

응답의 95%가 이 값 이하

**용도:** SLA 정의에 널리 사용

**의미:** 대부분 사용자의 경험

#### P99 (99th Percentile)

응답의 99%가 이 값 이하

**용도:** 워스트 케이스 분석

**의미:** 거의 모든 사용자의 경험

#### Standard Deviation (표준편차)

응답 시간의 변동성 측정

**용도:** 성능 일관성 평가

**해석:** 낮을수록 안정적

#### Min/Max

최소 및 최대 응답 시간

**용도:** 성능 범위 파악

**주의:** 극단적 이상치 가능

### 통계 메트릭 계산

def get_latency_stats(self, task_type: Optional[str] = None) -> Dict[str, float]: """Get latency statistics""" latencies = self.latencies if task_type: latencies = [l for l in latencies if l["task_type"] == task_type] if not latencies: return {} times = [l["total_time"] for l in latencies] return { "mean": round(statistics.mean(times), 3), "median": round(statistics.median(times), 3), "p50": round(np.percentile(times, 50), 3), "p95": round(np.percentile(times, 95), 3), "p99": round(np.percentile(times, 99), 3), "min": round(min(times), 3), "max": round(max(times), 3), "std": round(statistics.stdev(times) if len(times) > 1 else 0, 3) } 

## 🔍 병목 지점 분석

**병목 분석** 은 시스템에서 가장 시간이 많이 걸리는 구성 요소를 식별합니다. 각 작업의 breakdown을 집계하여 평균 시간이 가장 긴 구성 요소를 찾아냅니다. 

### 병목 분석 알고리즘

def analyze_bottlenecks(self) -> Dict[str, Any]: """Identify performance bottlenecks""" if not self.latencies: return {} # Aggregate breakdown times breakdown_totals = defaultdict(float) breakdown_counts = defaultdict(int) for latency in self.latencies: # Skip if breakdown is empty or None if not latency.get("breakdown"): continue for component, time in latency["breakdown"].items(): breakdown_totals[component] += time breakdown_counts[component] += 1 # Return empty if no breakdown data if not breakdown_totals: return {"breakdown_averages": {}, "bottleneck": None} # Calculate average time per component breakdown_avgs = { component: breakdown_totals[component] / breakdown_counts[component] for component in breakdown_totals } # Find the slowest component bottleneck = max(breakdown_avgs, key=breakdown_avgs.get) return { "breakdown_averages": {k: round(v, 3) for k, v in breakdown_avgs.items()}, "bottleneck": bottleneck, "bottleneck_avg_time": round(breakdown_avgs[bottleneck], 3) } 

### 일반적인 병목 지점

구성 요소 | 일반적인 원인 | 최적화 방법  
---|---|---  
**LLM API Call** | 외부 API 응답 시간 | 스트리밍 활용, 모델 선택 최적화, 배치 처리  
**Context Retrieval** | RAG, 벡터 DB 조회 | 인덱스 최적화, 캐싱, 쿼리 최적화  
**Tool Execution** | 외부 도구/API 호출 | 병렬 실행, 타임아웃 설정, 캐싱  
**Prompt Processing** | 복잡한 템플릿 렌더링 | 템플릿 최적화, 사전 컴파일  
**Output Parsing** | JSON/구조화 데이터 파싱 | 파서 최적화, 스키마 단순화  
  
## 📊 작업 유형별 분석

작업 유형(QA, Code Generation, Reasoning 등)에 따라 지연 시간 특성이 다릅니다. `get_latency_by_type()`는 각 작업 유형별로 통계를 분리하여 제공합니다. 

### 작업 유형별 통계 계산

def get_latency_by_type(self) -> Dict[str, Dict[str, float]]: """Get latency statistics broken down by task type""" if not self.latencies: return {} # Group latencies by task type latencies_by_type = defaultdict(list) for latency in self.latencies: task_type = latency.get("task_type", "unknown") latencies_by_type[task_type].append(latency["total_time"]) # Calculate statistics for each type type_stats = {} for task_type, times in latencies_by_type.items(): if times: type_stats[task_type] = { "avg": round(statistics.mean(times), 3), "median": round(statistics.median(times), 3), "min": round(min(times), 3), "max": round(max(times), 3), "p95": round(np.percentile(times, 95), 3), "p99": round(np.percentile(times, 99), 3), "count": len(times), "total_time": round(sum(times), 3), "std": round(statistics.stdev(times), 3) if len(times) > 1 else 0.0 } return type_stats 

### 사용 예시

# 작업 유형별 지연 시간 분석 type_stats = tracker.get_latency_by_type() for task_type, stats in type_stats.items(): print(f"\nTask Type: {task_type}") print(f" Count: {stats['count']}") print(f" Avg: {stats['avg']:.3f}s") print(f" P95: {stats['p95']:.3f}s") print(f" P99: {stats['p99']:.3f}s") # 출력 예시: # Task Type: qa # Count: 150 # Avg: 1.234s # P95: 2.456s # P99: 3.789s # # Task Type: code_generation # Count: 75 # Avg: 3.456s # P95: 5.678s # P99: 7.890s

## ✅ SLA 준수 모니터링

**SLA (Service Level Agreement)** 준수는 서비스 품질 보장의 핵심입니다. `check_sla_compliance()`는 작업 유형별 SLA 목표 대비 실제 성능을 모니터링합니다. 

### SLA 준수율 계산

SLA 준수율 계산식

Compliance Rate = (목표 시간 이내 완료 작업 수 / 전체 작업 수) × 100 

def check_sla_compliance(self, sla_targets: Dict[str, float]) -> Dict[str, Any]: """Check SLA compliance""" results = {} for task_type, target in sla_targets.items(): type_latencies = [ l["total_time"] for l in self.latencies if l["task_type"] == task_type ] if not type_latencies: continue # Calculate P95 latency p95 = np.percentile(type_latencies, 95) # Count how many tasks met the SLA within_sla = sum(1 for t in type_latencies if t <= target) results[task_type] = { "target": target, "p95": round(p95, 3), "compliance_rate": round((within_sla / len(type_latencies)) * 100, 2), "within_sla": within_sla, "total": len(type_latencies) } return results 

### SLA 목표 설정 예시

# SLA 목표 정의 (초 단위) sla_targets = { "qa": 2.0, # QA 작업은 2초 이내 "code_generation": 5.0, # 코드 생성은 5초 이내 "reasoning": 3.0, # 추론 작업은 3초 이내 "summarization": 4.0 # 요약 작업은 4초 이내 } # SLA 준수율 확인 compliance = tracker.check_sla_compliance(sla_targets) for task_type, result in compliance.items(): print(f"\n{task_type}:") print(f" Target: {result['target']:.1f}s") print(f" P95: {result['p95']:.3f}s") print(f" Compliance: {result['compliance_rate']:.1f}%") print(f" Within SLA: {result['within_sla']}/{result['total']}") # Alert if SLA is violated if result['compliance_rate'] < 95.0: print(f" ⚠️ WARNING: SLA compliance below 95%") 

### SLA 준수율 기준

준수율 | 상태 | 조치  
---|---|---  
≥ 99% | ✅ Excellent | 현재 상태 유지  
95-98% | ✓ Good | 모니터링 계속  
90-94% | ⚠️ Warning | 최적화 검토 필요  
< 90% | ❌ Critical | 즉각적인 조치 필요  
  
## 💻 사용 예시

### 기본 사용법

from agent_evaluator import AgentEvaluator import time # Evaluator 초기화 evaluator = AgentEvaluator() # 작업 시작 start_time = time.time() # 구성 요소별 시간 측정 breakdown = {} # 1. Context retrieval context_start = time.time() context = retrieve_context(query) breakdown["context_retrieval"] = time.time() - context_start # 2. LLM call llm_start = time.time() response = llm.generate(prompt) breakdown["llm_call"] = time.time() - llm_start # 3. Output parsing parse_start = time.time() result = parse_output(response) breakdown["output_parsing"] = time.time() - parse_start # 총 시간 계산 total_time = time.time() - start_time # Latency 기록 evaluator.record_latency( task_id="task_001", task_type="qa", total_time=total_time, breakdown=breakdown ) # 통계 조회 stats = evaluator.get_latency_stats(task_type="qa") print(f"Mean: {stats['mean']:.3f}s") print(f"P95: {stats['p95']:.3f}s") print(f"P99: {stats['p99']:.3f}s") 

### 병목 분석 예시

# 여러 작업 실행 후 병목 분석 bottleneck_analysis = evaluator.analyze_bottlenecks() print("=== Performance Bottleneck Analysis ===") print(f"\nComponent Average Times:") for component, avg_time in bottleneck_analysis["breakdown_averages"].items(): print(f" {component}: {avg_time:.3f}s") print(f"\n🔴 Bottleneck: {bottleneck_analysis['bottleneck']}") print(f" Average Time: {bottleneck_analysis['bottleneck_avg_time']:.3f}s") # 출력 예시: # === Performance Bottleneck Analysis === # # Component Average Times: # context_retrieval: 0.234s # llm_call: 1.567s # output_parsing: 0.089s # # 🔴 Bottleneck: llm_call # Average Time: 1.567s

## 🤖 평가 데이터 자동 처리 방안

**실제 프로젝트에서는 수백~수천 개의 작업에 대한 응답 시간을 측정하고 분석해야 합니다.**  
Latency Metrics는 시간 측정이 자동으로 이루어지므로 별도 데이터 준비가 불필요하지만, 측정 자동화, 병목 분석, SLA 모니터링 등을 효율적으로 처리하는 전략이 중요합니다. 

### 자동화 수준별 전략

레벨 | 자동화 범위 | 측정 방법 | 적용 시나리오  
---|---|---|---  
**Level 1** | 기본 시간 측정 | 총 시간만 자동 기록 | 빠른 프로토타입  
**Level 2** | 데코레이터 기반 | 함수 자동 래핑 | 기존 코드 최소 수정  
**Level 3** | 컨텍스트 매니저 | 구성 요소별 자동 측정 | 상세 병목 분석  
**Level 4** | 프레임워크 통합 | 콜백 기반 자동 수집 | LangChain, CrewAI 등  
**Level 5** | 실시간 모니터링 | 자동 알림 + 대시보드 | 프로덕션 환경  
  
### Level 1: 기본 자동 시간 측정

#### 💡 핵심 아이디어

Agent 실행의 시작/종료 시간만 자동 측정 (breakdown 없음)

**장점** : 가장 간단, 코드 수정 최소

**단점** : 병목 분석 불가

from agent_evaluator import PerformanceMonitor import time class BasicLatencyTracker: """기본 자동 시간 측정""" def __init__(self, monitor: PerformanceMonitor): self.monitor = monitor def execute_and_track(self, task_id: str, agent_func, *args, **kwargs): """Agent 함수 실행 + 자동 시간 측정""" # 시작 시간 start_time = time.time() try: # Agent 실행 result = agent_func(*args, **kwargs) success = True except Exception as e: result = None success = False # 총 시간 계산 total_time = time.time() - start_time # 자동 기록 self.monitor.record_task( task_id=task_id, success=success, latency=total_time, ← 자동 측정 completion_score=1.0 if success else 0.0 ) return result # ============================================================ # 사용 예시 # ============================================================ monitor = PerformanceMonitor() tracker = BasicLatencyTracker(monitor) # 여러 작업 실행 questions = [ "파이썬 리스트 정렬 방법은?", "머신러닝이란?", # ... 수백 개 ] for i, question in enumerate(questions): result = tracker.execute_and_track( task_id=f"task_{i:03d}", agent_func=your_agent.run, question ) # 통계 자동 계산 latency_stats = monitor.latency_tracker.get_latency_stats() print(f"Mean: {latency_stats['mean']:.3f}s") print(f"P95: {latency_stats['p95']:.3f}s") print(f"P99: {latency_stats['p99']:.3f}s") 

### Level 2: 데코레이터 기반 자동 측정

#### 💡 핵심 아이디어

Python 데코레이터로 함수에 시간 측정을 자동 추가

**장점** : 기존 함수 수정 불필요, 재사용 가능

**단점** : Breakdown 측정 제한적

from agent_evaluator import PerformanceMonitor import time from functools import wraps def track_latency(monitor: PerformanceMonitor, task_type: str = "default"): """시간 측정 데코레이터""" def decorator(func): @wraps(func) def wrapper(*args, **kwargs): task_id = kwargs.get("task_id", f"{func.__name__}_{int(time.time())}") # 시작 시간 start_time = time.time() try: result = func(*args, **kwargs) success = True except Exception as e: result = None success = False raise finally: # 시간 자동 기록 total_time = time.time() - start_time monitor.record_task( task_id=task_id, success=success, latency=total_time, completion_score=1.0 if success else 0.0 ) return result return wrapper return decorator # ============================================================ # 사용 예시 # ============================================================ monitor = PerformanceMonitor() @track_latency(monitor, task_type="qa") def qa_agent(question: str, task_id: str = None) -> str: """QA Agent (자동 시간 측정)""" response = your_llm.generate(question) return response @track_latency(monitor, task_type="code_generation") def code_agent(prompt: str, task_id: str = None) -> str: """Code Generation Agent (자동 시간 측정)""" code = your_llm.generate_code(prompt) return code # 사용 - 데코레이터가 자동으로 시간 측정 for i in range(100): qa_response = qa_agent( f"질문 {i}", task_id=f"qa_{i:03d}" ) # 통계 자동 계산 latency_stats = monitor.latency_tracker.get_latency_stats() print(f"QA Agent - Mean: {latency_stats['mean']:.3f}s") 

### Level 3: 컨텍스트 매니저로 구성 요소별 자동 측정

#### 💡 핵심 아이디어

Context Manager로 구성 요소별 시간을 자동 수집하여 병목 분석 가능

**장점** : Breakdown 자동 수집, 병목 분석 가능

**단점** : 코드 블록 구조 필요

from agent_evaluator import PerformanceMonitor import time from contextlib import contextmanager class LatencyContextManager: """구성 요소별 시간 자동 측정""" def __init__(self, monitor: PerformanceMonitor): self.monitor = monitor self.task_id = None self.total_start = None self.breakdown = {} def start_task(self, task_id: str): """작업 시작""" self.task_id = task_id self.total_start = time.time() self.breakdown = {} return self @contextmanager def measure_component(self, component_name: str): """구성 요소 시간 측정""" start = time.time() try: yield finally: elapsed = time.time() - start self.breakdown[component_name] = elapsed def end_task(self, success: bool = True): """작업 종료 및 자동 기록""" total_time = time.time() - self.total_start self.monitor.record_task( task_id=self.task_id, success=success, latency=total_time, completion_score=1.0 if success else 0.0 ) # Breakdown 별도 기록 self.monitor.latency_tracker.record_latency( task_id=self.task_id, task_type="auto", total_time=total_time, breakdown=self.breakdown ) # ============================================================ # 사용 예시 # ============================================================ monitor = PerformanceMonitor() ctx = LatencyContextManager(monitor) for i in range(100): # 작업 시작 ctx.start_task(f"task_{i:03d}") # 구성 요소 1: Context Retrieval with ctx.measure_component("context_retrieval"): context = retrieve_context(query) # 구성 요소 2: LLM Call with ctx.measure_component("llm_call"): response = llm.generate(prompt) # 구성 요소 3: Output Parsing with ctx.measure_component("output_parsing"): result = parse_output(response) # 작업 종료 (자동 기록) ctx.end_task(success=True) # 병목 분석 자동 수행 bottleneck_analysis = monitor.latency_tracker.analyze_bottlenecks() print(f"Bottleneck: {bottleneck_analysis['bottleneck']}") print(f"Average Time: {bottleneck_analysis['bottleneck_avg_time']:.3f}s") 

### Level 4: 프레임워크 자동 통합 (LangChain 예시)

#### 💡 핵심 아이디어

프레임워크의 콜백 시스템으로 자동으로 모든 시간 측정

**장점** : 완전 자동, 코드 수정 불필요

**단점** : 프레임워크 종속적

from langchain.callbacks import BaseCallbackHandler from agent_evaluator import PerformanceMonitor import time class AutoLatencyCallback(BaseCallbackHandler): """LangChain 자동 Latency 측정 콜백""" def __init__(self, monitor: PerformanceMonitor): self.monitor = monitor self.task_times = {} self.breakdowns = {} def on_chain_start(self, serialized, inputs, run_id, **kwargs): """체인 시작 - 자동 타이머 시작""" self.task_times[run_id] = time.time() self.breakdowns[run_id] = {} def on_llm_start(self, serialized, prompts, run_id, **kwargs): """LLM 시작 - 자동 기록""" self.breakdowns[run_id]["llm_start_time"] = time.time() def on_llm_end(self, response, run_id, **kwargs): """LLM 종료 - 자동 계산""" if "llm_start_time" in self.breakdowns[run_id]: llm_time = time.time() - self.breakdowns[run_id]["llm_start_time"] self.breakdowns[run_id]["llm_call"] = llm_time def on_retriever_start(self, serialized, query, run_id, **kwargs): """Retriever 시작""" self.breakdowns[run_id]["retriever_start_time"] = time.time() def on_retriever_end(self, documents, run_id, **kwargs): """Retriever 종료""" if "retriever_start_time" in self.breakdowns[run_id]: retriever_time = time.time() - self.breakdowns[run_id]["retriever_start_time"] self.breakdowns[run_id]["context_retrieval"] = retriever_time def on_chain_end(self, outputs, run_id, **kwargs): """체인 종료 - 자동 기록""" total_time = time.time() - self.task_times[run_id] # Breakdown에서 임시 시간 제거 breakdown = { k: v for k, v in self.breakdowns[run_id].items() if not k.endswith("_start_time") } # 자동 기록 self.monitor.record_task( task_id=str(run_id), success=True, latency=total_time, completion_score=1.0 ) self.monitor.latency_tracker.record_latency( task_id=str(run_id), task_type="langchain", total_time=total_time, breakdown=breakdown ) # 정리 del self.task_times[run_id] del self.breakdowns[run_id] # ============================================================ # 사용 예시 - 완전 자동 # ============================================================ from langchain.chains import RetrievalQA from langchain.llms import OpenAI monitor = PerformanceMonitor() callback = AutoLatencyCallback(monitor) # LangChain 설정 llm = OpenAI(temperature=0) qa_chain = RetrievalQA.from_chain_type( llm=llm, retriever=vectorstore.as_retriever(), callbacks=[callback] ← 콜백만 추가하면 자동 측정 ) # 실행 - 모든 시간 자동 측정됨 for i, question in enumerate(questions): result = qa_chain.run(question) # 통계 및 병목 자동 분석 latency_stats = monitor.latency_tracker.get_latency_stats() bottleneck = monitor.latency_tracker.analyze_bottlenecks() print(f"Mean: {latency_stats['mean']:.3f}s") print(f"P95: {latency_stats['p95']:.3f}s") print(f"Bottleneck: {bottleneck['bottleneck']}") 

### Level 5: 실시간 모니터링 및 자동 알림

#### 💡 핵심 아이디어

SLA 위반 시 자동 알림, 실시간 대시보드 업데이트

**장점** : 프로덕션 모니터링, 조기 경보

**단점** : 인프라 필요

from agent_evaluator import PerformanceMonitor import time import threading from typing import Callable class RealTimeLatencyMonitor: """실시간 Latency 모니터링 및 자동 알림""" def __init__( self, monitor: PerformanceMonitor, sla_targets: dict[str, float], alert_callback: Callable = None ): self.monitor = monitor self.sla_targets = sla_targets self.alert_callback = alert_callback or self.default_alert self.violation_count = {} self.check_interval = 60 # 60초마다 체크 self.running = False def default_alert(self, message: str): """기본 알림 (콘솔 출력)""" print(f"🚨 [ALERT] {message}") def start_monitoring(self): """모니터링 시작 (백그라운드 스레드)""" self.running = True thread = threading.Thread(target=self._monitor_loop, daemon=True) thread.start() print(f"✅ Real-time monitoring started (interval: {self.check_interval}s)") def stop_monitoring(self): """모니터링 중지""" self.running = False def _monitor_loop(self): """모니터링 루프""" while self.running: time.sleep(self.check_interval) self.check_sla_violations() def check_sla_violations(self): """SLA 위반 체크 및 알림""" compliance = self.monitor.latency_tracker.check_sla_compliance(self.sla_targets) for task_type, result in compliance.items(): compliance_rate = result["compliance_rate"] # 95% 미만이면 경고 if compliance_rate < 95.0: if task_type not in self.violation_count: self.violation_count[task_type] = 0 self.violation_count[task_type] += 1 message = ( f"SLA Violation: {task_type} - " f"Compliance: {compliance_rate:.1f}% " f"(Target: {result['target']}s, P95: {result['p95']:.3f}s) " f"[Count: {self.violation_count[task_type]}]" ) self.alert_callback(message) # 90% 미만이면 긴급 elif compliance_rate < 90.0: message = ( f"🔴 CRITICAL SLA Violation: {task_type} - " f"Compliance: {compliance_rate:.1f}%" ) self.alert_callback(message) def get_real_time_stats(self) -> dict: """실시간 통계 조회""" latency_stats = self.monitor.latency_tracker.get_latency_stats() bottleneck = self.monitor.latency_tracker.analyze_bottlenecks() compliance = self.monitor.latency_tracker.check_sla_compliance(self.sla_targets) return { "latency_stats": latency_stats, "bottleneck": bottleneck, "sla_compliance": compliance, "violation_count": self.violation_count } # ============================================================ # 사용 예시 # ============================================================ def slack_alert(message: str): """Slack 알림 (예시)""" # slack_webhook_url로 메시지 전송 print(f"Slack: {message}") monitor = PerformanceMonitor() # SLA 목표 설정 sla_targets = { "qa": 2.0, "code_generation": 5.0, "reasoning": 3.0 } # 실시간 모니터링 시작 rt_monitor = RealTimeLatencyMonitor( monitor=monitor, sla_targets=sla_targets, alert_callback=slack_alert ← 커스텀 알림 ) rt_monitor.start_monitoring() # 작업 실행 (백그라운드에서 자동 모니터링) for i in range(1000): result = your_agent.run(f"task {i}") monitor.record_task(f"task_{i}", success=True, latency=1.5) # 실시간 통계 조회 stats = rt_monitor.get_real_time_stats() print(f"Current P95: {stats['latency_stats']['p95']:.3f}s") print(f"Bottleneck: {stats['bottleneck']['bottleneck']}") 

### 성능 최적화 자동화 팁

**⚡ 대량 Latency 측정 최적화**

#### 1\. 측정 오버헤드 최소화

  * **time.perf_counter()** : time.time()보다 정확 (나노초 단위)
  * **샘플링** : 모든 요청이 아닌 10%만 상세 측정
  * **비동기 기록** : 시간 기록을 별도 스레드로 처리

#### 2\. 메모리 관리

  * **Rolling Window** : 최근 1000개만 메모리 유지
  * **주기적 저장** : 5분마다 파일/DB 저장 후 메모리 정리
  * **집계 우선** : 원본 대신 통계만 저장 (P50/P95/P99)

#### 3\. 병렬 처리

  * **ThreadPoolExecutor** : I/O 바운드 측정
  * **asyncio** : 비동기 Agent 측정
  * **멀티프로세싱** : CPU 바운드 병목 분석

# 고성능 시간 측정 예시 import time from collections import deque class HighPerformanceLatencyTracker: def __init__(self, max_size: int = 1000): self.latencies = deque(maxlen=max_size) # Rolling window self.sample_rate = 0.1 # 10%만 샘플링 def measure(self, func, *args, **kwargs): # 샘플링 결정 should_sample = (time.time() % 10) < self.sample_rate * 10 if should_sample: # 정밀 측정 (perf_counter) start = time.perf_counter() result = func(*args, **kwargs) elapsed = time.perf_counter() - start self.latencies.append(elapsed) else: # 샘플링 안함 (빠름) result = func(*args, **kwargs) return result def get_stats(self): if not self.latencies: return {} import numpy as np return { "p50": round(np.percentile(self.latencies, 50), 3), "p95": round(np.percentile(self.latencies, 95), 3), "p99": round(np.percentile(self.latencies, 99), 3) } 

#### ⚠️ 자동화 주의사항

  * **시간 동기화** : 분산 시스템에서는 NTP로 시간 동기화 필수
  * **콜드 스타트** : 첫 요청은 초기화 시간 포함, 별도 처리
  * **타임아웃** : 무한 대기 방지를 위한 적절한 타임아웃 설정
  * **측정 오버헤드** : 너무 잦은 시간 측정은 성능 저하 유발
  * **알림 피로** : 알림 빈도 제한 (같은 이슈는 1시간에 1번)

## 🔧 프레임워크 통합

### LangChain 통합

from langchain.callbacks import BaseCallbackHandler from agent_evaluator import AgentEvaluator import time class LatencyCallbackHandler(BaseCallbackHandler): def __init__(self, evaluator: AgentEvaluator): self.evaluator = evaluator self.start_times = {} self.breakdowns = {} def on_chain_start(self, serialized, inputs, run_id, **kwargs): self.start_times[run_id] = time.time() self.breakdowns[run_id] = {} def on_llm_start(self, serialized, prompts, run_id, **kwargs): self.breakdowns[run_id]["llm_start"] = time.time() def on_llm_end(self, response, run_id, **kwargs): llm_time = time.time() - self.breakdowns[run_id]["llm_start"] self.breakdowns[run_id]["llm_call"] = llm_time def on_chain_end(self, outputs, run_id, **kwargs): total_time = time.time() - self.start_times[run_id] self.evaluator.record_latency( task_id=str(run_id), task_type="langchain", total_time=total_time, breakdown=self.breakdowns[run_id] ) # 사용 evaluator = AgentEvaluator() callback = LatencyCallbackHandler(evaluator) chain.run(input_text, callbacks=[callback]) 

### CrewAI 통합

from crewai import Agent, Task, Crew from agent_evaluator import AgentEvaluator import time class LatencyMonitoredCrew(Crew): def __init__(self, *args, evaluator: AgentEvaluator, **kwargs): super().__init__(*args, **kwargs) self.evaluator = evaluator def kickoff(self, inputs: dict): start_time = time.time() breakdown = {} # Execute crew result = super().kickoff(inputs) total_time = time.time() - start_time # Record latency self.evaluator.record_latency( task_id=f"crew_{int(time.time())}", task_type="crewai", total_time=total_time, breakdown=breakdown ) return result # 사용 evaluator = AgentEvaluator() crew = LatencyMonitoredCrew( agents=[agent1, agent2], tasks=[task1, task2], evaluator=evaluator ) result = crew.kickoff({"input": "data"}) 

### LangGraph 통합

from langgraph.graph import StateGraph from agent_evaluator import AgentEvaluator import time def create_monitored_graph(evaluator: AgentEvaluator): graph = StateGraph() def monitored_node(state): node_start = time.time() # Your node logic result = process_node(state) node_time = time.time() - node_start # Store timing in state if "breakdown" not in state: state["breakdown"] = {} state["breakdown"]["node_time"] = node_time return result graph.add_node("monitored", monitored_node) # Add final node to record total latency def record_latency(state): evaluator.record_latency( task_id=state.get("task_id"), task_type="langgraph", total_time=state.get("total_time"), breakdown=state.get("breakdown", {}) ) return state graph.add_node("record", record_latency) return graph 

### AutoGen 통합

from autogen import AssistantAgent, UserProxyAgent from agent_evaluator import AgentEvaluator import time class LatencyMonitoredAgent(AssistantAgent): def __init__(self, *args, evaluator: AgentEvaluator, **kwargs): super().__init__(*args, **kwargs) self.evaluator = evaluator def generate_reply(self, messages, sender, config=None): start_time = time.time() breakdown = {} # Generate reply reply_start = time.time() reply = super().generate_reply(messages, sender, config) breakdown["reply_generation"] = time.time() - reply_start total_time = time.time() - start_time # Record latency self.evaluator.record_latency( task_id=f"autogen_{sender.name}_{int(time.time())}", task_type="autogen", total_time=total_time, breakdown=breakdown ) return reply # 사용 evaluator = AgentEvaluator() assistant = LatencyMonitoredAgent( name="assistant", llm_config=llm_config, evaluator=evaluator ) 

## ✨ Best Practices

**1\. 의미 있는 Breakdown 제공**  
총 시간만이 아니라 구성 요소별 시간을 기록하여 병목 지점을 정확히 식별하세요. 

**2\. 작업 유형 구분**  
QA, Code Generation, Reasoning 등 작업 유형을 명확히 구분하여 각 유형별 성능 특성을 파악하세요. 

**3\. P95/P99 중심 모니터링**  
평균값보다 P95/P99를 SLA 기준으로 사용하여 대부분의 사용자 경험을 보장하세요. 

**4\. 정기적인 병목 분석**  
주기적으로 `analyze_bottlenecks()`를 실행하여 새로운 성능 이슈를 조기에 발견하세요. 

**5\. SLA 목표 현실적 설정**  
작업 유형의 복잡도와 외부 의존성을 고려하여 달성 가능한 SLA를 설정하세요. 

**6\. 콜드 스타트 고려**  
첫 번째 요청은 초기화 시간이 포함될 수 있으므로 별도로 추적하거나 제외하세요. 

**7\. 타임스탬프 기록**  
시간대별 성능 변화를 분석하기 위해 타임스탬프를 함께 기록하세요. 

**8\. 알림 임계값 설정**  
SLA 준수율이 95% 미만으로 떨어지면 자동 알림을 보내도록 설정하세요. 

## ⚠️ 주의사항

#### 1\. 네트워크 지연 변동성

외부 API 호출(LLM, RAG)은 네트워크 상태에 따라 지연 시간이 크게 변동될 수 있습니다. 충분한 샘플을 수집하여 통계적 신뢰도를 확보하세요. 

#### 2\. 시간 측정 오버헤드

`time.time()` 호출 자체도 약간의 오버헤드가 있습니다. 매우 짧은 작업(< 10ms)의 경우 측정 오차가 클 수 있습니다. 

#### 3\. 병렬 처리 고려

여러 구성 요소가 병렬로 실행되는 경우, breakdown 합계가 total_time보다 클 수 있습니다. 순차/병렬 실행을 명확히 구분하여 기록하세요. 

#### 4\. 메모리 관리

모든 latency 기록을 메모리에 유지하면 메모리 부족이 발생할 수 있습니다. 주기적으로 오래된 데이터를 파일/DB에 저장하고 메모리에서 제거하세요. 

#### 5\. 타임존 일관성

분산 시스템에서는 모든 노드의 시간이 동기화되어 있는지 확인하세요. UTC 기준 타임스탬프 사용을 권장합니다. 

## 🔗 관련 메트릭

메트릭 | 관계 | 설명  
---|---|---  
**Cost/Token Economy** | 상충 관계 | 빠른 모델은 비용이 높고, 저렴한 모델은 느린 경향  
**Quality Score** | 균형 필요 | 응답 속도와 품질 사이의 트레이드오프 존재  
**Retry Count** | 직접 영향 | 재시도가 많으면 전체 latency 증가  
**Task Completion Rate** | 간접 영향 | 타임아웃으로 인한 실패는 완료율 저하  
**Think Time (Layer 2)** | 구성 요소 | 에이전트의 사고 시간은 latency의 일부  
  
## 🚀 성능 최적화 전략

### 1\. LLM API 최적화

  * **모델 선택** : 작업에 적합한 가장 작은 모델 사용 (GPT-4 대신 GPT-3.5)
  * **스트리밍** : 긴 응답의 경우 스트리밍으로 첫 토큰 시간(TTFT) 단축
  * **배치 처리** : 독립적인 여러 요청을 한 번에 처리
  * **프롬프트 최적화** : 불필요한 토큰 제거로 처리 시간 단축

### 2\. Context Retrieval 최적화

  * **벡터 인덱스** : FAISS, Pinecone 등 효율적인 벡터 DB 사용
  * **캐싱** : 자주 조회되는 컨텍스트를 메모리에 캐싱
  * **Top-K 조정** : 검색 결과 수를 최소화하여 후처리 시간 단축
  * **필터링** : 메타데이터 필터로 검색 범위 사전 축소

### 3\. Tool Execution 최적화

  * **병렬 실행** : 독립적인 도구 호출은 병렬로 실행
  * **타임아웃 설정** : 무한 대기 방지를 위한 적절한 타임아웃
  * **결과 캐싱** : 동일한 입력에 대한 도구 실행 결과 재사용
  * **폴백 전략** : 실패 시 빠른 대체 방법 제공

### 4\. 인프라 최적화

  * **지역 선택** : API 서버와 가까운 리전에서 실행
  * **연결 풀링** : HTTP 연결 재사용으로 handshake 오버헤드 제거
  * **CDN 활용** : 정적 리소스는 CDN으로 배포
  * **로드 밸런싱** : 트래픽을 여러 인스턴스로 분산

## 📋 요약

**Latency Metrics** 는 AI 에이전트의 성능을 종합적으로 모니터링하는 핵심 메트릭입니다. 

  * **통계 분석** : Mean, Median, P95, P99로 다양한 관점에서 성능 평가
  * **병목 식별** : 구성 요소별 시간 분석으로 최적화 우선순위 결정
  * **작업 유형별 추적** : 각 작업 유형의 성능 특성 이해
  * **SLA 모니터링** : 서비스 품질 목표 달성 여부 지속적 확인
  * **프레임워크 통합** : LangChain, CrewAI, LangGraph, AutoGen 지원

  
Layer 1 네이티브 메트릭으로 외부 의존성 없이 실시간 성능 모니터링이 가능하며, 프로덕션 환경에서 SLA 준수와 사용자 경험 최적화에 필수적입니다.
