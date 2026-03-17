# 📊 Context Recall

Ragas RAG 평가 메트릭 - 검색 재현율 (Retrieval Recall)

Agent Evaluator v0.5.2

Ragas Layer 3 RAG Evaluation Retrieval Quality Requires Ground Truth

## 📋 개요

**Context Recall** 은 Ragas 라이브러리에서 제공하는 RAG(Retrieval-Augmented Generation) 시스템 전용 평가 메트릭으로, **검색된 컨텍스트들이 정답(Ground Truth)을 생성하는 데 필요한 정보를 얼마나 완전하게 포함하고 있는지** 를 측정합니다.

  


이 메트릭은 정답의 각 주장(Claim)을 추출한 후, 검색된 컨텍스트에서 해당 주장을 뒷받침할 수 있는 정보가 있는지 검증합니다. **검색 시스템(Retrieval System)의 완전성을 평가** 하는 핵심 메트릭으로, Vector DB나 검색 알고리즘이 중요한 정보를 빠뜨리지 않는지 확인합니다.

### ⚠️ 중요: Ground Truth 필수

**Context Recall은 다른 Ragas 메트릭과 달리`expected_output` (ground_truth)이 필수입니다.**

  * `expected_output`이 제공되지 않으면 Context Recall은 **자동으로 스킵** 됩니다
  * metric_adapters.py Line 450: `self.context_recall`은 `if context.expected_output:` 블록 내에만 포함됨
  * 다른 3개 메트릭(Faithfulness, Answer Relevancy, Context Precision)은 ground truth 없이도 평가 가능

### 🎯 비즈니스 임팩트

  * **검색 완전성 보장** : 중요한 정보 누락으로 인한 불완전한 답변 방지
  * **사용자 만족도** : 질문에 대한 포괄적인 정보 제공
  * **검색 시스템 개선** : top_k, embedding 모델, 청킹 전략 최적화 지표
  * **품질 보증** : 테스트 세트로 검색 시스템의 회귀(regression) 탐지

## 📊 다이어그램 시각화

### 1️⃣ 핵심 개념 및 재현율 평가 (Ragas)
```python
    graph TD
        A[Question + Contexts + Ground Truth] --> B[ContextRecall Metric  
    Ragas Framework]
        B --> C[LLM Judge  
    gpt-4o-mini]
    
        C --> D[Ground Truth Claims 추출]
        D --> E[GT Claim 1, 2, 3, ...]
    
        E --> F{각 GT Claim 검증}
        F -->|Context에서 찾음| G[Recalled: 1]
        F -->|Context에 없음| H[Missing: 0]
    
        G --> I[Context Recall Calculation]
        H --> I
    
        I --> J[Recall Score  
    = recalled_claims / total_gt_claims]
    
        J --> K{Coverage Level}
        K -->|≥ 0.90| L[Excellent: 완전한 Coverage]
        K -->|0.75-0.89| M[Good: 대부분 포함]
        K -->|0.60-0.74| N[Moderate: 일부 누락]
        K -->|< 0.60| O[Poor: 심각한 누락]
    
        style A fill:#e1f5ff
        style J fill:#fff3cd
        style L fill:#d4edda
        style O fill:#f8d7da
        
```

### 2️⃣ 평가 파이프라인 (Coverage Check)
```python
    sequenceDiagram
        participant RAG as RAG System
        participant Adapter as RagasAdapter
        participant Ragas as Ragas Framework
        participant LLM as gpt-4o-mini
    
        RAG->>Adapter: evaluate(question, contexts, ground_truth_answer)
        Note over RAG: ground_truth_answer는  
    필수 정보 포함
    
        Adapter->>Adapter: Create Ragas Dataset  
    SingleTurnSample
    
        Adapter->>Ragas: evaluate(dataset, metrics=[context_recall])
    
        Ragas->>LLM: Extract claims from ground_truth
        LLM-->>Ragas: [GT Claim 1, Claim 2, Claim 3, ...]
    
        loop For each GT claim
            Ragas->>LLM: Is claim present in contexts?
            LLM-->>Ragas: Yes/No
        end
    
        Ragas->>Ragas: Calculate: found_claims / total_gt_claims
    
        Ragas-->>Adapter: context_recall score (0-1)
    
        Adapter-->>RAG: {'ragas_context_recall': 0.88}
        
```

### 3️⃣ Precision vs Recall Trade-off
```python
    graph TD
        A[RAG Retrieval Optimization] --> B{목표 설정}
    
        B -->|고정밀도| C[Context Precision 최적화  
    Metric 24]
        B -->|고재현율| D[Context Recall 최적화  
    Metric 25]
        B -->|균형| E[Precision & Recall 밸런스]
    
        C --> F[Strategy: Reranker + Top-K=3  
    Result: Precision ↑, Recall ↓  
    Use: 정확성 중시 QA]
    
        D --> G[Strategy: Increase Top-K=10  
    Result: Recall ↑, Precision ↓  
    Use: 정보 누락 방지]
    
        E --> H[Strategy: Hybrid + Rerank + Top-K=5  
    Result: 균형 잡힌 성능  
    Use: 프로덕션 권장]
    
        F --> I[F1-Score = 2×P×R / P+R]
        G --> I
        H --> I
    
        I --> J[최적화 목표:  
    F1-Score ≥ 0.85]
    
        J --> K[실험적 Top-K 조정:  
    3, 5, 10 테스트  
    Cost vs Quality 분석]
    
        style A fill:#e1f5ff
        style I fill:#fff3cd
        style J fill:#d4edda
        
```

### 4️⃣ 임계값 및 Coverage 최적화
```python
    graph TD
        A[Context Recall Score] --> B{임계값 비교}
        B -->|≥ 0.90| C[🌟 Excellent  
    Complete Coverage]
        B -->|0.75-0.89| D[✅ Good  
    Most Info Included]
        B -->|0.60-0.74| E[⚠️ Moderate  
    Some Missing Info]
        B -->|< 0.60| F[❌ Poor  
    Significant Gaps]
    
        C --> G[권장: 현재 Top-K 유지  
    Coverage 충분]
        D --> H[권장: Top-K 증가  
    0.90 목표]
        E --> I[권장: Chunk Size 조정  
    Retrieval 전략 개선]
        F --> J[권장: 즉시 개선  
    Embedding/Chunking 재설계]
    
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
Line 450 (context_recall 메트릭 선택 - **조건부**)  
**외부 라이브러리** | Ragas (`ragas.metrics.context_recall`)  
**반환 키** | `ragas_context_recall`  
**전제 조건** | **⚠️`expected_output` (ground_truth) 필수**  
  
## ⚙️ 평가 원리

### Step 1: Ground Truth에서 Claim 추출

LLM을 사용하여 정답(Ground Truth)에서 독립적인 사실 주장(Claims)을 추출합니다.

Ground Truth: "파이썬 3.11은 2022년 10월에 출시되었으며, 이전 버전보다 10-60% 빠릅니다. Faster CPython 프로젝트의 결과입니다." → Extracted Claims: 1\. "파이썬 3.11은 2022년 10월에 출시되었다" 2\. "파이썬 3.11은 이전 버전보다 10-60% 빠르다" 3\. "Faster CPython 프로젝트의 결과이다"

### Step 2: 컨텍스트에서 Claim 검증

각 Claim이 검색된 컨텍스트에서 확인 가능한지 LLM이 판단합니다.

Retrieved Contexts: [1] "Python 3.11 was released in October 2022..." [2] "Performance improvements range from 10-60% faster..." [3] "Django is a Python web framework..." # Not relevant Claim 1: ✅ Supported by Context [1] Claim 2: ✅ Supported by Context [2] Claim 3: ❌ Not found in any context

### Step 3: Recall Score 계산

Context Recall = (검색된 컨텍스트에서 확인 가능한 Claims 수) / (전체 Claims 수) 예시: 2 / 3 = 0.667 (66.7%의 정보만 검색됨)

#### 📊 Score 해석 가이드

  * 0.9 ~ 1.0: 완벽한 검색 재현율 (Excellent)
  * 0.7 ~ 0.89: 양호한 검색 완전성 (Good)
  * 0.5 ~ 0.69: 일부 정보 누락 (Acceptable with caution)
  * < 0.5: 중요한 정보 누락 (Poor - 수정 필요)

**⚠️ 방향 주의:** 높을수록 좋음 (1.0 = 모든 필요한 정보가 검색됨)

**🔍 평가 대상:** 생성 품질이 아닌 **검색(Retrieval) 완전성** 을 평가함

## 🔧 메서드 상세

### RagasAdapter.evaluate() - Context Recall 평가

**소스 코드** (metric_adapters.py Lines 420-534):

def evaluate(self, context: EvaluationContext) -> Dict[str, Any]: """Evaluate using Ragas RAG metrics""" if not self._available: return {} # Only evaluate RAG tasks with retrieved context if not context.retrieved_context: return {} results = {} try: from datasets import Dataset # Prepare data in Ragas format data = { 'question': [context.input_text], 'answer': [context.output_text], 'contexts': [context.retrieved_context] } # Select metrics based on available data # ⚠️ IMPORTANT: context_recall requires ground_truth if context.expected_output: data['ground_truth'] = [context.expected_output] metrics = [ self.faithfulness, self.answer_relevancy, self.context_recall, # ← Context Recall (조건부 - ground_truth 필요) self.context_precision ] else: # Skip context_recall when no ground_truth available metrics = [ self.faithfulness, self.answer_relevancy, self.context_precision # ← Context Recall은 제외됨 ] dataset = Dataset.from_dict(data) # Set LLM for all metrics for metric in metrics: if hasattr(metric, 'llm'): metric.llm = self.llm eval_result = self.evaluate_fn( dataset, metrics=metrics ) # Extract Context Recall score (if ground_truth was provided) import math for metric_name in ['faithfulness', 'answer_relevancy', 'context_recall', 'context_precision']: try: value_list = eval_result[metric_name] if isinstance(value_list, (list, tuple)) and len(value_list) > 0: value = value_list[0] else: value = value_list if value is not None and isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)): results[f'ragas_{metric_name}'] = float(value) except (KeyError, IndexError, TypeError, AttributeError, ValueError): continue # Skip if metric not available # Calculate overall Ragas score numeric_metrics = {k: v for k, v in results.items() if isinstance(v, (int, float)) and not isinstance(v, bool)} if numeric_metrics: results['ragas_overall_score'] = sum(numeric_metrics.values()) / len(numeric_metrics) except Exception as e: import traceback print(f"⚠️ Ragas unexpected error: {e}") results['ragas_error'] = f"Unexpected error: {str(e)}" return results

#### 🔑 핵심 포인트

  * **조건부 트리거** : `retrieved_context`와 `expected_output`이 모두 제공되어야 Context Recall 평가됨
  * **Ground Truth 필수** : `expected_output` 없으면 자동으로 스킵됨
  * **LLM 기반** : GPT-4o-mini 또는 GPT-4o를 사용하여 Ground Truth에서 Claim 추출 및 검증
  * **검색 완전성 평가** : 생성 품질이 아닌 검색 시스템의 재현율(Recall)을 측정
  * **Overall Score 포함** : 다른 Ragas 메트릭과 평균화되어 `ragas_overall_score`에 반영

## 📊 데이터 수집 방법

### 방법 1: HybridPerformanceMonitor with Ground Truth (권장)

RAG 시스템에서 `retrieved_context`와 `expected_output`을 함께 제공하면 Context Recall이 평가됩니다.

from agent_evaluator import HybridPerformanceMonitor, create_taskresult # 1. Monitor 초기화 (Ragas 활성화) monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o-mini" ) # 2. 테스트 데이터 준비 (Ground Truth 포함) test_cases = [ { 'question': "파이썬 3.11의 성능 개선 사항은?", 'ground_truth': "파이썬 3.11은 2022년 10월에 출시되었으며, 이전 버전보다 10-60% 빠릅니다. Faster CPython 프로젝트의 결과입니다.", }, # ... 더 많은 테스트 케이스 ] # 3. RAG 시스템 실행 및 평가 for test in test_cases: query = test['question'] ground_truth = test['ground_truth'] # Vector DB에서 컨텍스트 검색 retrieved_docs = vector_db.search(query, top_k=5) retrieved_context = [doc.content for doc in retrieved_docs] # LLM 답변 생성 llm_response = llm.generate( prompt=f"Question: {query}\n\nContext: {retrieved_context}", context=retrieved_context ) # 4. Task 기록 (Context Recall 자동 평가) task = create_taskresult( task_id=f"rag_test_{test['question'][:20]}", task_type="qa", success=True, completion_score=1.0 ) monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=llm_response, retrieved_context=retrieved_context, # ← 필수 expected_output=ground_truth # ← Context Recall 트리거 (필수!) ) # 5. Context Recall Score 확인 latest_task = monitor.extended_tasks[-1] context_recall = latest_task.advanced_metrics.get('ragas_context_recall') if context_recall is not None: print(f"Context Recall Score: {context_recall:.3f}") if context_recall < 0.7: print(f"⚠️ 경고: 낮은 Context Recall - 중요한 정보 누락 가능성") else: print("⚠️ Context Recall이 평가되지 않았습니다 (ground_truth 누락?)") 

### 방법 2: RagasAdapter 독립 사용 with Ground Truth (고급)

Ragas 메트릭만 단독으로 평가하고 싶을 때 사용합니다.

from agent_evaluator.integrations.metric_adapters import ( RagasAdapter, EvaluationContext ) # 1. Adapter 초기화 ragas = RagasAdapter(llm_model="gpt-4o-mini") # 2. Evaluation Context 생성 (Ground Truth 포함) context = EvaluationContext( input_text="Kubernetes에서 Pod와 Container의 차이는?", output_text="Pod는 Kubernetes에서 배포 가능한 최소 단위로, 하나 이상의 Container를 포함합니다. Container는 실제 애플리케이션이 실행되는 격리된 환경입니다.", retrieved_context=[ "A Pod is the smallest deployable unit in Kubernetes and can contain one or more containers.", "Containers provide isolated runtime environments for applications.", "Pods share network and storage resources." ], expected_output="Pod는 Kubernetes의 최소 배포 단위이며 하나 이상의 Container를 포함합니다. Container는 격리된 실행 환경을 제공하며, Pod 내의 Container들은 네트워크와 스토리지를 공유합니다." # ← Ground Truth (필수!) ) # 3. Ragas 평가 실행 results = ragas.evaluate(context) # 4. Context Recall 결과 확인 if 'ragas_context_recall' in results: print(f"Context Recall: {results['ragas_context_recall']:.3f}") print(f"Context Precision: {results['ragas_context_precision']:.3f}") print(f"Faithfulness: {results['ragas_faithfulness']:.3f}") print(f"Answer Relevancy: {results['ragas_answer_relevancy']:.3f}") print(f"Overall Score: {results['ragas_overall_score']:.3f}") print(f"Quality Level: {results['ragas_quality']}") else: print("⚠️ Context Recall이 평가되지 않았습니다") 

### 방법 3: 검색 시스템 회귀 테스트 (프로덕션)

Golden Dataset으로 검색 시스템의 성능 회귀(regression)를 탐지합니다.

from agent_evaluator import HybridPerformanceMonitor, create_taskresult from typing import List, Dict import json class RetrievalRegressionTest: def __init__(self, golden_dataset_path: str): """ 검색 시스템 회귀 테스트 Args: golden_dataset_path: Ground Truth가 포함된 테스트 데이터셋 경로 """ self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o" # 회귀 테스트에는 고정밀 모델 사용 ) # Golden Dataset 로드 with open(golden_dataset_path, 'r', encoding='utf-8') as f: self.golden_dataset = json.load(f) def run_regression_test(self, retrieval_system) -> Dict: """검색 시스템의 Context Recall 측정""" recall_scores = [] failed_cases = [] for i, test_case in enumerate(self.golden_dataset): query = test_case['question'] ground_truth = test_case['ground_truth'] # 검색 시스템으로 컨텍스트 검색 retrieved = retrieval_system.retrieve(query) # LLM 답변 생성 answer = self.llm.generate(query, retrieved) # Context Recall 평가 task = create_taskresult(f"regression_test_{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved, expected_output=ground_truth # ← Ground Truth (필수) ) latest = self.monitor.extended_tasks[-1] context_recall = latest.advanced_metrics.get('ragas_context_recall', 0.0) recall_scores.append(context_recall) # 낮은 Recall 케이스 기록 if context_recall < 0.7: failed_cases.append({ 'question': query, 'ground_truth': ground_truth, 'context_recall': context_recall, 'retrieved_contexts': retrieved }) avg_recall = sum(recall_scores) / len(recall_scores) if recall_scores else 0 return { 'avg_context_recall': avg_recall, 'min_context_recall': min(recall_scores) if recall_scores else 0, 'max_context_recall': max(recall_scores) if recall_scores else 0, 'failed_cases_count': len(failed_cases), 'failed_cases': failed_cases, 'total_test_cases': len(self.golden_dataset), 'pass_rate': (len(self.golden_dataset) - len(failed_cases)) / len(self.golden_dataset) } def compare_with_baseline(self, current_result: Dict, baseline_recall: float) -> Dict: """현재 결과와 베이스라인 비교""" current_recall = current_result['avg_context_recall'] diff = current_recall - baseline_recall status = "PASS" if diff >= -0.05 else "FAIL" # 5% 이상 하락 시 실패 return { 'status': status, 'current_recall': current_recall, 'baseline_recall': baseline_recall, 'difference': diff, 'regression_detected': diff < -0.05 } # 사용 예시 # 1. Golden Dataset 준비 (golden_dataset.json) golden_dataset = [ { "question": "파이썬 3.11의 성능 개선 사항은?", "ground_truth": "파이썬 3.11은 2022년 10월에 출시되었으며, 이전 버전보다 10-60% 빠릅니다." }, # ... 더 많은 테스트 케이스 ] # 2. 회귀 테스트 실행 regression_test = RetrievalRegressionTest("golden_dataset.json") result = regression_test.run_regression_test(my_retrieval_system) print(f"평균 Context Recall: {result['avg_context_recall']:.3f}") print(f"실패한 케이스: {result['failed_cases_count']}/{result['total_test_cases']}") print(f"Pass Rate: {result['pass_rate']*100:.1f}%") # 3. 베이스라인과 비교 baseline_recall = 0.85 # 이전 버전의 Context Recall comparison = regression_test.compare_with_baseline(result, baseline_recall) if comparison['status'] == "FAIL": print(f"🚨 회귀 감지! Context Recall이 {comparison['difference']*100:.1f}% 하락했습니다.") else: print(f"✅ 회귀 테스트 통과") 

### 방법 4: 검색 파라미터 최적화 (A/B 테스트)

서로 다른 검색 파라미터의 Context Recall을 비교하여 최적값을 찾습니다.

from agent_evaluator import HybridPerformanceMonitor, create_taskresult from typing import List, Dict class RetrievalParameterOptimization: def __init__(self, golden_dataset: List[Dict]): """ Args: golden_dataset: Ground Truth가 포함된 테스트 데이터 """ self.golden_dataset = golden_dataset self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o" ) def test_top_k_parameter(self, retrieval_system) -> Dict: """top_k 파라미터 최적화""" results = {} for top_k in [3, 5, 7, 10, 15]: recall_scores = [] for i, test_case in enumerate(self.golden_dataset): query = test_case['question'] ground_truth = test_case['ground_truth'] # 다양한 top_k로 검색 retrieved = retrieval_system.retrieve(query, top_k=top_k) answer = self.llm.generate(query, retrieved) # Context Recall 평가 task = create_taskresult(f"topk_{top_k}_q{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved, expected_output=ground_truth ) latest = self.monitor.extended_tasks[-1] context_recall = latest.advanced_metrics.get('ragas_context_recall', 0.0) recall_scores.append(context_recall) results[top_k] = { 'avg_recall': sum(recall_scores) / len(recall_scores), 'min_recall': min(recall_scores), 'max_recall': max(recall_scores) } print(f"top_k={top_k}: Context Recall = {results[top_k]['avg_recall']:.3f}") # 최적 top_k 선택 best_top_k = max(results, key=lambda k: results[k]['avg_recall']) print(f"\n🏆 최적 top_k: {best_top_k} (Recall: {results[best_top_k]['avg_recall']:.3f})") return {'best_top_k': best_top_k, 'all_results': results} def test_chunk_size(self, retrieval_system) -> Dict: """문서 청킹 크기 최적화""" results = {} for chunk_size in [256, 512, 1024, 2048]: recall_scores = [] # 문서 재청킹 retrieval_system.reindex_with_chunk_size(chunk_size) for i, test_case in enumerate(self.golden_dataset): query = test_case['question'] ground_truth = test_case['ground_truth'] retrieved = retrieval_system.retrieve(query, top_k=5) answer = self.llm.generate(query, retrieved) task = create_taskresult(f"chunk_{chunk_size}_q{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved, expected_output=ground_truth ) latest = self.monitor.extended_tasks[-1] context_recall = latest.advanced_metrics.get('ragas_context_recall', 0.0) recall_scores.append(context_recall) results[chunk_size] = sum(recall_scores) / len(recall_scores) print(f"chunk_size={chunk_size}: Context Recall = {results[chunk_size]:.3f}") best_chunk = max(results, key=results.get) print(f"\n🏆 최적 chunk_size: {best_chunk} (Recall: {results[best_chunk]:.3f})") return {'best_chunk_size': best_chunk, 'all_results': results} # 사용 예시 golden_dataset = [ {"question": "Q1", "ground_truth": "GT1"}, {"question": "Q2", "ground_truth": "GT2"}, # ... 더 많은 테스트 케이스 ] optimizer = RetrievalParameterOptimization(golden_dataset) # top_k 최적화 top_k_result = optimizer.test_top_k_parameter(my_retrieval_system) # chunk_size 최적화 chunk_result = optimizer.test_chunk_size(my_retrieval_system) 

## 💡 Best Practices

### 1\. Threshold 설정 전략

도메인 | 권장 Threshold | 이유  
---|---|---  
의료, 법률, 금융 | **≥ 0.9** | 중요한 정보 누락 시 심각한 결과 초래  
고객 지원, FAQ | **≥ 0.8** | 완전한 답변 제공 필요  
기술 문서, 튜토리얼 | **≥ 0.7** | 핵심 정보 포함 필수  
일반 대화, 브레인스토밍 | **≥ 0.6** | 기본 정보 제공 충분  
  
### 2\. Context Recall 개선 방법

  1. **top_k 증가**
     * 더 많은 컨텍스트 검색 (3 → 5 → 7)
     * 단, Precision 하락 가능성 주의
     * Recall vs Precision 트레이드오프 고려
  2. **Hybrid Search 도입**
     * Semantic search + Keyword search 결합
     * 키워드 매칭으로 놓친 정보 보완
     * BM25 + Vector search (alpha 가중치 조정)
  3. **문서 청킹 전략 개선**
     * Chunk 크기 최적화 (너무 작으면 정보 분산, 너무 크면 노이즈 증가)
     * Overlap 설정으로 경계 정보 누락 방지
     * Semantic chunking (문맥 단위로 분할)
  4. **Query Expansion**
     * 동의어, 유사 표현 추가로 검색 범위 확장
     * LLM으로 query rewriting (더 구체적/명확하게)
     * Multi-query retrieval (여러 관점에서 검색)
  5. **문서 인덱싱 개선**
     * 메타데이터 활용 (카테고리, 태그, 날짜 등)
     * 계층적 인덱싱 (문서 → 섹션 → 단락)
     * 더 나은 Embedding 모델 (text-embedding-3-large)

### ⚠️ 주의사항

  * **Ground Truth 필수** : `expected_output`이 없으면 Context Recall을 평가할 수 없음
  * **테스트 전용** : Ground Truth가 필요하므로 프로덕션 실시간 평가에는 부적합
  * **LLM 의존성** : GPT 모델 API 비용 및 latency 고려 필요
  * **검색 완전성만 평가** : 생성 품질이 아닌 검색 시스템의 재현율만 측정함
  * **언어 제한** : 영어 최적화, 다른 언어는 성능이 낮을 수 있음
  * **Ground Truth 품질** : Ground Truth 자체가 불완전하면 평가 결과도 부정확함

### 3\. Golden Dataset 구축 전략

  * **다양한 질문 유형** : 사실 기반, 비교, 설명, How-to 등 다양한 질문 포함
  * **난이도 분포** : 쉬운 질문부터 어려운 질문까지 균형 있게 구성
  * **도메인 커버리지** : 주요 사용 사례와 도메인을 모두 커버
  * **정기적 업데이트** : 새로운 문서 추가 시 Golden Dataset도 업데이트
  * **Human Review** : Ground Truth는 전문가가 작성하거나 검증

### 4\. Precision vs Recall 균형

**Context Precision과 Context Recall을 함께 최적화:**

  * **Precision만 높으면** : 관련성 높지만 정보 부족 (불완전한 답변)
  * **Recall만 높으면** : 정보는 많지만 노이즈 많음 (품질 저하)
  * **균형 잡힌 전략** : 
    * 초기 검색: 높은 top_k로 Recall 확보 (예: top_k=20)
    * Re-ranking: 관련성 높은 컨텍스트만 선택하여 Precision 개선 (최종 top_k=5)

## 🎯 활용 예시

### 예시 1: CI/CD 파이프라인에서 회귀 테스트

from agent_evaluator import HybridPerformanceMonitor, create_taskresult import sys class RetrievalCITest: def __init__(self, golden_dataset_path: str, threshold: float = 0.75): self.monitor = HybridPerformanceMonitor(use_ragas=True) self.threshold = threshold with open(golden_dataset_path, 'r') as f: self.golden_dataset = json.load(f) def run_ci_test(self, retrieval_system) -> bool: """CI/CD에서 실행할 회귀 테스트""" recall_scores = [] for i, test_case in enumerate(self.golden_dataset): query = test_case['question'] ground_truth = test_case['ground_truth'] retrieved = retrieval_system.retrieve(query) answer = self.llm.generate(query, retrieved) task = create_taskresult(f"ci_test_{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved, expected_output=ground_truth ) latest = self.monitor.extended_tasks[-1] context_recall = latest.advanced_metrics.get('ragas_context_recall', 0.0) recall_scores.append(context_recall) avg_recall = sum(recall_scores) / len(recall_scores) print(f"평균 Context Recall: {avg_recall:.3f}") print(f"Threshold: {self.threshold}") if avg_recall < self.threshold: print(f"❌ 테스트 실패: Context Recall이 threshold보다 낮습니다") return False else: print(f"✅ 테스트 통과") return True # CI/CD 스크립트에서 사용 if __name__ == "__main__": ci_test = RetrievalCITest("golden_dataset.json", threshold=0.75) success = ci_test.run_ci_test(my_retrieval_system) if not success: sys.exit(1) # CI/CD 실패

### 예시 2: 검색 시스템 성능 벤치마크

from agent_evaluator import HybridPerformanceMonitor, create_taskresult class RetrievalBenchmark: def __init__(self, golden_dataset: list): self.golden_dataset = golden_dataset self.monitor = HybridPerformanceMonitor(use_ragas=True) def benchmark_system(self, system_name: str, retrieval_system) -> dict: """검색 시스템 벤치마크""" recall_scores = [] precision_scores = [] for i, test_case in enumerate(self.golden_dataset): query = test_case['question'] ground_truth = test_case['ground_truth'] retrieved = retrieval_system.retrieve(query) answer = self.llm.generate(query, retrieved) task = create_taskresult(f"{system_name}_q{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved, expected_output=ground_truth ) latest = self.monitor.extended_tasks[-1] context_recall = latest.advanced_metrics.get('ragas_context_recall', 0.0) context_precision = latest.advanced_metrics.get('ragas_context_precision', 0.0) recall_scores.append(context_recall) precision_scores.append(context_precision) return { 'system_name': system_name, 'avg_recall': sum(recall_scores) / len(recall_scores), 'avg_precision': sum(precision_scores) / len(precision_scores), 'f1_score': self._calculate_f1(recall_scores, precision_scores) } def _calculate_f1(self, recalls: list, precisions: list) -> float: """F1 Score 계산 (Precision과 Recall의 조화 평균)""" f1_scores = [] for r, p in zip(recalls, precisions): if r + p > 0: f1 = 2 * (r * p) / (r + p) f1_scores.append(f1) return sum(f1_scores) / len(f1_scores) if f1_scores else 0 # 사용 benchmark = RetrievalBenchmark(golden_dataset) systems = { 'baseline': baseline_system, 'improved_v1': improved_system_v1, 'improved_v2': improved_system_v2 } for name, system in systems.items(): result = benchmark.benchmark_system(name, system) print(f"\n{name}:") print(f" Recall: {result['avg_recall']:.3f}") print(f" Precision: {result['avg_precision']:.3f}") print(f" F1 Score: {result['f1_score']:.3f}") 

### 예시 3: 검색 품질 대시보드 (오프라인)

from agent_evaluator import HybridPerformanceMonitor, create_taskresult import matplotlib.pyplot as plt class RetrievalQualityDashboard: def __init__(self, golden_dataset: list): self.golden_dataset = golden_dataset self.monitor = HybridPerformanceMonitor(use_ragas=True) def generate_quality_report(self, retrieval_system) -> dict: """검색 품질 리포트 생성""" results = { 'recall_scores': [], 'precision_scores': [], 'failed_queries': [] } for i, test_case in enumerate(self.golden_dataset): query = test_case['question'] ground_truth = test_case['ground_truth'] retrieved = retrieval_system.retrieve(query) answer = self.llm.generate(query, retrieved) task = create_taskresult(f"quality_test_{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved, expected_output=ground_truth ) latest = self.monitor.extended_tasks[-1] recall = latest.advanced_metrics.get('ragas_context_recall', 0.0) precision = latest.advanced_metrics.get('ragas_context_precision', 0.0) results['recall_scores'].append(recall) results['precision_scores'].append(precision) if recall < 0.7: results['failed_queries'].append({ 'query': query, 'recall': recall, 'precision': precision }) return results def plot_quality_metrics(self, results: dict): """품질 메트릭 시각화""" fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5)) # Recall 분포 ax1.hist(results['recall_scores'], bins=20, color='orange', alpha=0.7) ax1.set_title('Context Recall Distribution') ax1.set_xlabel('Context Recall') ax1.set_ylabel('Frequency') # Precision vs Recall ax2.scatter(results['recall_scores'], results['precision_scores'], alpha=0.5, color='purple') ax2.set_title('Precision vs Recall') ax2.set_xlabel('Context Recall') ax2.set_ylabel('Context Precision') plt.tight_layout() plt.savefig('retrieval_quality_report.png') print("리포트가 'retrieval_quality_report.png'에 저장되었습니다") # 사용 dashboard = RetrievalQualityDashboard(golden_dataset) results = dashboard.generate_quality_report(my_retrieval_system) dashboard.plot_quality_metrics(results) print(f"\n평균 Recall: {sum(results['recall_scores']) / len(results['recall_scores']):.3f}") print(f"평균 Precision: {sum(results['precision_scores']) / len(results['precision_scores']):.3f}") print(f"실패한 쿼리: {len(results['failed_queries'])}/{len(golden_dataset)}") 

## 🔗 관련 메트릭

메트릭 | 관계 | 설명  
---|---|---  
**Context Precision** | 보완 관계 | 검색된 컨텍스트의 정밀도 평가 (Precision)  
Context Recall은 완전성 평가 (Recall)  
**Faithfulness** | 보완 관계 | 생성된 답변의 사실성 평가 (생성 품질)  
Context Recall은 검색 완전성 평가  
**Answer Relevancy (Ragas)** | 보완 관계 | 답변과 질문의 관련성 평가  
Context Recall은 검색 완전성 평가  
**Correctness (DeepEval)** | 유사 개념 | 답변과 Ground Truth의 일치성 평가  
Context Recall은 검색된 컨텍스트와 Ground Truth의 일치성 평가  
  
#### 💡 메트릭 조합 전략

**검색 시스템 품질 보장** \- Precision과 Recall 함께 평가:

  * **Context Precision** (높을수록 좋음): 검색된 컨텍스트의 정밀도
  * **Context Recall** (높을수록 좋음): 검색된 컨텍스트의 완전성
  * **F1 Score** : 2 × (Precision × Recall) / (Precision + Recall)

→ F1 Score 0.8 이상이면 **균형 잡힌 고품질 검색 시스템**

## 📚 참고 자료

  * [Ragas Context Recall 공식 문서](<https://docs.ragas.io/en/latest/concepts/metrics/context_recall.html>)
  * [RAGAS: Automated Evaluation of RAG (논문)](<https://arxiv.org/abs/2309.15217>)
  * [Agent Evaluator RAG 평가 예시](<../examples/rag_evaluation.py>)
  * [Faithfulness (Ragas) 문서](<./22_FAITHFULNESS.html>)
  * [Answer Relevancy (Ragas) 문서](<./23_ANSWER_RELEVANCY_RAGAS.html>)
  * [Context Precision 문서](<./24_CONTEXT_PRECISION.html>)

**Agent Evaluator v0.5.2** \- Layer 3 Ragas Metrics

Context Recall: RAG 검색 시스템의 완전성 평가 (Ground Truth 필수)

Developed by Agent Evaluator Team | [GitHub](<https://github.com/your-repo/agent-evaluator>)
