# 🔍 Hallucination Detection

Semantic Hallucination Detection with DeepEval

Agent Evaluator v0.5.0 - Layer 3 DeepEval Metric

## 🎯 개요

**Hallucination Detection** 은 LLM이 생성한 출력이 제공된 컨텍스트(Context)와 의미적으로 일치하는지 평가하는 DeepEval의 고급 메트릭입니다.   
  
"환각(Hallucination)"은 LLM이 컨텍스트에 없는 정보를 만들어내거나, 사실과 다른 내용을 생성하는 현상입니다. DeepEval의 HallucinationMetric은 LLM을 평가자로 사용하여 의미적 일관성을 검증합니다. 

### ⚠️ 중요성

  * **신뢰성 확보** : RAG 시스템에서 검색된 문서 기반 답변 검증
  * **사실성 보장** : 근거 없는 정보 생성 방지
  * **법적 리스크 감소** : 금융, 의료, 법률 분야에서 필수적
  * **사용자 신뢰 구축** : 일관되고 정확한 정보 제공
  * **품질 관리** : 출력 품질의 자동 검증 체계 구축

## 📊 다이어그램 시각화

### 1️⃣ 핵심 개념 및 환각 탐지 (DeepEval Semantic)
```python
    graph TD
        A[Response + Context] --> B[HallucinationMetric  
    DeepEval]
        B --> C[Semantic Analysis  
    LLM-based 80-90% accuracy]
    
        C --> D[Context Grounding Check]
        D --> E[모든 주장이 Context에 근거하는가?]
    
        E --> F{Semantic Verification}
        F -->|모든 주장 지원됨| G[hallucination_score = 1.0  
    No Hallucination]
        F -->|일부 주장 미지원| H[hallucination_score = 0.5-0.9  
    Partial Hallucination]
        F -->|대부분 미지원| I[hallucination_score = 0.0-0.4  
    Severe Hallucination]
    
        G --> J{Quality Level}
        H --> J
        I --> J
    
        J -->|≥ 0.90| K[Excellent: 신뢰 가능]
        J -->|0.70-0.89| L[Good: 양호]
        J -->|0.50-0.69| M[Moderate: 검증 필요]
        J -->|< 0.50| N[Poor: 환각 심각]
    
        style A fill:#e1f5ff
        style G fill:#d4edda
        style I fill:#f8d7da
        style C fill:#fff3cd
        
```

### 2️⃣ 평가 파이프라인 (Semantic vs Rule-Based)
```python
    graph LR
        A[Hallucination Detection] --> B[Layer 1: Rule-Based  
    Metric 03]
        A --> C[Layer 3: Semantic  
    Metric 19 DeepEval]
    
        B --> D[Pattern Matching  
    70-80% accuracy]
        D --> E[Unsupported claims  
    word overlap < 30%  
    Numerical inconsistency]
    
        C --> F[LLM Semantic Analysis  
    80-90% accuracy]
        F --> G[Context grounding  
    Meaning verification  
    Claim-by-claim check]
    
        E --> H[Fast, Low Cost  
    $0 per eval  
    Instant results]
        G --> I[Accurate, High Cost  
    $0.01-0.03 per eval  
    2-5 sec]
    
        H --> J[Use Case:  
    Real-time monitoring  
    High-volume filtering]
        I --> K[Use Case:  
    Critical verification  
    Production quality check]
    
        style B fill:#cfe2ff
        style C fill:#fff3cd
        style H fill:#d4edda
        style I fill:#ffc107
        
```

### 3️⃣ 비용 및 정확도 트레이드오프
```python
    graph TD
        A[Hallucination Detection Strategy] --> B{Use Case}
    
        B -->|개발/테스트| C[Rule-Based Layer 1  
    빠르고 저렴]
        B -->|프로덕션 샘플링| D[DeepEval 10% 샘플  
    비용 효율]
        B -->|크리티컬 검증| E[DeepEval 100%  
    최고 정확도]
    
        C --> F[Cost: $0  
    Accuracy: 70-80%  
    Speed: Instant]
        D --> G[Cost: ~$1-3/day for 100 tasks  
    Accuracy: 80-90% on samples  
    Speed: Mixed]
        E --> H[Cost: ~$10-30/day for 100 tasks  
    Accuracy: 80-90%  
    Speed: 2-5 sec/eval]
    
        F --> I[Recommendation]
        G --> I
        H --> I
    
        I --> J[Hybrid Approach:  
    Layer 1 for all  
    Layer 3 for high-risk]
    
        style A fill:#e1f5ff
        style I fill:#fff3cd
        style J fill:#d4edda
        
```

### 4️⃣ 임계값 및 품질 관리
```python
    graph TD
        A[Hallucination Score  
    1.0 = No Hallucination] --> B{임계값 비교}
        B -->|≥ 0.90| C[🌟 Excellent  
    Highly Grounded]
        B -->|0.70-0.89| D[✅ Good  
    Mostly Accurate]
        B -->|0.50-0.69| E[⚠️ Moderate  
    Some Hallucinations]
        B -->|< 0.50| F[❌ Poor  
    Severe Hallucinations]
    
        C --> G[권장: 현재 품질 유지  
    Context 품질 지속]
        D --> H[권장: 0.90 목표  
    Retrieval 개선]
        E --> I[권장: Context 강화  
    Ground Truth 보완]
        F --> J[권장: 즉시 개선  
    RAG 재설계 필수]
    
        style C fill:#d4edda
        style D fill:#cfe2ff
        style E fill:#fff3cd
        style F fill:#f8d7da
        
```

## 📍 구현 위치

**파일:** `agent_evaluator/integrations/metric_adapters.py`  
**클래스:** `DeepEvalAdapter`  
**메서드:** `_evaluate_hallucination()`  
**라인:** 249-271 

### 핵심 메서드

메서드 | 라인 | 설명  
---|---|---  
`__init__()` | 87-128 | DeepEval 어댑터 초기화  
`evaluate()` | 133-198 | 모든 DeepEval 메트릭 평가 (환각 포함)  
`_evaluate_hallucination()` | 249-271 | 환각 탐지 메트릭 실행  
  
## 📋 Hallucination 평가 원리

**Hallucination Detection** 은 다음 단계로 작동합니다:   
  


  1. **Context 제공** : RAG 시스템에서 검색된 문서나 참조 자료를 컨텍스트로 제공
  2. **Output 비교** : LLM이 생성한 출력(actual_output)과 컨텍스트 비교
  3. **의미적 검증** : 평가용 LLM이 출력의 각 주장(claim)이 컨텍스트에서 지지되는지 검증
  4. **Score 산출** : 0.0 ~ 1.0 범위의 점수 반환 (높을수록 환각 없음 = 좋음)

### Hallucination Score 해석

#### ⚠️ 중요: Score 방향

**DeepEval HallucinationMetric은 "환각 없음" 점수입니다**

  * **1.0 = 완벽 (환각 없음)** : 모든 내용이 컨텍스트에서 지지됨
  * **0.0 = 매우 나쁨 (전부 환각)** : 모든 내용이 컨텍스트와 무관

Hallucination Score | 등급 | 설명 | 권장 조치  
---|---|---|---  
0.9 ~ 1.0 | **Excellent** | 환각 거의 없음 | 현재 수준 유지  
0.7 ~ 0.89 | **Good** | 소수의 환각 | 경미한 개선 고려  
0.5 ~ 0.69 | **Acceptable** | 일부 환각 존재 | 프롬프트 개선 필요  
0.0 ~ 0.49 | **Critical** | 심각한 환각 | 즉각적인 수정 필요  
  
### 환각의 유형

유형 | 설명 | 예시  
---|---|---  
**추가 정보 (Addition)** | 컨텍스트에 없는 새로운 정보 생성 | 컨텍스트에 가격 없는데 "가격은 $100"이라고 답변  
**왜곡 (Distortion)** | 컨텍스트의 정보를 잘못 해석 | "2023년 출시"를 "2022년 출시"로 변경  
**모순 (Contradiction)** | 컨텍스트와 반대되는 정보 생성 | 컨텍스트: "유료 서비스" → 답변: "무료"  
**과장 (Exaggeration)** | 컨텍스트의 내용을 과대 포장 | "인기" → "세계 최고", "일부" → "모두"  
  
## ⚙️ 핵심 메서드 상세 설명

### _evaluate_hallucination() - 환각 탐지 실행

**목적** : 출력이 컨텍스트와 의미적으로 일치하는지 검증

**위치** : Lines 249-271

def _evaluate_hallucination(self, test_case) -> Dict[str, Any]: """Evaluate hallucination (contextual consistency)""" try: # 1. HallucinationMetric 생성 metric = self.HallucinationMetric( threshold=self.threshold, # 기본: 0.5 (이 이상이면 Pass) model=self.model # 평가용 LLM (예: gpt-4o-mini) ) # 2. 평가 수행 # test_case에는 context와 actual_output이 포함되어야 함 metric.measure(test_case) # 3. 결과 반환 return { 'hallucination_score': metric.score, # 0.0 ~ 1.0 (높을수록 환각 없음) 'hallucination_detected': metric.score < self.threshold, # 환각 있음? 'hallucination_passed': metric.score >= self.threshold # 테스트 통과? } except Exception as e: print(f"⚠️ Hallucination metric error: {e}") return {'hallucination_error': str(e)} 

#### ✅ 평가 로직 핵심 포인트

  1. **Context 필수** : retrieved_context가 반드시 제공되어야 평가 가능
  2. **의미적 검증** : 단순 문자열 매칭이 아닌 LLM 기반 의미 이해
  3. **이진 판정** : threshold 기준으로 Pass/Fail 자동 판단
  4. **Score 방향 주의** : 높을수록 좋음 (환각 없음)

### HybridPerformanceMonitor 통합

**목적** : 환각 탐지를 HybridPerformanceMonitor에서 자동 실행

**위치** : `agent_evaluator/core/hybrid_monitor.py` Lines 286-302

# HybridPerformanceMonitor.record_task() 내부 # DeepEval 환각 탐지 결과가 있으면 HallucinationDetector에도 자동 반영 if 'hallucination_score' in advanced_metrics: # DeepEval 점수를 환각률(hallucination_rate)로 변환 # DeepEval: 1.0 = 환각 없음 (좋음), 0.0 = 전부 환각 (나쁨) # 환각률: 0.0 = 환각 없음, 1.0 = 전부 환각 hallucination_rate = 1.0 - advanced_metrics['hallucination_score'] # HallucinationDetector에 자동 추가 hallucination_detection = { "task_id": task.task_id, "hallucination_rate": hallucination_rate, "indicators": [], # DeepEval은 상세 지표 미제공 "timestamp": task.timestamp, "source": "deepeval", # 출처 표시 "score": advanced_metrics['hallucination_score'], # 원본 보존 "detected": hallucination_rate > 0.5 } self.hallucination_detector.detections.append(hallucination_detection) 

## 🔍 데이터 수집 방법 (실전 가이드)

Hallucination Detection 메트릭을 현장에서 측정하기 위한 4가지 실전 방법을 소개합니다.

### 방법 1: RAG 시스템에서 HybridPerformanceMonitor 사용 (권장)

#### 📌 사용 시기

RAG (Retrieval-Augmented Generation) 시스템에서 검색된 문서 기반 답변의 환각 탐지

from agent_evaluator import HybridPerformanceMonitor, create_taskresult # 1. HybridPerformanceMonitor 초기화 (DeepEval 활성화) monitor = HybridPerformanceMonitor( use_deepeval=True, deepeval_model="gpt-4o-mini", use_ragas=False, use_langsmith=False ) # 2. RAG 시스템 실행 (검색 + 생성) query = "2023년 파이썬 3.11의 주요 기능은 무엇인가요?" # 벡터 DB에서 관련 문서 검색 retrieved_docs = vector_db.search(query, top_k=3) retrieved_context = [doc['content'] for doc in retrieved_docs] # 예시 컨텍스트 retrieved_context = [ "Python 3.11은 2022년 10월 출시되었으며, 이전 버전보다 10-60% 빠른 성능을 제공합니다.", "주요 기능으로는 Exception Groups, Task Groups, Tomllib 추가 등이 있습니다.", "타입 힌팅이 개선되었으며, Self 타입이 추가되었습니다." ] # LLM으로 답변 생성 llm_response = llm.generate( prompt=f"Context: {retrieved_context}\n\nQuestion: {query}" ) output_text = """ Python 3.11의 주요 기능은 다음과 같습니다: 1\. 성능 향상: 이전 버전보다 10-60% 빠른 실행 속도 2\. Exception Groups: 여러 예외를 동시에 처리 3\. Task Groups: 비동기 작업 그룹 관리 4\. Tomllib: TOML 파일 파싱 라이브러리 추가 5\. 타입 힌팅 개선: Self 타입 추가 """ # 3. 환각 탐지 평가 수행 task = create_taskresult( task_id="rag_001", task_type="QA", success=True, completion_score=1.0 ) monitor.record_task( task=task, enable_advanced_metrics=True, # DeepEval 활성화 input_text=query, output_text=output_text, retrieved_context=retrieved_context # 환각 탐지 트리거 ) # 4. 결과 확인 monitor.print_summary() # 출력 예시: # 🔬 ADVANCED METRICS # Hallucination Score: 0.950 (n=1) # Hallucination Detection: 0/1 (0.0%) # 5. 상세 결과 확인 if monitor.extended_tasks: latest_task = monitor.extended_tasks[-1] hall_score = latest_task.advanced_metrics.get('hallucination_score') hall_detected = latest_task.advanced_metrics.get('hallucination_detected') print(f"Hallucination Score: {hall_score:.3f} (1.0 = 환각 없음)") print(f"Hallucination Detected: {hall_detected}") 

**✅ Best Practice - RAG 환각 탐지:**

  * **충분한 Context** : 최소 2-3개의 검색 결과 제공 (top-k=3~5)
  * **Context 품질** : 검색 결과의 관련성이 높을수록 환각 탐지 정확도 향상
  * **명시적 지시** : 프롬프트에 "검색된 문서만 기반으로 답변" 명시
  * **Threshold 조정** : 엄격한 평가가 필요하면 threshold=0.7 사용

### 방법 2: DeepEvalAdapter 직접 사용 (고급)

#### 📌 사용 시기

HybridPerformanceMonitor 없이 환각 탐지만 독립적으로 사용하고 싶은 경우

from agent_evaluator.integrations.metric_adapters import ( DeepEvalAdapter, EvaluationContext ) # 1. DeepEvalAdapter 초기화 adapter = DeepEvalAdapter( model="gpt-4o-mini", threshold=0.7, # 환각 탐지 기준 (엄격) timeout=60 ) if not adapter.is_available(): print("⚠️ DeepEval not installed. Install with: pip install deepeval") exit(1) # 2. 평가 컨텍스트 생성 context = EvaluationContext( input_text="OpenAI의 GPT-4 출시일은?", output_text="GPT-4는 2023년 3월 14일에 출시되었습니다.", retrieved_context=[ "OpenAI는 2023년 3월 14일 GPT-4를 공개했습니다.", "GPT-4는 GPT-3.5보다 훨씬 더 정확하고 창의적입니다." ] ) # 3. 환각 탐지 수행 results = adapter.evaluate(context) # 4. 결과 확인 if 'hallucination_score' in results: score = results['hallucination_score'] detected = results['hallucination_detected'] passed = results['hallucination_passed'] print(f"Hallucination Score: {score:.3f} (1.0 = 환각 없음)") print(f"Hallucination Detected: {detected}") print(f"Test Passed: {passed}") if detected: print("⚠️ 환각이 탐지되었습니다! 출력이 컨텍스트와 일치하지 않습니다.") else: print(f"Error: {results.get('hallucination_error', 'Unknown error')}") # 5. 환각이 있는 예시 (의도적) hallucinated_context = EvaluationContext( input_text="OpenAI의 GPT-4 출시일은?", output_text="GPT-4는 2022년 12월에 출시되었으며, 500조 파라미터를 가지고 있습니다.", # 환각 retrieved_context=[ "OpenAI는 2023년 3월 14일 GPT-4를 공개했습니다." ] ) hallucinated_results = adapter.evaluate(hallucinated_context) print(f"\n환각 예시 Score: {hallucinated_results['hallucination_score']:.3f}") print(f"환각 탐지: {hallucinated_results['hallucination_detected']}") 

### 방법 3: 프로덕션 RAG 모니터링 (실시간)

#### 📌 사용 시기

대규모 프로덕션 RAG 시스템에서 실시간 환각 탐지 및 알림

import random from datetime import datetime from agent_evaluator import HybridPerformanceMonitor, create_taskresult class ProductionRAGMonitor: """프로덕션 RAG 시스템 환각 모니터링""" def __init__( self, sample_rate: float = 0.2, # 20% 샘플링 threshold: float = 0.7, # 환각 임계값 alert_threshold: float = 0.5 # 알림 임계값 ): self.monitor = HybridPerformanceMonitor( use_deepeval=True, deepeval_model="gpt-4o-mini" ) self.sample_rate = sample_rate self.threshold = threshold self.alert_threshold = alert_threshold self.total_queries = 0 self.evaluated_queries = 0 self.hallucination_alerts = [] def track_rag_interaction( self, query_id: str, user_query: str, retrieved_docs: list, generated_response: str ): """RAG 상호작용 추적 및 환각 탐지""" self.total_queries += 1 # 샘플링: 비용 절감을 위해 일부만 평가 should_evaluate = random.random() < self.sample_rate if should_evaluate: self.evaluated_queries += 1 # Context 추출 retrieved_context = [ doc['content'] if isinstance(doc, dict) else doc for doc in retrieved_docs ] # TaskResult 생성 task = create_taskresult( task_id=query_id, task_type="QA", success=True, completion_score=1.0 ) # 환각 탐지 수행 self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=user_query, output_text=generated_response, retrieved_context=retrieved_context ) # 환각 알림 확인 if self.monitor.extended_tasks: latest_task = self.monitor.extended_tasks[-1] hall_score = latest_task.advanced_metrics.get('hallucination_score') if hall_score is not None and hall_score < self.alert_threshold: # 심각한 환각 탐지 → 알림 alert = { 'query_id': query_id, 'timestamp': datetime.now().isoformat(), 'hallucination_score': hall_score, 'query': user_query[:100], 'response': generated_response[:100], 'severity': 'CRITICAL' if hall_score < 0.3 else 'WARNING' } self.hallucination_alerts.append(alert) print(f"🚨 [{alert['severity']}] Hallucination detected!") print(f" Query ID: {query_id}") print(f" Score: {hall_score:.3f} (< {self.alert_threshold})") def get_daily_report(self): """일일 환각 탐지 리포트""" print(f"\n📊 Daily Hallucination Detection Report") print(f" Date: {datetime.now().strftime('%Y-%m-%d')}") print(f" Total Queries: {self.total_queries}") print(f" Evaluated: {self.evaluated_queries} ({self.sample_rate*100:.0f}%)") print(f" Hallucination Alerts: {len(self.hallucination_alerts)}") if self.hallucination_alerts: print(f"\n🚨 Top 5 Hallucination Cases:") for i, alert in enumerate(self.hallucination_alerts[:5], 1): print(f" {i}. [{alert['severity']}] Score: {alert['hallucination_score']:.3f}") print(f" Query: {alert['query']}...") self.monitor.print_summary() # 사용 예시 rag_monitor = ProductionRAGMonitor( sample_rate=0.2, # 20% 평가 (비용 80% 절감) alert_threshold=0.5 # 0.5 미만이면 알림 ) # 프로덕션 RAG 파이프라인 for i in range(50): # 사용자 쿼리 user_query = f"사용자 질문 {i}" # RAG: 검색 retrieved_docs = vector_db.search(user_query, top_k=3) # RAG: 생성 response = llm.generate(user_query, context=retrieved_docs) # 환각 모니터링 rag_monitor.track_rag_interaction( query_id=f"query_{i}", user_query=user_query, retrieved_docs=retrieved_docs, generated_response=response ) # 일일 리포트 rag_monitor.get_daily_report() 

#### ⚠️ 프로덕션 모니터링 주의사항

  * **샘플링 비율** : 초기에는 30%로 시작하여 안정화 후 10-20%로 감소
  * **비용 관리** : DeepEval API 호출 비용 월 예산 설정
  * **알림 임계값** : 비즈니스 중요도에 따라 조정 (금융/의료: 0.8, 일반: 0.5)
  * **False Positive** : 일부 정상 케이스도 환각으로 오탐지 가능
  * **Context 품질** : 검색 품질이 낮으면 환각 탐지 정확도 하락

### 방법 4: Layer 1 Native 환각 탐지와 비교

#### 📌 사용 시기

Layer 1 Native 환각 탐지와 Layer 3 DeepEval 환각 탐지를 함께 사용하여 정확도 향상

from agent_evaluator import HybridPerformanceMonitor, create_taskresult # Layer 1 (Native) + Layer 3 (DeepEval) 통합 환각 탐지 monitor = HybridPerformanceMonitor( use_deepeval=True, enable_hallucination_detection=True # Layer 1도 활성화 ) # RAG 데이터 query = "파이썬 3.11의 주요 기능은?" retrieved_context = [ "Python 3.11은 성능이 10-60% 향상되었습니다.", "Exception Groups와 Task Groups가 추가되었습니다." ] response = "Python 3.11의 주요 기능은 성능 향상과 Exception Groups입니다." task = create_taskresult( task_id="compare_001", task_type="QA", success=True, completion_score=1.0 ) # 통합 평가 (Layer 1 + Layer 3) monitor.record_task( task=task, enable_advanced_metrics=True, # Layer 3 DeepEval input_text=query, output_text=response, retrieved_context=retrieved_context, # 둘 다 트리거 context='\n'.join(retrieved_context), # Layer 1용 response=response # Layer 1용 ) # 결과 비교 if monitor.extended_tasks: latest_task = monitor.extended_tasks[-1] # Layer 3 DeepEval 결과 deepeval_score = latest_task.advanced_metrics.get('hallucination_score') # Layer 1 Native 결과 if monitor.hallucination_detector.detections: native_detection = monitor.hallucination_detector.detections[-1] native_rate = native_detection['hallucination_rate'] print(f"Layer 1 Native Hallucination Rate: {native_rate:.3f} (낮을수록 좋음)") print(f"Layer 3 DeepEval Hallucination Score: {deepeval_score:.3f} (높을수록 좋음)") # 통합 판정 if deepeval_score < 0.5: print("⚠️ DeepEval: 환각 탐지 (심각)") elif native_rate > 0.3: print("⚠️ Native: 환각 가능성 (주의)") else: print("✅ 두 레이어 모두 환각 없음 (안전)") # 통합 리포트 monitor.print_summary() 

#### 📊 Layer 1 vs Layer 3 환각 탐지 비교

구분 | Layer 1 Native | Layer 3 DeepEval  
---|---|---  
**방식** | 키워드/패턴 기반 | LLM 의미 이해 기반  
**속도** | 매우 빠름 (< 10ms) | 느림 (1-3초)  
**비용** | 무료 | API 비용 발생  
**정확도** | 중간 (단순 패턴) | 높음 (의미적 검증)  
**권장 용도** | 실시간 1차 필터링 | 중요 작업 정밀 검증  
  
## 💡 Best Practices

#### 1\. Context 제공 가이드라인

  * **충분한 양** : 최소 2-3개의 관련 문서 제공
  * **높은 품질** : 검색 결과의 관련성 점수 0.7 이상 필터링
  * **다양성** : 동일 정보 반복보다 다양한 측면 포함
  * **최신성** : 시간에 민감한 정보는 최신 문서 우선

#### 2\. Threshold 설정 전략

  * **금융/의료/법률** : threshold=0.8 (엄격)
  * **일반 챗봇** : threshold=0.6 (보통)
  * **창의적 작업** : threshold=0.5 (관대)
  * **동적 조정** : 중요 질의는 임계값 상향

#### 3\. 환각 감소 전략

  * **프롬프트 명시** : "검색된 문서만 기반으로 답변하세요" 추가
  * **Temperature 낮추기** : 0.3 이하로 설정하여 창의성 제한
  * **인용 요구** : 답변에 출처 인용 강제
  * **검색 품질 향상** : Re-ranking, 하이브리드 검색 적용

#### ⚠️ 주의사항

  * **False Positive** : 패러프레이징을 환각으로 오탐지 가능
  * **Context 의존성** : Context 품질이 낮으면 정확도 하락
  * **LLM 편향** : 평가용 LLM의 한계 상속
  * **비용 누적** : 대량 평가 시 API 비용 급증
  * **지연 시간** : 실시간 응답 필요 시 비동기 처리 고려

## 📈 활용 예시

### 예시 1: 의료 Q&A 챗봇 환각 탐지

# 의료 정보 챗봇의 환각 탐지 (높은 정확도 필요) monitor = HybridPerformanceMonitor( use_deepeval=True, deepeval_model="gpt-4o" # 의료: 정확도 최우선 ) medical_query = "당뇨병 환자의 식단 관리 방법은?" medical_docs = [ "당뇨병 환자는 탄수화물 섭취를 제한하고 혈당 지수가 낮은 음식을 선택해야 합니다.", "규칙적인 식사 시간을 유지하고, 하루 3끼를 균등하게 나누어 먹는 것이 중요합니다." ] response = "당뇨병 환자는 저탄수화물 식단과 규칙적인 식사가 중요합니다." task = create_taskresult("medical_001", "QA", True, 1.0) monitor.record_task( task, True, medical_query, response, retrieved_context=medical_docs ) # 엄격한 검증 hall_score = monitor.extended_tasks[-1].advanced_metrics['hallucination_score'] if hall_score < 0.8: # 의료는 0.8 이상 요구 print("⚠️ 의료 정보 검증 실패 - 인간 검토 필요") 

### 예시 2: 제품 매뉴얼 챗봇

# 제품 매뉴얼 기반 챗봇 (환각 탐지로 잘못된 안내 방지) monitor = HybridPerformanceMonitor(use_deepeval=True) manual_context = [ "제품 A는 220V 전압에서 작동합니다.", "사용 전 반드시 안전 가이드를 읽으세요." ] # 잘못된 답변 (환각) wrong_response = "제품 A는 110V에서 작동하며 안전 가이드는 선택 사항입니다." task = create_taskresult("manual_001", "QA", True, 1.0) monitor.record_task( task, True, "제품 A 사용 방법?", wrong_response, retrieved_context=manual_context ) hall_score = monitor.extended_tasks[-1].advanced_metrics['hallucination_score'] print(f"Hallucination Score: {hall_score:.3f}") # 출력: 0.2 미만 (환각 심각)

## 🔗 관련 메트릭

  * **Hallucination Detection (Layer 1)** : 빠른 키워드 기반 환각 탐지
  * **G-Eval (Layer 3)** : 사용자 정의 품질 평가
  * **Ragas Faithfulness (Layer 3)** : RAG 전용 충실도 평가
  * **Answer Relevancy (Layer 3)** : 답변 관련성 평가

## 📚 참고 자료

  * **DeepEval Documentation** : <https://docs.confident-ai.com/>
  * **Hallucination Research** : "Survey of Hallucination in Natural Language Generation"
  * **Agent Evaluator GitHub** : [GitHub Repository](<https://github.com/your-repo/agent-evaluator>)
