# 📊 Context Precision

Ragas RAG 평가 메트릭 - 검색 정밀도 (Retrieval Precision)

Agent Evaluator v0.5.1

Ragas Layer 3 RAG Evaluation Retrieval Quality

## 📋 개요

**Context Precision** 은 Ragas 라이브러리에서 제공하는 RAG(Retrieval-Augmented Generation) 시스템 전용 평가 메트릭으로, **검색된 컨텍스트들이 질문과 얼마나 관련성이 높은지** 를 측정합니다.

  


이 메트릭은 검색된 컨텍스트 각각이 질문에 유용한지(relevant) 평가하고, 관련성 높은 컨텍스트가 상위 순위에 배치되었는지 확인합니다. **검색 시스템(Retrieval System)의 품질을 평가** 하는 핵심 메트릭으로, Vector DB나 검색 알고리즘의 성능을 측정합니다.

### 🎯 비즈니스 임팩트

  * **검색 품질 개선** : 무관한 컨텍스트 제거로 LLM 답변 품질 향상
  * **비용 절감** : 불필요한 컨텍스트 전송으로 인한 토큰 비용 낭비 방지
  * **응답 속도 향상** : 관련성 높은 컨텍스트만 전송하여 latency 감소
  * **사용자 만족도** : 정확한 정보 제공으로 신뢰도 증가

## 📊 다이어그램 시각화

### 1️⃣ 핵심 개념 및 정밀도 평가 (Ragas)
```python
    graph TD
        A[Question + Contexts Ranked List + Ground Truth] --> B[ContextPrecision Metric  
    Ragas Framework]
        B --> C[LLM Judge  
    gpt-4o-mini]
    
        C --> D[Ranking Quality Analysis]
        D --> E[Top-K Context Evaluation]
    
        E --> F{각 Context}
        F -->|관련성 높음| G[Relevant Context  
    상위 랭크]
        F -->|관련성 낮음| H[Irrelevant Context  
    하위 랭크]
    
        G --> I{실제 위치}
        H --> I
    
        I -->|관련 문맥이 상위| J[High Precision  
    Good Retrieval]
        I -->|관련 문맥이 하위| K[Low Precision  
    Poor Ranking]
    
        J --> L[Context Precision Score  
    = relevant@top-k / k]
    
        K --> L
    
        L --> M{Quality Level}
        M -->|≥ 0.90| N[Excellent: 정밀한 Retrieval]
        M -->|0.75-0.89| O[Good: 양호한 Ranking]
        M -->|0.60-0.74| P[Moderate: Ranking 개선 필요]
        M -->|< 0.60| Q[Poor: Retrieval 문제]
    
        style A fill:#e1f5ff
        style L fill:#fff3cd
        style N fill:#d4edda
        style Q fill:#f8d7da
        
```

### 2️⃣ 평가 파이프라인 (Retrieval Quality)
```python
    sequenceDiagram
        participant RAG as RAG Retrieval
        participant Adapter as RagasAdapter
        participant Ragas as Ragas Framework
        participant LLM as gpt-4o-mini
    
        RAG->>Adapter: evaluate(question, contexts=[c1,c2,c3,...], ground_truth)
        Note over RAG: contexts는 relevance score  
    순서로 정렬된 리스트
    
        Adapter->>Adapter: Create Ragas Dataset  
    SingleTurnSample
    
        Adapter->>Ragas: evaluate(dataset, metrics=[context_precision])
    
        Ragas->>LLM: Assess relevance of each context
        Note over LLM: Top-K contexts 중  
    실제 관련 문맥 비율
    
        LLM-->>Ragas: Relevance scores per context
    
        Ragas->>Ragas: Calculate precision@k  
    = relevant_in_top_k / k
    
        Ragas-->>Adapter: context_precision score (0-1)
    
        Adapter-->>RAG: {'ragas_context_precision': 0.85}
        
```

### 3️⃣ Retrieval 최적화 전략
```python
    graph TD
        A[Context Precision 개선] --> B[전략 1: Reranking]
        A --> C[전략 2: Hybrid Search]
        A --> D[전략 3: Embedding 개선]
    
        B --> E[Cohere Rerank  
    BGE Reranker  
    Cross-Encoder]
        E --> F[Before: Precision 0.65  
    After: Precision 0.85+  
    Cost: +$0.001/query]
    
        C --> G[Dense + Sparse  
    Vector + BM25  
    Weighted Fusion]
        G --> H[Before: Precision 0.70  
    After: Precision 0.80+  
    Cost: 계산 증가 20%]
    
        D --> I[Domain-Specific  
    Fine-tuned Embeddings  
    Instruction-tuned]
        I --> J[Before: Precision 0.60  
    After: Precision 0.75+  
    Cost: Training 필요]
    
        F --> K[ROI Analysis]
        H --> K
        J --> K
    
        K --> L[Reranking: 최고 효과/비용  
    권장: Cohere/BGE]
    
        style A fill:#e1f5ff
        style K fill:#fff3cd
        style L fill:#d4edda
        
```

### 4️⃣ 임계값 및 Retrieval 최적화
```python
    graph TD
        A[Context Precision Score] --> B{임계값 비교}
        B -->|≥ 0.90| C[🌟 Excellent  
    Optimal Ranking]
        B -->|0.75-0.89| D[✅ Good  
    Good Retrieval]
        B -->|0.60-0.74| E[⚠️ Moderate  
    Ranking Issues]
        B -->|< 0.60| F[❌ Poor  
    Retrieval Failure]
    
        C --> G[권장: 현재 시스템 유지  
    Reranker 효과적]
        D --> H[권장: Reranker 도입  
    0.90 목표]
        E --> I[권장: Hybrid Search 고려  
    Top-K 조정]
        F --> J[권장: 즉시 개선  
    Embedding 재학습]
    
        style C fill:#d4edda
        style D fill:#cfe2ff
        style E fill:#fff3cd
        style F fill:#f8d7da
        
```

## 🔍 구현 위치

항목 | 내용  
---|---  
**파일** | `agent_evaluator/integrations/metric_adapters.py`  
**클래스** | `RagasAdapter`  
**메서드** | `evaluate()`  
**라인 번호** | Lines 420-534 (전체 평가 로직)  
Lines 451, 458 (context_precision 메트릭 선택)  
**외부 라이브러리** | Ragas (`ragas.metrics.context_precision`)  
**반환 키** | `ragas_context_precision`  
  
## ⚙️ 평가 원리

### Step 1: 컨텍스트 관련성 평가

LLM을 사용하여 각 검색된 컨텍스트가 질문에 유용한지(relevant) 판단합니다.

Question: "파이썬 3.11의 성능 개선 사항은?" Retrieved Contexts: [1] "Python 3.11 is 10-60% faster than 3.10..." ✅ Relevant [2] "파이썬은 1991년 Guido van Rossum이 만들었습니다." ❌ Not Relevant [3] "Performance improvements in 3.11 include faster interpreter..." ✅ Relevant [4] "Python 2.7 reached end of life in 2020." ❌ Not Relevant

### Step 2: Precision@K 계산

상위 K개 컨텍스트 중 관련성 있는 비율을 계산합니다.

Precision@1 = 1/1 = 1.00 (첫 번째가 relevant) Precision@2 = 1/2 = 0.50 (두 번째가 not relevant) Precision@3 = 2/3 = 0.67 (세 번째가 relevant) Precision@4 = 2/4 = 0.50 (네 번째가 not relevant)

### Step 3: Average Precision 계산

Context Precision = Σ(Precision@K × Relevance@K) / Total Relevant = (1.00×1 + 0.50×0 + 0.67×1 + 0.50×0) / 2 = (1.00 + 0.67) / 2 = 0.835 (높은 정밀도)

#### 📊 Score 해석 가이드

  * 0.9 ~ 1.0: 완벽한 검색 정밀도 (Excellent)
  * 0.7 ~ 0.89: 양호한 검색 품질 (Good)
  * 0.5 ~ 0.69: 일부 무관한 컨텍스트 포함 (Acceptable with caution)
  * < 0.5: 검색 품질 낮음 (Poor - 수정 필요)

**⚠️ 방향 주의:** 높을수록 좋음 (1.0 = 모든 컨텍스트가 관련성 있음)

**🔍 평가 대상:** 생성 품질이 아닌 **검색(Retrieval) 품질** 을 평가함

## 🔧 메서드 상세

### RagasAdapter.evaluate() - Context Precision 평가

**소스 코드** (metric_adapters.py Lines 420-534):

def evaluate(self, context: EvaluationContext) -> Dict[str, Any]: """Evaluate using Ragas RAG metrics""" if not self._available: return {} # Only evaluate RAG tasks with retrieved context if not context.retrieved_context: return {} results = {} try: from datasets import Dataset # Prepare data in Ragas format data = { 'question': [context.input_text], 'answer': [context.output_text], 'contexts': [context.retrieved_context] } # Select metrics based on available data if context.expected_output: data['ground_truth'] = [context.expected_output] metrics = [ self.faithfulness, self.answer_relevancy, self.context_recall, self.context_precision # ← Context Precision 메트릭 ] else: # Skip context_recall when no ground_truth available metrics = [ self.faithfulness, self.answer_relevancy, self.context_precision # ← Context Precision 메트릭 (항상 포함) ] dataset = Dataset.from_dict(data) # Set LLM for all metrics for metric in metrics: if hasattr(metric, 'llm'): metric.llm = self.llm eval_result = self.evaluate_fn( dataset, metrics=metrics ) # Extract Context Precision score import math for metric_name in ['faithfulness', 'answer_relevancy', 'context_recall', 'context_precision']: try: value_list = eval_result[metric_name] if isinstance(value_list, (list, tuple)) and len(value_list) > 0: value = value_list[0] else: value = value_list if value is not None and isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)): results[f'ragas_{metric_name}'] = float(value) except (KeyError, IndexError, TypeError, AttributeError, ValueError): continue # Calculate overall Ragas score numeric_metrics = {k: v for k, v in results.items() if isinstance(v, (int, float)) and not isinstance(v, bool)} if numeric_metrics: results['ragas_overall_score'] = sum(numeric_metrics.values()) / len(numeric_metrics) except Exception as e: import traceback print(f"⚠️ Ragas unexpected error: {e}") results['ragas_error'] = f"Unexpected error: {str(e)}" return results

#### 🔑 핵심 포인트

  * **자동 트리거** : `retrieved_context`가 제공되면 Context Precision이 자동 평가됨
  * **Ground Truth 불필요** : `expected_output` 없이도 평가 가능 (contexts vs question 비교)
  * **LLM 기반** : GPT-4o-mini 또는 GPT-4o를 사용하여 컨텍스트 관련성 판단
  * **검색 품질 평가** : 생성 품질이 아닌 검색 시스템의 정밀도를 측정
  * **Overall Score 포함** : 다른 Ragas 메트릭과 평균화되어 `ragas_overall_score`에 반영

## 📊 데이터 수집 방법

### 방법 1: HybridPerformanceMonitor 자동 평가 (권장)

RAG 시스템에서 `retrieved_context`만 제공하면 Context Precision이 자동으로 평가됩니다.

from agent_evaluator import HybridPerformanceMonitor, create_taskresult # 1. Monitor 초기화 (Ragas 활성화) monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o-mini" # 비용 절감 ) # 2. RAG 시스템 실행 user_query = "Rust 언어의 메모리 안전성은 어떻게 보장되나요?" # Vector DB에서 컨텍스트 검색 retrieved_docs = vector_db.search(user_query, top_k=5) retrieved_context = [doc.content for doc in retrieved_docs] # LLM 답변 생성 llm_response = llm.generate( prompt=f"Question: {user_query}\n\nContext: {retrieved_context}", context=retrieved_context ) # 3. Task 기록 (Context Precision 자동 평가) task = create_taskresult( task_id="rag_query_003", task_type="qa", success=True, completion_score=1.0 ) monitor.record_task( task=task, enable_advanced_metrics=True, # Ragas 활성화 input_text=user_query, output_text=llm_response, retrieved_context=retrieved_context # ← Context Precision 트리거 ) # 4. Context Precision Score 확인 latest_task = monitor.extended_tasks[-1] context_precision = latest_task.advanced_metrics.get('ragas_context_precision') overall = latest_task.advanced_metrics.get('ragas_overall_score') print(f"Context Precision Score: {context_precision:.3f}") print(f"Ragas Overall Score: {overall:.3f}") if context_precision < 0.7: print(f"⚠️ 경고: 낮은 Context Precision 감지 - 검색 품질 개선 필요") 

### 방법 2: RagasAdapter 독립 사용 (고급)

Ragas 메트릭만 단독으로 평가하고 싶을 때 사용합니다.

from agent_evaluator.integrations.metric_adapters import ( RagasAdapter, EvaluationContext ) # 1. Adapter 초기화 ragas = RagasAdapter(llm_model="gpt-4o-mini") # 2. Evaluation Context 생성 context = EvaluationContext( input_text="Kubernetes에서 Pod와 Container의 차이는?", output_text="Pod는 Kubernetes에서 배포 가능한 최소 단위로, 하나 이상의 Container를 포함합니다. Container는 실제 애플리케이션이 실행되는 격리된 환경입니다.", retrieved_context=[ "A Pod is the smallest deployable unit in Kubernetes and can contain one or more containers.", "Containers provide isolated runtime environments for applications.", "Kubernetes was originally developed by Google.", # Less relevant "Pods share network and storage resources." ] ) # 3. Ragas 평가 실행 results = ragas.evaluate(context) # 4. Context Precision 결과 확인 print(f"Context Precision: {results['ragas_context_precision']:.3f}") print(f"Faithfulness: {results['ragas_faithfulness']:.3f}") print(f"Answer Relevancy: {results['ragas_answer_relevancy']:.3f}") print(f"Overall Score: {results['ragas_overall_score']:.3f}") print(f"Quality Level: {results['ragas_quality']}") 

### 방법 3: 검색 시스템 A/B 테스트 (프로덕션)

서로 다른 검색 알고리즘의 Context Precision을 비교합니다.

from agent_evaluator import HybridPerformanceMonitor, create_taskresult from typing import List, Dict class RetrievalSystemABTest: def __init__(self, test_queries: List[str]): """ 검색 시스템 A/B 테스트 Args: test_queries: 테스트용 질문 리스트 """ self.test_queries = test_queries self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o" # A/B 테스트에는 고정밀 모델 사용 ) def test_retrieval_system(self, system_name: str, retrieval_system) -> Dict: """특정 검색 시스템의 Context Precision 측정""" precision_scores = [] for i, query in enumerate(self.test_queries): # 검색 시스템으로 컨텍스트 검색 retrieved = retrieval_system.retrieve(query) # LLM 답변 생성 (일관성 유지를 위해 동일 프롬프트 사용) answer = self.llm.generate(query, retrieved) # Context Precision 평가 task = create_taskresult(f"{system_name}_q{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved ) latest = self.monitor.extended_tasks[-1] precision = latest.advanced_metrics.get('ragas_context_precision', 0.0) precision_scores.append(precision) return { 'system_name': system_name, 'avg_context_precision': sum(precision_scores) / len(precision_scores), 'min_context_precision': min(precision_scores), 'scores': precision_scores } def compare_systems(self, retrieval_systems: Dict) -> Dict: """여러 검색 시스템 비교""" results = [] for system_name, system in retrieval_systems.items(): print(f"\n테스트 중: {system_name}...") result = self.test_retrieval_system(system_name, system) results.append(result) print(f" 평균 Context Precision: {result['avg_context_precision']:.3f}") # 최고 성능 검색 시스템 선택 best = max(results, key=lambda x: x['avg_context_precision']) return { 'all_results': results, 'best_system': best['system_name'], 'best_avg_precision': best['avg_context_precision'] } # 사용 예시 test_queries = [ "딥러닝 모델의 학습 속도를 높이는 방법은?", "Kubernetes Pod와 Container의 차이는?", "파이썬 3.11의 주요 기능은?", # ... 더 많은 테스트 쿼리 ] ab_test = RetrievalSystemABTest(test_queries) retrieval_systems = { "cosine_similarity": CosineSimilarityRetrieval(top_k=5), "hybrid_search": HybridSearchRetrieval(top_k=5, alpha=0.5), "reranked": RerankedRetrieval(top_k=5, reranker="cohere") } comparison = ab_test.compare_systems(retrieval_systems) print(f"\n🏆 최고 성능 검색 시스템: {comparison['best_system']}") print(f" 평균 Context Precision: {comparison['best_avg_precision']:.3f}") 

### 방법 4: 실시간 검색 품질 모니터링

프로덕션 RAG 시스템의 검색 품질을 지속적으로 모니터링합니다.

import random from agent_evaluator import HybridPerformanceMonitor, create_taskresult from datetime import datetime class RetrievalQualityMonitor: def __init__(self, sample_rate: float = 0.15, precision_threshold: float = 0.7): """ 검색 품질 모니터 Args: sample_rate: 평가 샘플링 비율 (15% = 0.15) precision_threshold: Context Precision 경고 임계값 """ self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o-mini" ) self.sample_rate = sample_rate self.threshold = precision_threshold self.low_precision_incidents = [] def track_retrieval(self, query_id: str, query: str, retrieved_contexts: list, answer: str) -> dict: """검색 추적 및 샘플링 평가""" # 샘플링 결정 (15% 확률로 Ragas 평가) should_evaluate = random.random() < self.sample_rate if should_evaluate: task = create_taskresult(query_id, "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved_contexts ) # Context Precision Score 확인 latest = self.monitor.extended_tasks[-1] context_precision = latest.advanced_metrics.get('ragas_context_precision', 1.0) # 낮은 Context Precision 감지 시 알림 if context_precision < self.threshold: self._log_low_precision(query_id, context_precision, query, retrieved_contexts) return { 'evaluated': True, 'context_precision': context_precision, 'alert_triggered': context_precision < self.threshold } else: return {'evaluated': False} def _log_low_precision(self, query_id: str, score: float, query: str, contexts: list): """낮은 Context Precision 로깅""" incident = { 'timestamp': datetime.now().isoformat(), 'query_id': query_id, 'context_precision': score, 'query': query, 'num_contexts': len(contexts) } self.low_precision_incidents.append(incident) print(f""" 🚨 낮은 Context Precision 감지! Query ID: {query_id} Context Precision Score: {score:.3f} (Threshold: {self.threshold}) Query: {query} Retrieved Contexts: {len(contexts)}개 권장 조치: 1\. Embedding 모델 개선 (ada-002 → text-embedding-3-large) 2\. Hybrid search 도입 (Semantic + Keyword) 3\. Re-ranking 모델 추가 (Cohere Rerank, Cross-Encoder) 4\. top_k 파라미터 조정 5\. 문서 청킹 전략 개선 """) def generate_weekly_report(self) -> dict: """주간 검색 품질 리포트""" tasks = self.monitor.extended_tasks precision_scores = [ t.advanced_metrics.get('ragas_context_precision') for t in tasks if 'ragas_context_precision' in t.advanced_metrics ] if not precision_scores: return {'error': 'No data available'} return { 'week': datetime.now().strftime('%Y-W%U'), 'total_evaluated': len(precision_scores), 'avg_context_precision': sum(precision_scores) / len(precision_scores), 'min_context_precision': min(precision_scores), 'max_context_precision': max(precision_scores), 'low_precision_count': len(self.low_precision_incidents), 'low_precision_rate': len(self.low_precision_incidents) / len(precision_scores), 'incidents': self.low_precision_incidents } # 사용 예시 monitor = RetrievalQualityMonitor( sample_rate=0.15, # 15% 샘플링 → 비용 85% 절감 precision_threshold=0.7 ) # RAG 쿼리마다 호출 result = monitor.track_retrieval( query_id="rag_001", query="Kubernetes에서 StatefulSet과 Deployment의 차이는?", retrieved_contexts=[ "StatefulSet provides unique network identities for pods...", "Deployment is used for stateless applications...", "Pods are the smallest deployable units..." ], answer="StatefulSet은 상태를 유지하는 애플리케이션에 사용되며..." ) # 주간 리포트 생성 weekly = monitor.generate_weekly_report() print(f"주간 평균 Context Precision: {weekly['avg_context_precision']:.3f}") print(f"낮은 Context Precision 비율: {weekly['low_precision_rate']*100:.1f}%") 

## 💡 Best Practices

### 1\. Threshold 설정 전략

도메인 | 권장 Threshold | 이유  
---|---|---  
의료, 법률, 금융 | **≥ 0.9** | 고위험 분야, 무관한 컨텍스트로 인한 오답 방지  
고객 지원, FAQ | **≥ 0.8** | 정확한 답변을 위한 높은 검색 정밀도 필요  
기술 문서, 튜토리얼 | **≥ 0.7** | 다양한 관점의 정보 허용  
일반 대화, 브레인스토밍 | **≥ 0.6** | 폭넓은 정보 제공 가능  
  
### 2\. Context Precision 개선 방법

  1. **Embedding 모델 업그레이드**
     * OpenAI ada-002 → text-embedding-3-large
     * 다국어 지원: multilingual-e5-large
     * 도메인 특화: fine-tuned embeddings
  2. **Hybrid Search 도입**
     * Semantic search + Keyword search 결합
     * BM25 + Vector search (alpha 가중치 조정)
     * 각 방법의 장점 활용 (의미적 유사성 + 정확한 키워드 매칭)
  3. **Re-ranking 추가**
     * Cohere Rerank API 사용
     * Cross-Encoder 모델 (BERT 기반)
     * 초기 검색 후 관련성 재평가
  4. **문서 청킹 전략 최적화**
     * Chunk 크기 조정 (256, 512, 1024 tokens)
     * Overlap 설정 (문맥 연결성 유지)
     * Semantic chunking (문장/단락 경계 기준)
  5. **top_k 파라미터 조정**
     * 너무 많으면: 무관한 컨텍스트 포함 (Precision 하락)
     * 너무 적으면: 중요한 정보 누락 (Recall 하락)
     * 최적값 실험: 3-10개 사이에서 A/B 테스트

### ⚠️ 주의사항

  * **컨텍스트 필수** : `retrieved_context`가 없으면 Context Precision을 평가할 수 없음
  * **LLM 의존성** : GPT 모델 API 비용 및 latency 고려 필요
  * **검색 품질에만 집중** : Context Precision은 생성 품질이 아닌 검색 품질만 평가함
  * **언어 제한** : 영어 최적화, 다른 언어는 성능이 낮을 수 있음
  * **질문 품질** : 모호한 질문은 낮은 점수를 유발 (질문 명확화 필요)

### 3\. 비용 최적화 전략

  * **샘플링 사용** : 프로덕션에서 10-20% 샘플링으로 비용 80-90% 절감
  * **모델 선택** : 일반 평가는 gpt-4o-mini (저렴), 중요 평가는 gpt-4o (고정밀)
  * **배치 평가** : 실시간 대신 야간 배치로 평가하여 부하 분산
  * **캐싱** : 유사한 질문의 재평가 방지

## 🎯 활용 예시

### 예시 1: 검색 알고리즘 최적화

from agent_evaluator import HybridPerformanceMonitor, create_taskresult class RetrievalOptimizer: def __init__(self): self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o" ) def optimize_top_k(self, test_queries: list, retrieval_system) -> dict: """top_k 파라미터 최적화""" results = {} for top_k in [3, 5, 7, 10]: precision_scores = [] for i, query in enumerate(test_queries): # 다양한 top_k로 검색 retrieved = retrieval_system.retrieve(query, top_k=top_k) answer = self.llm.generate(query, retrieved) # Context Precision 평가 task = create_taskresult(f"topk_{top_k}_q{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved ) latest = self.monitor.extended_tasks[-1] precision = latest.advanced_metrics.get('ragas_context_precision', 0.0) precision_scores.append(precision) results[top_k] = sum(precision_scores) / len(precision_scores) print(f"top_k={top_k}: Context Precision = {results[top_k]:.3f}") # 최적 top_k 선택 best_top_k = max(results, key=results.get) print(f"\n🏆 최적 top_k: {best_top_k} (Precision: {results[best_top_k]:.3f})") return {'best_top_k': best_top_k, 'all_results': results} # 사용 optimizer = RetrievalOptimizer() test_queries = ["query1", "query2", "query3"] result = optimizer.optimize_top_k(test_queries, my_retrieval_system) 

### 예시 2: Vector DB 성능 비교

from agent_evaluator import HybridPerformanceMonitor, create_taskresult class VectorDBBenchmark: def __init__(self, test_queries: list): self.test_queries = test_queries self.monitor = HybridPerformanceMonitor(use_ragas=True) def benchmark_vector_db(self, db_name: str, vector_db) -> dict: """Vector DB의 Context Precision 측정""" precision_scores = [] for i, query in enumerate(self.test_queries): retrieved = vector_db.search(query, top_k=5) answer = self.llm.generate(query, retrieved) task = create_taskresult(f"{db_name}_q{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved ) latest = self.monitor.extended_tasks[-1] precision = latest.advanced_metrics.get('ragas_context_precision', 0.0) precision_scores.append(precision) return { 'db_name': db_name, 'avg_precision': sum(precision_scores) / len(precision_scores), 'scores': precision_scores } def compare_vector_dbs(self, vector_dbs: dict) -> dict: """여러 Vector DB 비교""" results = [] for db_name, db in vector_dbs.items(): print(f"\n테스트 중: {db_name}...") result = self.benchmark_vector_db(db_name, db) results.append(result) print(f" 평균 Context Precision: {result['avg_precision']:.3f}") best = max(results, key=lambda x: x['avg_precision']) return {'all_results': results, 'best_db': best['db_name']} # 사용 benchmark = VectorDBBenchmark(test_queries) vector_dbs = { 'pinecone': pinecone_client, 'weaviate': weaviate_client, 'qdrant': qdrant_client } comparison = benchmark.compare_vector_dbs(vector_dbs) print(f"\n🏆 최고 성능 Vector DB: {comparison['best_db']}") 

### 예시 3: 실시간 검색 품질 대시보드

from agent_evaluator import HybridPerformanceMonitor, create_taskresult from collections import deque import time class ContextPrecisionDashboard: """실시간 Context Precision 모니터링""" def __init__(self, window_size: int = 100): self.monitor = HybridPerformanceMonitor(use_ragas=True) self.recent_scores = deque(maxlen=window_size) self.alert_count = 0 def track_retrieval(self, query_id: str, query: str, answer: str, contexts: list): """검색 추적 및 실시간 메트릭 업데이트""" task = create_taskresult(query_id, "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=contexts ) latest = self.monitor.extended_tasks[-1] context_precision = latest.advanced_metrics.get('ragas_context_precision', 0.0) self.recent_scores.append({ 'timestamp': time.time(), 'query_id': query_id, 'context_precision': context_precision }) if context_precision < 0.6: self.alert_count += 1 def print_dashboard(self): """콘솔 Dashboard 출력""" if not self.recent_scores: return scores = [s['context_precision'] for s in self.recent_scores] avg = sum(scores) / len(scores) last_5_avg = sum(scores[-5:]) / min(5, len(scores)) print(f""" ╔══════════════════════════════════════════════════════════╗ ║ Context Precision Live Dashboard ║ ╠══════════════════════════════════════════════════════════╣ ║ Current Avg: {avg:.3f} ║ ║ Last 5 Avg: {last_5_avg:.3f} ║ ║ Min/Max: {min(scores):.3f} / {max(scores):.3f} ║ ║ Alert Count: {self.alert_count} ║ ║ Total Queries: {len(self.recent_scores)} ║ ║ Low Precision: {sum(1 for s in scores if s < 0.6) / len(scores)*100:.1f}% ║ ╚══════════════════════════════════════════════════════════╝ """) # 사용 dashboard = ContextPrecisionDashboard(window_size=100) import threading def dashboard_loop(): while True: dashboard.print_dashboard() time.sleep(10) threading.Thread(target=dashboard_loop, daemon=True).start() 

## 🔗 관련 메트릭

메트릭 | 관계 | 설명  
---|---|---  
**Context Recall** | 보완 관계 | 검색된 컨텍스트의 완전성 평가 (Recall)  
Context Precision은 정밀도 평가 (Precision)  
**Faithfulness** | 보완 관계 | 생성된 답변의 사실성 평가 (생성 품질)  
Context Precision은 검색 품질 평가  
**Answer Relevancy (Ragas)** | 보완 관계 | 답변과 질문의 관련성 평가  
Context Precision은 컨텍스트와 질문의 관련성 평가  
**Contextual Relevancy (DeepEval)** | 유사 (다른 구현) | DeepEval의 컨텍스트 관련성 메트릭  
동일 목적이지만 평가 방법 상이  
  
#### 💡 메트릭 조합 전략

**검색 시스템 품질 보장** \- Precision과 Recall 함께 평가:

  * **Context Precision** (높을수록 좋음): 검색된 컨텍스트의 정밀도
  * **Context Recall** (높을수록 좋음): 검색된 컨텍스트의 완전성

→ 둘 다 0.8 이상이면 **고품질 검색 시스템**

## 📚 참고 자료

  * [Ragas Context Precision 공식 문서](<https://docs.ragas.io/en/latest/concepts/metrics/context_precision.html>)
  * [RAGAS: Automated Evaluation of RAG (논문)](<https://arxiv.org/abs/2309.15217>)
  * [Agent Evaluator RAG 평가 예시](<../examples/rag_evaluation.py>)
  * [Faithfulness (Ragas) 문서](<./22_FAITHFULNESS.html>)
  * [Answer Relevancy (Ragas) 문서](<./23_ANSWER_RELEVANCY_RAGAS.html>)
  * [Context Recall 문서](<./25_CONTEXT_RECALL.html>)

**Agent Evaluator v0.5.1** \- Layer 3 Ragas Metrics

Context Precision: RAG 검색 시스템의 정밀도 평가

Developed by Agent Evaluator Team | [GitHub](<https://github.com/your-repo/agent-evaluator>)
