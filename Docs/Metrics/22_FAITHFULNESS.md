# 📊 Faithfulness

Ragas RAG 평가 메트릭 - 사실적 일관성 (Factual Consistency)

Agent Evaluator v0.5.1

Ragas Layer 3 RAG Evaluation

## 📋 개요

**Faithfulness** 는 Ragas 라이브러리에서 제공하는 RAG(Retrieval-Augmented Generation) 시스템 전용 평가 메트릭으로, **LLM이 생성한 답변이 검색된 컨텍스트(Context)와 사실적으로 일치하는지** 를 측정합니다.

  


이 메트릭은 답변의 각 주장(Claim)을 추출한 후, 검색된 컨텍스트에서 해당 주장을 뒷받침할 수 있는 근거가 있는지 검증합니다. **환각(Hallucination) 탐지** 의 핵심 메트릭으로, RAG 시스템이 검색된 문서 범위 내에서만 답변을 생성하는지 확인합니다.

### 🎯 비즈니스 임팩트

  * **환각 방지** : RAG 시스템이 검색된 문서에 없는 내용을 지어내는 것을 방지
  * **신뢰성 보장** : 의료, 법률, 금융 등 고위험 도메인에서 사실 기반 답변 보장
  * **규정 준수** : 출처 기반 답변 요구사항 충족 (예: GDPR, HIPAA)
  * **사용자 신뢰** : 잘못된 정보 제공으로 인한 법적 리스크 및 신뢰도 하락 방지

## 📊 다이어그램 시각화

### 1️⃣ 핵심 개념 및 충실도 평가 (Ragas)
```python
    graph TD
        A[Response + Retrieved Context] --> B[Faithfulness Metric  
    Ragas Framework]
        B --> C[LLM Judge  
    gpt-4o-mini default]
    
        C --> D[Claim Extraction]
        D --> E[Response에서 모든 주장 추출  
    Claim 1, 2, 3, ...]
    
        E --> F[Claim-by-Claim Verification]
        F --> G{Each Claim}
    
        G -->|Context 지원| H[Faithful: 1]
        G -->|Context 미지원| I[Unfaithful: 0]
    
        H --> J[Faithfulness Calculation]
        I --> J
    
        J --> K[Faithfulness Score  
    = supported_claims / total_claims]
    
        K --> L{Quality Level}
        L -->|≥ 0.90| M[Excellent: 매우 충실]
        L -->|0.75-0.89| N[Good: 충실함]
        L -->|0.60-0.74| O[Moderate: 부분 불충실]
        L -->|< 0.60| P[Poor: 불충실 심각]
    
        style A fill:#e1f5ff
        style K fill:#fff3cd
        style M fill:#d4edda
        style P fill:#f8d7da
        
```

### 2️⃣ 평가 파이프라인 (Ragas Integration)
```python
    sequenceDiagram
        participant RAG as RAG System
        participant Adapter as RagasAdapter
        participant Ragas as Ragas Framework
        participant LLM as gpt-4o-mini
    
        RAG->>Adapter: evaluate(question, answer, contexts)
        Adapter->>Adapter: Create Ragas Dataset  
    SingleTurnSample
    
        Adapter->>Ragas: evaluate(dataset, metrics=[faithfulness])
        Note over Ragas: LangChain OpenAI LLM  
    model: gpt-4o-mini
    
        Ragas->>LLM: Extract claims from answer
        LLM-->>Ragas: [Claim 1, Claim 2, Claim 3, ...]
    
        loop For each claim
            Ragas->>LLM: Is claim supported by contexts?
            LLM-->>Ragas: Yes/No
        end
    
        Ragas->>Ragas: Calculate: supported / total
        Ragas-->>Adapter: faithfulness score (0-1)
    
        Adapter-->>RAG: {'ragas_faithfulness': 0.92}
        
```

### 3️⃣ Ragas 4-Metric Suite (RAG 평가)
```python
    graph TD
        A[Ragas Framework] --> B[4가지 RAG 메트릭]
    
        B --> C[1. Faithfulness  
    충실도]
        B --> D[2. Answer Relevancy  
    답변 관련성]
        B --> E[3. Context Precision  
    문맥 정밀도]
        B --> F[4. Context Recall  
    문맥 재현율]
    
        C --> G[Response vs Context  
    모든 주장이 근거 있는가?]
        D --> H[Answer vs Question  
    질문에 답하는가?]
        E --> I[Context Ranking  
    관련 문맥이 상위에?]
        F --> J[Context Coverage  
    필요한 정보 포함?]
    
        G --> K[Combined RAG Score  
    4개 메트릭 평균]
        H --> K
        I --> K
        J --> K
    
        K --> L[RAG System Quality 0-1]
    
        style A fill:#e1f5ff
        style K fill:#fff3cd
        style L fill:#d4edda
        
```

### 4️⃣ 임계값 및 RAG 최적화
```python
    graph TD
        A[Faithfulness Score] --> B{임계값 비교}
        B -->|≥ 0.90| C[🌟 Excellent  
    Highly Faithful]
        B -->|0.75-0.89| D[✅ Good  
    Faithful]
        B -->|0.60-0.74| E[⚠️ Moderate  
    Some Unfaithful Claims]
        B -->|< 0.60| F[❌ Poor  
    Many Unfaithful Claims]
    
        C --> G[권장: 현재 RAG 유지  
    Context 품질 지속]
        D --> H[권장: 0.90 목표  
    Retrieval Top-K 조정]
        E --> I[권장: Context 필터링  
    Reranker 도입]
        F --> J[권장: 즉시 개선  
    Retrieval 전면 재검토]
    
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
Lines 448, 456 (faithfulness 메트릭 선택)  
**외부 라이브러리** | Ragas (`ragas.metrics.faithfulness`)  
**반환 키** | `ragas_faithfulness`  
  
## ⚙️ 평가 원리

### Step 1: Claim 추출

LLM을 사용하여 생성된 답변에서 독립적인 사실 주장(Claims)을 추출합니다.

Answer: "파이썬 3.11은 2022년 10월에 출시되었으며, 이전 버전보다 10-60% 빠릅니다." → Claims: 1\. "파이썬 3.11은 2022년 10월에 출시되었다" 2\. "파이썬 3.11은 이전 버전보다 10-60% 빠르다"

### Step 2: 컨텍스트 검증

각 Claim이 검색된 컨텍스트에서 뒷받침될 수 있는지 LLM이 판단합니다.

Context 1: "Python 3.11 was released in October 2022..." Context 2: "Performance improvements range from 10-60% faster..." Claim 1: ✅ Supported (Context 1에서 확인 가능) Claim 2: ✅ Supported (Context 2에서 확인 가능)

### Step 3: Score 계산

Faithfulness Score = (지원되는 Claims 수) / (전체 Claims 수) 예시: 2 / 2 = 1.0 (완벽한 일관성)

#### 📊 Score 해석 가이드

  * 0.9 ~ 1.0: 완벽한 사실 일관성 (Excellent)
  * 0.7 ~ 0.89: 양호한 일관성 (Good)
  * 0.5 ~ 0.69: 일부 환각 존재 (Acceptable with caution)
  * < 0.5: 심각한 환각 (Poor - 수정 필요)

**⚠️ 방향 주의:** 높을수록 좋음 (1.0 = 모든 주장이 컨텍스트에서 지원됨)

## 🔧 메서드 상세

### RagasAdapter.evaluate() - Faithfulness 평가

**소스 코드** (metric_adapters.py Lines 420-534):

def evaluate(self, context: EvaluationContext) -> Dict[str, Any]: """Evaluate using Ragas RAG metrics""" if not self._available: return {} # Only evaluate RAG tasks with retrieved context if not context.retrieved_context: return {} results = {} try: from datasets import Dataset # Prepare data in Ragas format data = { 'question': [context.input_text], 'answer': [context.output_text], 'contexts': [context.retrieved_context] } # Select metrics based on available data if context.expected_output: data['ground_truth'] = [context.expected_output] metrics = [ self.faithfulness, # ← Faithfulness 메트릭 self.answer_relevancy, self.context_recall, self.context_precision ] else: # Skip context_recall when no ground_truth available metrics = [ self.faithfulness, # ← Faithfulness 메트릭 (항상 포함) self.answer_relevancy, self.context_precision ] dataset = Dataset.from_dict(data) # Set LLM for all metrics for metric in metrics: if hasattr(metric, 'llm'): metric.llm = self.llm eval_result = self.evaluate_fn( dataset, metrics=metrics ) # Extract Faithfulness score import math for metric_name in ['faithfulness', 'answer_relevancy', 'context_recall', 'context_precision']: try: value_list = eval_result[metric_name] if isinstance(value_list, (list, tuple)) and len(value_list) > 0: value = value_list[0] else: value = value_list if value is not None and isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)): results[f'ragas_{metric_name}'] = float(value) except (KeyError, IndexError, TypeError, AttributeError, ValueError): continue # Calculate overall Ragas score numeric_metrics = {k: v for k, v in results.items() if isinstance(v, (int, float)) and not isinstance(v, bool)} if numeric_metrics: results['ragas_overall_score'] = sum(numeric_metrics.values()) / len(numeric_metrics) except Exception as e: import traceback print(f"⚠️ Ragas unexpected error: {e}") results['ragas_error'] = f"Unexpected error: {str(e)}" return results

#### 🔑 핵심 포인트

  * **자동 트리거** : `retrieved_context`가 제공되면 Faithfulness가 자동 평가됨
  * **Ground Truth 불필요** : `expected_output` 없이도 평가 가능 (answer vs contexts 비교)
  * **LLM 기반** : GPT-4o-mini 또는 GPT-4o를 사용하여 Claims 추출 및 검증
  * **Overall Score 포함** : 다른 Ragas 메트릭과 평균화되어 `ragas_overall_score`에 반영

## 📊 데이터 수집 방법

### 방법 1: HybridPerformanceMonitor 자동 평가 (권장)

RAG 시스템에서 `retrieved_context`만 제공하면 Faithfulness가 자동으로 평가됩니다.

from agent_evaluator import HybridPerformanceMonitor, create_taskresult # 1. Monitor 초기화 (Ragas 활성화) monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o-mini" # 비용 절감 ) # 2. RAG 시스템 실행 user_query = "파이썬 3.11의 주요 성능 개선 사항은 무엇인가요?" # Vector DB에서 컨텍스트 검색 retrieved_docs = vector_db.search(user_query, top_k=3) retrieved_context = [doc.content for doc in retrieved_docs] # LLM 답변 생성 llm_response = llm.generate( prompt=f"Question: {user_query}\n\nContext: {retrieved_context}", context=retrieved_context ) # 3. Task 기록 (Faithfulness 자동 평가) task = create_taskresult( task_id="rag_query_001", task_type="qa", success=True, completion_score=1.0 ) monitor.record_task( task=task, enable_advanced_metrics=True, # Ragas 활성화 input_text=user_query, output_text=llm_response, retrieved_context=retrieved_context # ← Faithfulness 트리거 ) # 4. Faithfulness Score 확인 latest_task = monitor.extended_tasks[-1] faithfulness = latest_task.advanced_metrics.get('ragas_faithfulness') overall = latest_task.advanced_metrics.get('ragas_overall_score') print(f"Faithfulness Score: {faithfulness:.3f}") print(f"Ragas Overall Score: {overall:.3f}") if faithfulness < 0.7: print(f"⚠️ 경고: 낮은 Faithfulness 감지 - 환각 가능성 있음") 

### 방법 2: RagasAdapter 독립 사용 (고급)

Ragas 메트릭만 단독으로 평가하고 싶을 때 사용합니다.

from agent_evaluator.integrations.metric_adapters import ( RagasAdapter, EvaluationContext ) # 1. Adapter 초기화 ragas = RagasAdapter(llm_model="gpt-4o-mini") # 2. Evaluation Context 생성 context = EvaluationContext( input_text="2023년 노벨 물리학상 수상자는 누구인가요?", output_text="2023년 노벨 물리학상은 Pierre Agostini, Ferenc Krausz, Anne L'Huillier가 수상했습니다.", retrieved_context=[ "The 2023 Nobel Prize in Physics was awarded to Pierre Agostini, Ferenc Krausz, and Anne L'Huillier.", "They were recognized for experimental methods that generate attosecond pulses of light." ] ) # 3. Ragas 평가 실행 results = ragas.evaluate(context) # 4. Faithfulness 결과 확인 print(f"Faithfulness: {results['ragas_faithfulness']:.3f}") print(f"Answer Relevancy: {results['ragas_answer_relevancy']:.3f}") print(f"Context Precision: {results['ragas_context_precision']:.3f}") print(f"Overall Score: {results['ragas_overall_score']:.3f}") print(f"Quality Level: {results['ragas_quality']}") 

### 방법 3: 프로덕션 RAG 품질 모니터링 (샘플링)

실시간 RAG 시스템에서 비용을 절감하면서 Faithfulness를 지속적으로 모니터링합니다.

import random from agent_evaluator import HybridPerformanceMonitor, create_taskresult class ProductionRAGMonitor: def __init__(self, sample_rate: float = 0.10, faithfulness_threshold: float = 0.7): """ 프로덕션 RAG 시스템 Faithfulness 모니터 Args: sample_rate: 평가 샘플링 비율 (10% = 0.10) faithfulness_threshold: Faithfulness 경고 임계값 """ self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o-mini" ) self.sample_rate = sample_rate self.threshold = faithfulness_threshold def track_rag_query(self, query_id: str, question: str, answer: str, retrieved_contexts: list) -> dict: """RAG 쿼리 추적 및 샘플링 평가""" # 샘플링 결정 (10% 확률로 Ragas 평가) should_evaluate = random.random() < self.sample_rate if should_evaluate: task = create_taskresult(query_id, "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=question, output_text=answer, retrieved_context=retrieved_contexts ) # Faithfulness Score 확인 latest = self.monitor.extended_tasks[-1] faithfulness = latest.advanced_metrics.get('ragas_faithfulness', 1.0) # 낮은 Faithfulness 감지 시 알림 if faithfulness < self.threshold: self._alert_low_faithfulness(query_id, faithfulness, question, answer) return { 'evaluated': True, 'faithfulness': faithfulness, 'alert_triggered': faithfulness < self.threshold } else: return {'evaluated': False} def _alert_low_faithfulness(self, query_id: str, score: float, question: str, answer: str): """낮은 Faithfulness 알림""" print(f""" 🚨 낮은 Faithfulness 감지! Query ID: {query_id} Faithfulness Score: {score:.3f} (Threshold: {self.threshold}) Question: {question} Answer: {answer[:200]}... 권장 조치: 1\. 검색 품질 개선 (top_k 조정, 검색 알고리즘 개선) 2\. LLM 프롬프트 개선 (컨텍스트 준수 강조) 3\. 해당 쿼리를 Human Review 대기열에 추가 """) def generate_weekly_report(self) -> dict: """주간 Faithfulness 리포트""" tasks = self.monitor.extended_tasks faithfulness_scores = [ t.advanced_metrics.get('ragas_faithfulness') for t in tasks if 'ragas_faithfulness' in t.advanced_metrics ] if not faithfulness_scores: return {'error': 'No data available'} return { 'total_evaluated': len(faithfulness_scores), 'avg_faithfulness': sum(faithfulness_scores) / len(faithfulness_scores), 'min_faithfulness': min(faithfulness_scores), 'max_faithfulness': max(faithfulness_scores), 'low_faithfulness_count': sum(1 for s in faithfulness_scores if s < self.threshold), 'low_faithfulness_rate': sum(1 for s in faithfulness_scores if s < self.threshold) / len(faithfulness_scores) } # 사용 예시 monitor = ProductionRAGMonitor( sample_rate=0.10, # 10% 샘플링 → 비용 90% 절감 faithfulness_threshold=0.7 ) # RAG 쿼리마다 호출 result = monitor.track_rag_query( query_id="rag_001", question="신제품의 보증 기간은 얼마나 되나요?", answer="신제품의 보증 기간은 2년입니다.", retrieved_contexts=["본 제품은 구매일로부터 2년간 무상 보증됩니다."] ) # 주간 리포트 생성 weekly = monitor.generate_weekly_report() print(f"주간 평균 Faithfulness: {weekly['avg_faithfulness']:.3f}") print(f"낮은 Faithfulness 비율: {weekly['low_faithfulness_rate']*100:.1f}%") 

### 방법 4: A/B 테스트 - RAG 구성 비교

서로 다른 RAG 구성(검색 알고리즘, chunk 크기, top_k 등)의 Faithfulness를 비교합니다.

from agent_evaluator import HybridPerformanceMonitor, create_taskresult from dataclasses import dataclass from typing import List @dataclass class RAGConfig: name: str chunk_size: int top_k: int search_algorithm: str class RAGABTest: def __init__(self, test_queries: List[tuple]): """ Args: test_queries: [(query, expected_answer, ground_truth_contexts), ...] """ self.test_queries = test_queries self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o" # A/B 테스트에는 고정밀 모델 사용 ) def test_rag_config(self, config: RAGConfig, rag_system) -> dict: """특정 RAG 구성의 Faithfulness 측정""" faithfulness_scores = [] for i, (query, expected, _) in enumerate(self.test_queries): # RAG 시스템으로 검색 + 생성 retrieved = rag_system.retrieve(query, config) answer = rag_system.generate(query, retrieved, config) # Faithfulness 평가 task = create_taskresult(f"{config.name}_q{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved ) latest = self.monitor.extended_tasks[-1] faithfulness = latest.advanced_metrics.get('ragas_faithfulness', 0.0) faithfulness_scores.append(faithfulness) return { 'config_name': config.name, 'avg_faithfulness': sum(faithfulness_scores) / len(faithfulness_scores), 'min_faithfulness': min(faithfulness_scores), 'scores': faithfulness_scores } def compare_configs(self, configs: List[RAGConfig], rag_system) -> dict: """여러 RAG 구성 비교""" results = [] for config in configs: print(f"\n테스트 중: {config.name}...") result = self.test_rag_config(config, rag_system) results.append(result) print(f" 평균 Faithfulness: {result['avg_faithfulness']:.3f}") # 최고 성능 구성 선택 best = max(results, key=lambda x: x['avg_faithfulness']) return { 'all_results': results, 'best_config': best['config_name'], 'best_avg_faithfulness': best['avg_faithfulness'] } # 사용 예시 test_queries = [ ("파이썬 3.11의 주요 기능은?", "...", None), ("FastAPI의 성능은?", "...", None), # ... 더 많은 테스트 쿼리 ] ab_test = RAGABTest(test_queries) configs = [ RAGConfig("small_chunks", chunk_size=256, top_k=5, search_algorithm="cosine"), RAGConfig("large_chunks", chunk_size=1024, top_k=3, search_algorithm="cosine"), RAGConfig("hybrid_search", chunk_size=512, top_k=5, search_algorithm="hybrid") ] comparison = ab_test.compare_configs(configs, my_rag_system) print(f"\n🏆 최고 성능: {comparison['best_config']}") print(f" 평균 Faithfulness: {comparison['best_avg_faithfulness']:.3f}") 

## 💡 Best Practices

### 1\. Threshold 설정 전략

도메인 | 권장 Threshold | 이유  
---|---|---  
의료, 법률, 금융 | **≥ 0.9** | 고위험 분야, 사실 오류 시 심각한 결과 초래  
교육, 기술 문서 | **≥ 0.8** | 정확성 중요, 일부 일반화 허용  
고객 지원, FAQ | **≥ 0.7** | 정확성과 유연성 균형  
일반 대화, 브레인스토밍 | **≥ 0.5** | 창의성 허용, 낮은 리스크  
  
### 2\. 비용 최적화 전략

  * **샘플링 사용** : 프로덕션에서 10-20% 샘플링으로 비용 80-90% 절감
  * **모델 선택** : 일반 평가는 gpt-4o-mini (저렴), 중요 평가는 gpt-4o (고정밀)
  * **배치 평가** : 실시간 대신 야간 배치로 평가하여 부하 분산
  * **캐싱** : 동일 컨텍스트 재평가 방지 (결과 캐싱)

### ⚠️ 주의사항

  * **컨텍스트 필수** : `retrieved_context`가 없으면 Faithfulness를 평가할 수 없음
  * **LLM 의존성** : GPT 모델 API 비용 및 latency 고려 필요
  * **완벽하지 않음** : LLM 기반 평가이므로 100% 정확도는 아님 (주기적 Human Review 필요)
  * **언어 제한** : 영어 최적화, 다른 언어는 성능이 낮을 수 있음
  * **컨텍스트 품질** : 검색된 컨텍스트 자체가 부정확하면 Faithfulness도 낮아짐

### 3\. Faithfulness 개선 방법

  1. **검색 품질 향상**
     * Embedding 모델 개선 (ada-002 → text-embedding-3-large)
     * Hybrid search 사용 (Semantic + Keyword)
     * Re-ranking 모델 추가 (Cohere Rerank, Cross-Encoder)
  2. **프롬프트 엔지니어링**
     * "컨텍스트에 없는 내용은 답변하지 마세요" 명시
     * Few-shot examples로 컨텍스트 준수 학습
     * Chain-of-Thought로 근거 기반 추론 유도
  3. **LLM 파라미터 조정**
     * Temperature 낮추기 (0.3 이하) → 보수적 답변
     * Top-p 낮추기 (0.8 이하) → 확신 있는 답변만
  4. **후처리 필터링**
     * Faithfulness < threshold인 답변 차단
     * "검색된 문서에서 답을 찾을 수 없습니다" 대체 응답

## 🎯 활용 예시

### 예시 1: 의료 Q&A 시스템 (고신뢰도 요구)

from agent_evaluator import HybridPerformanceMonitor, create_taskresult class MedicalRAGSystem: def __init__(self): self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o" # 의료는 고정밀 모델 필수 ) self.faithfulness_threshold = 0.9 # 엄격한 기준 def answer_medical_query(self, query: str) -> dict: """의료 질문에 대한 안전한 답변 생성""" # 1. 의료 문서 DB에서 검색 retrieved_docs = self.medical_db.search(query, top_k=5) contexts = [doc.content for doc in retrieved_docs] # 2. LLM 답변 생성 answer = self.llm.generate( prompt=f"""당신은 의료 정보 제공 AI입니다. 질문: {query} 참고 문서: {contexts} **중요**: 반드시 참고 문서에 근거하여 답변하세요. 근거가 불확실하면 "제공된 문서에서 확인할 수 없습니다"라고 답하세요. """ ) # 3. Faithfulness 평가 task = create_taskresult("medical_query", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=contexts ) latest = self.monitor.extended_tasks[-1] faithfulness = latest.advanced_metrics.get('ragas_faithfulness', 0.0) # 4. Safety Gate - 낮은 Faithfulness 차단 if faithfulness < self.faithfulness_threshold: return { 'answer': "죄송합니다. 해당 질문에 대해 신뢰할 수 있는 답변을 제공할 수 없습니다. 전문의와 상담하시기 바랍니다.", 'faithfulness': faithfulness, 'blocked': True, 'reason': f'Faithfulness too low ({faithfulness:.3f} < {self.faithfulness_threshold})' } return { 'answer': answer, 'faithfulness': faithfulness, 'blocked': False, 'source_documents': [doc.metadata for doc in retrieved_docs] } # 사용 medical_rag = MedicalRAGSystem() result = medical_rag.answer_medical_query("당뇨병 환자가 메트포르민을 복용할 때 주의사항은?") if not result['blocked']: print(f"답변: {result['answer']}") print(f"Faithfulness: {result['faithfulness']:.3f}") else: print(f"답변 차단됨: {result['reason']}") 

### 예시 2: 기업 내부 문서 검색 시스템

from agent_evaluator import HybridPerformanceMonitor, create_taskresult import json class EnterpriseKnowledgeBase: def __init__(self, sample_rate: float = 0.15): self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o-mini" ) self.sample_rate = sample_rate self.low_faithfulness_log = [] def query_knowledge_base(self, employee_id: str, query: str) -> dict: """기업 내부 문서 검색 및 답변""" # 문서 검색 retrieved = self.vector_db.search(query, filters={'department': employee_id}) contexts = [doc.content for doc in retrieved] # LLM 답변 answer = self.llm.generate(query, contexts) # 샘플링 평가 (15%) if random.random() < self.sample_rate: task = create_taskresult(f"kb_{employee_id}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=contexts ) latest = self.monitor.extended_tasks[-1] faithfulness = latest.advanced_metrics.get('ragas_faithfulness') # 낮은 Faithfulness 로깅 if faithfulness < 0.7: self.low_faithfulness_log.append({ 'timestamp': datetime.now().isoformat(), 'employee_id': employee_id, 'query': query, 'answer': answer, 'faithfulness': faithfulness, 'contexts': contexts }) # Slack 알림 self.send_slack_alert(f"Low Faithfulness detected: {faithfulness:.3f}") return {'answer': answer, 'sources': [doc.metadata['title'] for doc in retrieved]} def generate_monthly_report(self) -> dict: """월간 Faithfulness 리포트""" tasks = self.monitor.extended_tasks scores = [t.advanced_metrics.get('ragas_faithfulness') for t in tasks if 'ragas_faithfulness' in t.advanced_metrics] report = { 'month': datetime.now().strftime('%Y-%m'), 'total_evaluated': len(scores), 'avg_faithfulness': sum(scores) / len(scores) if scores else 0, 'low_faithfulness_incidents': len(self.low_faithfulness_log), 'incident_details': self.low_faithfulness_log } # JSON 리포트 저장 with open(f'faithfulness_report_{report["month"]}.json', 'w') as f: json.dump(report, f, indent=2, ensure_ascii=False) return report 

### 예시 3: 실시간 Faithfulness Dashboard

from agent_evaluator import HybridPerformanceMonitor, create_taskresult from collections import deque import time class FaithfulnessLiveMonitor: """실시간 Faithfulness 모니터링 Dashboard""" def __init__(self, window_size: int = 100): self.monitor = HybridPerformanceMonitor(use_ragas=True) self.recent_scores = deque(maxlen=window_size) self.alert_count = 0 def track_query(self, query_id: str, query: str, answer: str, contexts: list): """쿼리 추적 및 실시간 메트릭 업데이트""" task = create_taskresult(query_id, "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=contexts ) latest = self.monitor.extended_tasks[-1] faithfulness = latest.advanced_metrics.get('ragas_faithfulness', 0.0) self.recent_scores.append({ 'timestamp': time.time(), 'query_id': query_id, 'faithfulness': faithfulness }) if faithfulness < 0.6: self.alert_count += 1 def get_dashboard_metrics(self) -> dict: """Dashboard용 실시간 메트릭""" if not self.recent_scores: return {'error': 'No data'} scores = [s['faithfulness'] for s in self.recent_scores] return { 'current_avg': sum(scores) / len(scores), 'current_min': min(scores), 'current_max': max(scores), 'last_5_avg': sum(scores[-5:]) / min(5, len(scores)), 'alert_count': self.alert_count, 'total_queries': len(self.recent_scores), 'low_faithfulness_rate': sum(1 for s in scores if s < 0.6) / len(scores) } def print_dashboard(self): """콘솔 Dashboard 출력""" metrics = self.get_dashboard_metrics() print(f""" ╔══════════════════════════════════════════════════════════╗ ║ Faithfulness Live Dashboard ║ ╠══════════════════════════════════════════════════════════╣ ║ Current Avg: {metrics['current_avg']:.3f} ║ ║ Last 5 Avg: {metrics['last_5_avg']:.3f} ║ ║ Min/Max: {metrics['current_min']:.3f} / {metrics['current_max']:.3f} ║ ║ Alert Count: {metrics['alert_count']} ║ ║ Total Queries: {metrics['total_queries']} ║ ║ Low Faith Rate: {metrics['low_faithfulness_rate']*100:.1f}% ║ ╚══════════════════════════════════════════════════════════╝ """) # 사용 dashboard = FaithfulnessLiveMonitor(window_size=100) # 주기적으로 Dashboard 출력 (별도 스레드) import threading def dashboard_loop(): while True: dashboard.print_dashboard() time.sleep(10) # 10초마다 업데이트 threading.Thread(target=dashboard_loop, daemon=True).start() 

## 🔗 관련 메트릭

메트릭 | 관계 | 설명  
---|---|---  
**Context Precision** | 보완 관계 | 검색된 컨텍스트의 관련성 평가 (입력 측면)  
Faithfulness는 출력의 사실성 평가 (출력 측면)  
**Context Recall** | 보완 관계 | 검색된 컨텍스트의 완전성 평가  
Faithfulness는 생성된 답변의 근거 평가  
**Answer Relevancy (Ragas)** | 독립적 | 답변과 질문의 관련성 평가  
Faithfulness는 답변과 컨텍스트의 일치성 평가  
**Hallucination (DeepEval)** | 유사 (다른 구현) | DeepEval의 환각 탐지 메트릭  
Faithfulness와 동일 목적이지만 평가 방법 상이  
**Hallucination Detector (Native)** | 보완 관계 | Layer 1 간단한 환각 탐지 (휴리스틱 기반)  
Faithfulness는 LLM 기반 정교한 평가  
  
#### 💡 메트릭 조합 전략

**RAG 시스템 품질 보장** \- 3가지 Ragas 메트릭 함께 사용:

  * **Context Precision** (높을수록 좋음): 검색 품질
  * **Faithfulness** (높을수록 좋음): 생성 품질
  * **Answer Relevancy** (높을수록 좋음): 전체 품질

→ 3가지 모두 0.8 이상이면 **고품질 RAG 시스템**

## 📚 참고 자료

  * [Ragas Faithfulness 공식 문서](<https://docs.ragas.io/en/latest/concepts/metrics/faithfulness.html>)
  * [RAGAS: Automated Evaluation of RAG (논문)](<https://arxiv.org/abs/2309.15217>)
  * [Agent Evaluator RAG 평가 예시](<../examples/rag_evaluation.py>)
  * [Answer Relevancy (Ragas) 문서](<./23_ANSWER_RELEVANCY_RAGAS.html>)
  * [Context Precision 문서](<./24_CONTEXT_PRECISION.html>)
  * [Context Recall 문서](<./25_CONTEXT_RECALL.html>)

**Agent Evaluator v0.5.1** \- Layer 3 Ragas Metrics

Faithfulness: RAG 시스템의 사실적 일관성 평가

Developed by Agent Evaluator Team | [GitHub](<https://github.com/your-repo/agent-evaluator>)
