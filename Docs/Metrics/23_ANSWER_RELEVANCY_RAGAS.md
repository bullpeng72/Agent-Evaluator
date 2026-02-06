# 📊 Answer Relevancy

Ragas RAG 평가 메트릭 - 답변 관련성 (Answer-Question Relevance)

Agent Evaluator v0.5.0

Ragas Layer 3 RAG Evaluation

## 📋 개요

**Answer Relevancy** 는 Ragas 라이브러리에서 제공하는 RAG(Retrieval-Augmented Generation) 시스템 전용 평가 메트릭으로, **LLM이 생성한 답변이 사용자의 질문과 얼마나 관련성이 있는지** 를 측정합니다.

  


이 메트릭은 답변에서 역질문(Reverse Question)을 생성한 후, 원래 질문과의 유사도를 계산하여 답변이 질문에 직접적으로 답하고 있는지 평가합니다. **불필요한 정보나 주제 이탈을 탐지** 하는 핵심 메트릭으로, RAG 시스템이 사용자 의도에 맞는 답변을 생성하는지 확인합니다.

### 🎯 비즈니스 임팩트

  * **사용자 만족도** : 질문과 관련 없는 답변으로 인한 불만 감소
  * **대화 효율성** : 불필요한 정보 제거로 대화 흐름 개선
  * **신뢰성 향상** : 명확하고 직접적인 답변으로 시스템 신뢰도 증가
  * **비용 절감** : 불필요한 토큰 생성 방지로 LLM API 비용 절감

## 📊 다이어그램 시각화

### 1️⃣ 핵심 개념 및 관련성 평가 (Ragas)
```python
    graph TD
        A[Question + Answer] --> B[AnswerRelevancy Metric  
    Ragas Framework]
        B --> C[LLM Judge  
    gpt-4o-mini]
    
        C --> D[Relevancy Analysis]
        D --> E[1. 질문에 직접 답변?]
        D --> F[2. 완전한 답변?]
        D --> G[3. 간결한가?]
        D --> H[4. 불필요한 정보 없음?]
    
        E --> I[Relevancy Score Calculation]
        F --> I
        G --> I
        H --> I
    
        I --> J[Answer Relevancy 0-1  
    1 = Perfectly Relevant]
    
        J --> K{Quality Level}
        K -->|≥ 0.90| L[Excellent: 매우 관련성 높음]
        K -->|0.75-0.89| M[Good: 관련성 있음]
        K -->|0.60-0.74| N[Moderate: 부분 관련]
        K -->|< 0.60| O[Poor: 관련성 낮음]
    
        style A fill:#e1f5ff
        style J fill:#fff3cd
        style L fill:#d4edda
        style O fill:#f8d7da
        
```

### 2️⃣ 평가 파이프라인 (Ragas vs DeepEval 비교)
```python
    graph LR
        A[Answer Relevancy] --> B[Ragas Implementation  
    Metric 23]
        A --> C[DeepEval Implementation  
    Metric 18]
    
        B --> D[Ragas Framework  
    RAG-focused]
        D --> E[4-metric suite  
    일관된 평가]
        E --> F[RAG 시스템 전용  
    Context 고려]
    
        C --> G[DeepEval Framework  
    General QA]
        G --> H[독립 메트릭  
    유연한 사용]
        H --> I[범용 QA 시스템  
    Context 선택적]
    
        F --> J[Use Case:  
    RAG 파이프라인  
    통합 평가 필요]
        I --> K[Use Case:  
    Chatbot, FAQ  
    단순 QA]
    
        J --> L[같은 목적, 다른 프레임워크  
    점수 범위: 0-1 동일]
        K --> L
    
        style A fill:#e1f5ff
        style B fill:#cfe2ff
        style C fill:#fff3cd
        style L fill:#d4edda
        
```

### 3️⃣ 비용 및 프레임워크 선택
```python
    graph TD
        A[Answer Relevancy 평가] --> B{시스템 유형}
    
        B -->|RAG System| C[Ragas 권장  
    Metric 23]
        B -->|General QA| D[DeepEval 권장  
    Metric 18]
        B -->|둘 다 사용 가능| E[Ragas 우선  
    더 많은 메트릭]
    
        C --> F[Cost: $0.01-0.02/eval  
    4 metrics 함께 사용  
    Total: $0.04-0.08/eval]
        D --> G[Cost: $0.01-0.02/eval  
    단독 사용  
    유연한 비용]
        E --> F
    
        F --> H[1000 evals/day:  
    $40-80/day  
    $1200-2400/month]
        G --> I[1000 evals/day:  
    $10-20/day  
    $300-600/month]
    
        H --> J[ROI: RAG 품질 보증  
    4개 메트릭 통합 분석]
        I --> K[ROI: 비용 효율적  
    단일 메트릭 검증]
    
        style A fill:#e1f5ff
        style H fill:#ffc107
        style I fill:#d4edda
        
```

### 4️⃣ 임계값 및 최적화 가이드
```python
    graph TD
        A[Relevancy Score  
    Ragas] --> B{임계값 비교}
        B -->|≥ 0.90| C[🌟 Excellent  
    Highly Relevant]
        B -->|0.75-0.89| D[✅ Good  
    Relevant]
        B -->|0.60-0.74| E[⚠️ Moderate  
    Partially Relevant]
        B -->|< 0.60| F[❌ Poor  
    Not Relevant]
    
        C --> G[권장: 현재 품질 유지  
    4개 메트릭 균형 유지]
        D --> H[권장: 0.90 목표  
    프롬프트 최적화]
        E --> I[권장: Answer 간결성  
    불필요 정보 제거]
        F --> J[권장: 즉시 개선  
    QA 파이프라인 재설계]
    
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
Lines 449, 457 (answer_relevancy 메트릭 선택)  
**외부 라이브러리** | Ragas (`ragas.metrics.answer_relevancy`)  
**반환 키** | `ragas_answer_relevancy`  
  
## ⚙️ 평가 원리

### Step 1: 역질문(Reverse Question) 생성

LLM을 사용하여 답변으로부터 여러 개의 가능한 질문을 역으로 생성합니다.

Answer: "파이썬 3.11은 2022년 10월에 출시되었으며, 이전 버전보다 10-60% 빠릅니다." → Generated Questions: 1\. "파이썬 3.11은 언제 출시되었나요?" 2\. "파이썬 3.11의 성능은 얼마나 개선되었나요?" 3\. "파이썬 3.11의 주요 특징은 무엇인가요?"

### Step 2: 질문 유사도 계산

원래 질문과 생성된 역질문들 간의 임베딩 유사도를 계산합니다.

Original Question: "파이썬 3.11의 성능 개선 사항은 무엇인가요?" Similarity Scores: Q1 vs Original: 0.75 Q2 vs Original: 0.95 ✅ (높은 유사도 - 답변이 질문과 관련됨) Q3 vs Original: 0.82

### Step 3: Score 계산

Answer Relevancy Score = Mean(Cosine Similarity 점수들) 예시: (0.75 + 0.95 + 0.82) / 3 = 0.84 (높은 관련성)

#### 📊 Score 해석 가이드

  * 0.9 ~ 1.0: 완벽한 관련성 (Excellent)
  * 0.7 ~ 0.89: 양호한 관련성 (Good)
  * 0.5 ~ 0.69: 일부 관련 있음 (Acceptable with caution)
  * < 0.5: 관련성 낮음 (Poor - 수정 필요)

**⚠️ 방향 주의:** 높을수록 좋음 (1.0 = 답변이 질문과 완벽하게 관련됨)

## 🔧 메서드 상세

### RagasAdapter.evaluate() - Answer Relevancy 평가

**소스 코드** (metric_adapters.py Lines 420-534):

def evaluate(self, context: EvaluationContext) -> Dict[str, Any]: """Evaluate using Ragas RAG metrics""" if not self._available: return {} # Only evaluate RAG tasks with retrieved context if not context.retrieved_context: return {} results = {} try: from datasets import Dataset # Prepare data in Ragas format data = { 'question': [context.input_text], 'answer': [context.output_text], 'contexts': [context.retrieved_context] } # Select metrics based on available data if context.expected_output: data['ground_truth'] = [context.expected_output] metrics = [ self.faithfulness, self.answer_relevancy, # ← Answer Relevancy 메트릭 self.context_recall, self.context_precision ] else: # Skip context_recall when no ground_truth available metrics = [ self.faithfulness, self.answer_relevancy, # ← Answer Relevancy 메트릭 (항상 포함) self.context_precision ] dataset = Dataset.from_dict(data) # Set LLM for all metrics for metric in metrics: if hasattr(metric, 'llm'): metric.llm = self.llm eval_result = self.evaluate_fn( dataset, metrics=metrics ) # Extract Answer Relevancy score import math for metric_name in ['faithfulness', 'answer_relevancy', 'context_recall', 'context_precision']: try: value_list = eval_result[metric_name] if isinstance(value_list, (list, tuple)) and len(value_list) > 0: value = value_list[0] else: value = value_list if value is not None and isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)): results[f'ragas_{metric_name}'] = float(value) except (KeyError, IndexError, TypeError, AttributeError, ValueError): continue # Calculate overall Ragas score numeric_metrics = {k: v for k, v in results.items() if isinstance(v, (int, float)) and not isinstance(v, bool)} if numeric_metrics: results['ragas_overall_score'] = sum(numeric_metrics.values()) / len(numeric_metrics) except Exception as e: import traceback print(f"⚠️ Ragas unexpected error: {e}") results['ragas_error'] = f"Unexpected error: {str(e)}" return results

#### 🔑 핵심 포인트

  * **자동 트리거** : `retrieved_context`가 제공되면 Answer Relevancy가 자동 평가됨
  * **Ground Truth 불필요** : `expected_output` 없이도 평가 가능 (answer vs question 비교)
  * **LLM 기반** : GPT-4o-mini 또는 GPT-4o를 사용하여 역질문 생성 및 유사도 계산
  * **Overall Score 포함** : 다른 Ragas 메트릭과 평균화되어 `ragas_overall_score`에 반영

## 📊 데이터 수집 방법

### 방법 1: HybridPerformanceMonitor 자동 평가 (권장)

RAG 시스템에서 `retrieved_context`만 제공하면 Answer Relevancy가 자동으로 평가됩니다.

from agent_evaluator import HybridPerformanceMonitor, create_taskresult # 1. Monitor 초기화 (Ragas 활성화) monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o-mini" # 비용 절감 ) # 2. RAG 시스템 실행 user_query = "FastAPI의 성능 벤치마크는 어떻게 되나요?" # Vector DB에서 컨텍스트 검색 retrieved_docs = vector_db.search(user_query, top_k=3) retrieved_context = [doc.content for doc in retrieved_docs] # LLM 답변 생성 llm_response = llm.generate( prompt=f"Question: {user_query}\n\nContext: {retrieved_context}", context=retrieved_context ) # 3. Task 기록 (Answer Relevancy 자동 평가) task = create_taskresult( task_id="rag_query_002", task_type="qa", success=True, completion_score=1.0 ) monitor.record_task( task=task, enable_advanced_metrics=True, # Ragas 활성화 input_text=user_query, output_text=llm_response, retrieved_context=retrieved_context # ← Answer Relevancy 트리거 ) # 4. Answer Relevancy Score 확인 latest_task = monitor.extended_tasks[-1] answer_relevancy = latest_task.advanced_metrics.get('ragas_answer_relevancy') overall = latest_task.advanced_metrics.get('ragas_overall_score') print(f"Answer Relevancy Score: {answer_relevancy:.3f}") print(f"Ragas Overall Score: {overall:.3f}") if answer_relevancy < 0.7: print(f"⚠️ 경고: 낮은 Answer Relevancy 감지 - 답변이 질문과 관련성 낮음") 

### 방법 2: RagasAdapter 독립 사용 (고급)

Ragas 메트릭만 단독으로 평가하고 싶을 때 사용합니다.

from agent_evaluator.integrations.metric_adapters import ( RagasAdapter, EvaluationContext ) # 1. Adapter 초기화 ragas = RagasAdapter(llm_model="gpt-4o-mini") # 2. Evaluation Context 생성 context = EvaluationContext( input_text="딥러닝 모델의 학습 속도를 높이는 방법은?", output_text="딥러닝 모델의 학습 속도를 높이려면 배치 크기를 늘리고, mixed precision training을 사용하며, gradient accumulation을 적용할 수 있습니다. 또한 더 강력한 GPU를 사용하는 것도 효과적입니다.", retrieved_context=[ "To speed up deep learning training, increase batch size and use mixed precision training.", "Gradient accumulation allows training with larger effective batch sizes.", "Modern GPUs like A100 significantly accelerate deep learning workloads." ] ) # 3. Ragas 평가 실행 results = ragas.evaluate(context) # 4. Answer Relevancy 결과 확인 print(f"Answer Relevancy: {results['ragas_answer_relevancy']:.3f}") print(f"Faithfulness: {results['ragas_faithfulness']:.3f}") print(f"Context Precision: {results['ragas_context_precision']:.3f}") print(f"Overall Score: {results['ragas_overall_score']:.3f}") print(f"Quality Level: {results['ragas_quality']}") 

### 방법 3: 챗봇 대화 품질 모니터링 (실시간)

고객 지원 챗봇에서 답변의 관련성을 지속적으로 모니터링합니다.

import random from agent_evaluator import HybridPerformanceMonitor, create_taskresult from datetime import datetime class ChatbotQualityMonitor: def __init__(self, sample_rate: float = 0.20, relevancy_threshold: float = 0.7): """ 챗봇 대화 품질 모니터 Args: sample_rate: 평가 샘플링 비율 (20% = 0.20) relevancy_threshold: Answer Relevancy 경고 임계값 """ self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o-mini" ) self.sample_rate = sample_rate self.threshold = relevancy_threshold self.low_relevancy_conversations = [] def track_conversation(self, conversation_id: str, user_message: str, bot_response: str, retrieved_contexts: list) -> dict: """대화 추적 및 샘플링 평가""" # 샘플링 결정 (20% 확률로 Ragas 평가) should_evaluate = random.random() < self.sample_rate if should_evaluate: task = create_taskresult(conversation_id, "chat", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=user_message, output_text=bot_response, retrieved_context=retrieved_contexts ) # Answer Relevancy Score 확인 latest = self.monitor.extended_tasks[-1] answer_relevancy = latest.advanced_metrics.get('ragas_answer_relevancy', 1.0) # 낮은 Answer Relevancy 감지 시 알림 if answer_relevancy < self.threshold: self._log_low_relevancy(conversation_id, answer_relevancy, user_message, bot_response) return { 'evaluated': True, 'answer_relevancy': answer_relevancy, 'alert_triggered': answer_relevancy < self.threshold } else: return {'evaluated': False} def _log_low_relevancy(self, conv_id: str, score: float, user_msg: str, bot_response: str): """낮은 Answer Relevancy 로깅""" incident = { 'timestamp': datetime.now().isoformat(), 'conversation_id': conv_id, 'answer_relevancy': score, 'user_message': user_msg, 'bot_response': bot_response } self.low_relevancy_conversations.append(incident) print(f""" ⚠️ 낮은 Answer Relevancy 감지! Conversation ID: {conv_id} Answer Relevancy Score: {score:.3f} (Threshold: {self.threshold}) User: {user_msg} Bot: {bot_response[:200]}... 권장 조치: 1\. 프롬프트 개선 (질문에 직접 답하도록 명시) 2\. 검색 품질 개선 (더 관련성 높은 컨텍스트 검색) 3\. 답변 후처리 (불필요한 정보 제거) """) def generate_daily_report(self) -> dict: """일일 Answer Relevancy 리포트""" tasks = self.monitor.extended_tasks relevancy_scores = [ t.advanced_metrics.get('ragas_answer_relevancy') for t in tasks if 'ragas_answer_relevancy' in t.advanced_metrics ] if not relevancy_scores: return {'error': 'No data available'} return { 'date': datetime.now().strftime('%Y-%m-%d'), 'total_evaluated': len(relevancy_scores), 'avg_answer_relevancy': sum(relevancy_scores) / len(relevancy_scores), 'min_answer_relevancy': min(relevancy_scores), 'max_answer_relevancy': max(relevancy_scores), 'low_relevancy_count': len(self.low_relevancy_conversations), 'low_relevancy_rate': len(self.low_relevancy_conversations) / len(relevancy_scores), 'incidents': self.low_relevancy_conversations } # 사용 예시 monitor = ChatbotQualityMonitor( sample_rate=0.20, # 20% 샘플링 → 비용 80% 절감 relevancy_threshold=0.7 ) # 챗봇 대화마다 호출 result = monitor.track_conversation( conversation_id="chat_001", user_message="배송 추적은 어떻게 하나요?", bot_response="배송 추적은 주문 번호를 입력하면 확인하실 수 있습니다. 웹사이트 상단의 '배송 조회' 메뉴를 클릭하세요.", retrieved_contexts=["고객은 주문 번호로 배송 상태를 확인할 수 있습니다."] ) # 일일 리포트 생성 daily = monitor.generate_daily_report() print(f"일일 평균 Answer Relevancy: {daily['avg_answer_relevancy']:.3f}") print(f"낮은 Answer Relevancy 비율: {daily['low_relevancy_rate']*100:.1f}%") 

### 방법 4: 프롬프트 A/B 테스트

서로 다른 프롬프트의 Answer Relevancy를 비교하여 최적 프롬프트를 찾습니다.

from agent_evaluator import HybridPerformanceMonitor, create_taskresult from typing import List, Dict class PromptABTest: def __init__(self, test_queries: List[str]): """ Args: test_queries: 테스트용 질문 리스트 """ self.test_queries = test_queries self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o" # A/B 테스트에는 고정밀 모델 사용 ) def test_prompt_template(self, prompt_name: str, prompt_template: str, rag_system) -> Dict: """특정 프롬프트 템플릿의 Answer Relevancy 측정""" relevancy_scores = [] for i, query in enumerate(self.test_queries): # RAG 시스템으로 검색 + 생성 retrieved = rag_system.retrieve(query) answer = rag_system.generate(query, retrieved, prompt_template) # Answer Relevancy 평가 task = create_taskresult(f"{prompt_name}_q{i}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=retrieved ) latest = self.monitor.extended_tasks[-1] relevancy = latest.advanced_metrics.get('ragas_answer_relevancy', 0.0) relevancy_scores.append(relevancy) return { 'prompt_name': prompt_name, 'avg_answer_relevancy': sum(relevancy_scores) / len(relevancy_scores), 'min_answer_relevancy': min(relevancy_scores), 'scores': relevancy_scores } def compare_prompts(self, prompt_templates: Dict[str, str], rag_system) -> Dict: """여러 프롬프트 템플릿 비교""" results = [] for prompt_name, template in prompt_templates.items(): print(f"\n테스트 중: {prompt_name}...") result = self.test_prompt_template(prompt_name, template, rag_system) results.append(result) print(f" 평균 Answer Relevancy: {result['avg_answer_relevancy']:.3f}") # 최고 성능 프롬프트 선택 best = max(results, key=lambda x: x['avg_answer_relevancy']) return { 'all_results': results, 'best_prompt': best['prompt_name'], 'best_avg_relevancy': best['avg_answer_relevancy'] } # 사용 예시 test_queries = [ "파이썬 3.11의 주요 기능은?", "FastAPI의 성능은?", "딥러닝 모델 학습을 빠르게 하려면?", # ... 더 많은 테스트 쿼리 ] ab_test = PromptABTest(test_queries) prompt_templates = { "direct_answer": """질문에 직접 답변하세요. 질문: {question} 컨텍스트: {context} 답변:""", "detailed_explanation": """다음 질문에 상세하게 답변하세요. 배경 정보도 포함하세요. 질문: {question} 참고 자료: {context} 상세 답변:""", "concise_answer": """질문에 간결하게 답하세요. 핵심만 포함하세요. Q: {question} Context: {context} A:""" } comparison = ab_test.compare_prompts(prompt_templates, my_rag_system) print(f"\n🏆 최고 성능 프롬프트: {comparison['best_prompt']}") print(f" 평균 Answer Relevancy: {comparison['best_avg_relevancy']:.3f}") 

## 💡 Best Practices

### 1\. Threshold 설정 전략

도메인 | 권장 Threshold | 이유  
---|---|---  
고객 지원, FAQ | **≥ 0.8** | 질문에 직접적인 답변 필수  
기술 문서, 튜토리얼 | **≥ 0.7** | 관련성 중요하나 배경 설명 허용  
교육, 설명형 콘텐츠 | **≥ 0.6** | 부가 정보 제공 가능  
일반 대화, 브레인스토밍 | **≥ 0.5** | 창의적 답변 허용  
  
### 2\. Answer Relevancy 개선 방법

  1. **프롬프트 엔지니어링**
     * "질문에 직접 답하세요" 명시
     * "불필요한 정보는 생략하세요" 지시
     * Few-shot examples로 간결한 답변 학습
  2. **답변 길이 제한**
     * max_tokens 설정으로 장황한 답변 방지
     * "3문장 이내로 답하세요" 제약 추가
  3. **검색 품질 향상**
     * 더 관련성 높은 컨텍스트 검색 (top_k 조정)
     * Re-ranking으로 관련성 높은 문서 우선 제공
  4. **후처리 필터링**
     * Answer Relevancy < threshold인 답변 재생성
     * "더 구체적으로 질문해주세요" 안내

### ⚠️ 주의사항

  * **컨텍스트 필수** : `retrieved_context`가 없으면 Answer Relevancy를 평가할 수 없음
  * **LLM 의존성** : GPT 모델 API 비용 및 latency 고려 필요
  * **과도한 간결성 주의** : 너무 짧은 답변은 높은 점수를 받지만 사용자에게 불충분할 수 있음
  * **언어 제한** : 영어 최적화, 다른 언어는 성능이 낮을 수 있음
  * **질문 명확성** : 모호한 질문은 낮은 점수를 유발할 수 있음 (질문 품질도 중요)

### 3\. 비용 최적화 전략

  * **샘플링 사용** : 프로덕션에서 10-20% 샘플링으로 비용 80-90% 절감
  * **모델 선택** : 일반 평가는 gpt-4o-mini (저렴), 중요 평가는 gpt-4o (고정밀)
  * **배치 평가** : 실시간 대신 야간 배치로 평가하여 부하 분산
  * **캐싱** : 유사한 질문-답변 쌍 재평가 방지

## 🎯 활용 예시

### 예시 1: 고객 지원 챗봇 (높은 관련성 요구)

from agent_evaluator import HybridPerformanceMonitor, create_taskresult class CustomerSupportBot: def __init__(self): self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o-mini" ) self.relevancy_threshold = 0.8 # 고객 지원은 높은 관련성 필요 def answer_customer_query(self, customer_id: str, query: str) -> dict: """고객 질문에 대한 관련성 높은 답변 생성""" # 1. 지식베이스에서 검색 retrieved_docs = self.kb.search(query, top_k=5) contexts = [doc.content for doc in retrieved_docs] # 2. LLM 답변 생성 answer = self.llm.generate( prompt=f"""당신은 고객 지원 챗봇입니다. 고객 질문: {query} 참고 문서: {contexts} **중요**: \- 질문에 직접 답하세요 \- 불필요한 정보는 생략하세요 \- 3-4문장으로 간결하게 답하세요 """ ) # 3. Answer Relevancy 평가 task = create_taskresult(f"support_{customer_id}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=contexts ) latest = self.monitor.extended_tasks[-1] answer_relevancy = latest.advanced_metrics.get('ragas_answer_relevancy', 0.0) # 4. Quality Gate - 낮은 Answer Relevancy 차단 if answer_relevancy < self.relevancy_threshold: return { 'answer': "죄송합니다. 질문을 더 구체적으로 말씀해 주시겠어요? 예를 들어 '배송', '반품', '결제' 중 어떤 부분이 궁금하신가요?", 'answer_relevancy': answer_relevancy, 'blocked': True, 'reason': f'Answer Relevancy too low ({answer_relevancy:.3f} < {self.relevancy_threshold})' } return { 'answer': answer, 'answer_relevancy': answer_relevancy, 'blocked': False, 'source_documents': [doc.metadata for doc in retrieved_docs] } # 사용 bot = CustomerSupportBot() result = bot.answer_customer_query("cust_123", "배송 조회는 어떻게 하나요?") if not result['blocked']: print(f"답변: {result['answer']}") print(f"Answer Relevancy: {result['answer_relevancy']:.3f}") else: print(f"답변 차단됨: {result['reason']}") 

### 예시 2: 기술 문서 Q&A 시스템

from agent_evaluator import HybridPerformanceMonitor, create_taskresult import json class TechnicalDocsQA: def __init__(self, sample_rate: float = 0.10): self.monitor = HybridPerformanceMonitor( use_ragas=True, ragas_model="gpt-4o-mini" ) self.sample_rate = sample_rate self.low_relevancy_log = [] def query_technical_docs(self, developer_id: str, query: str) -> dict: """기술 문서 검색 및 답변""" # 문서 검색 retrieved = self.doc_db.search(query, filters={'type': 'technical'}) contexts = [doc.content for doc in retrieved] # LLM 답변 answer = self.llm.generate(query, contexts) # 샘플링 평가 (10%) if random.random() < self.sample_rate: task = create_taskresult(f"tech_{developer_id}", "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=contexts ) latest = self.monitor.extended_tasks[-1] answer_relevancy = latest.advanced_metrics.get('ragas_answer_relevancy') # 낮은 Answer Relevancy 로깅 if answer_relevancy < 0.7: self.low_relevancy_log.append({ 'timestamp': datetime.now().isoformat(), 'developer_id': developer_id, 'query': query, 'answer': answer, 'answer_relevancy': answer_relevancy, 'contexts': contexts }) # Slack 알림 self.send_slack_alert(f"Low Answer Relevancy detected: {answer_relevancy:.3f}") return {'answer': answer, 'sources': [doc.metadata['title'] for doc in retrieved]} def generate_weekly_report(self) -> dict: """주간 Answer Relevancy 리포트""" tasks = self.monitor.extended_tasks scores = [t.advanced_metrics.get('ragas_answer_relevancy') for t in tasks if 'ragas_answer_relevancy' in t.advanced_metrics] report = { 'week': datetime.now().strftime('%Y-W%U'), 'total_evaluated': len(scores), 'avg_answer_relevancy': sum(scores) / len(scores) if scores else 0, 'low_relevancy_incidents': len(self.low_relevancy_log), 'incident_details': self.low_relevancy_log } # JSON 리포트 저장 with open(f'answer_relevancy_report_{report["week"]}.json', 'w') as f: json.dump(report, f, indent=2, ensure_ascii=False) return report 

### 예시 3: 실시간 Answer Relevancy Dashboard

from agent_evaluator import HybridPerformanceMonitor, create_taskresult from collections import deque import time class AnswerRelevancyLiveMonitor: """실시간 Answer Relevancy 모니터링 Dashboard""" def __init__(self, window_size: int = 100): self.monitor = HybridPerformanceMonitor(use_ragas=True) self.recent_scores = deque(maxlen=window_size) self.alert_count = 0 def track_query(self, query_id: str, query: str, answer: str, contexts: list): """쿼리 추적 및 실시간 메트릭 업데이트""" task = create_taskresult(query_id, "qa", True, 1.0) self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=query, output_text=answer, retrieved_context=contexts ) latest = self.monitor.extended_tasks[-1] answer_relevancy = latest.advanced_metrics.get('ragas_answer_relevancy', 0.0) self.recent_scores.append({ 'timestamp': time.time(), 'query_id': query_id, 'answer_relevancy': answer_relevancy }) if answer_relevancy < 0.6: self.alert_count += 1 def get_dashboard_metrics(self) -> dict: """Dashboard용 실시간 메트릭""" if not self.recent_scores: return {'error': 'No data'} scores = [s['answer_relevancy'] for s in self.recent_scores] return { 'current_avg': sum(scores) / len(scores), 'current_min': min(scores), 'current_max': max(scores), 'last_5_avg': sum(scores[-5:]) / min(5, len(scores)), 'alert_count': self.alert_count, 'total_queries': len(self.recent_scores), 'low_relevancy_rate': sum(1 for s in scores if s < 0.6) / len(scores) } def print_dashboard(self): """콘솔 Dashboard 출력""" metrics = self.get_dashboard_metrics() print(f""" ╔══════════════════════════════════════════════════════════╗ ║ Answer Relevancy Live Dashboard ║ ╠══════════════════════════════════════════════════════════╣ ║ Current Avg: {metrics['current_avg']:.3f} ║ ║ Last 5 Avg: {metrics['last_5_avg']:.3f} ║ ║ Min/Max: {metrics['current_min']:.3f} / {metrics['current_max']:.3f} ║ ║ Alert Count: {metrics['alert_count']} ║ ║ Total Queries: {metrics['total_queries']} ║ ║ Low Relev Rate: {metrics['low_relevancy_rate']*100:.1f}% ║ ╚══════════════════════════════════════════════════════════╝ """) # 사용 dashboard = AnswerRelevancyLiveMonitor(window_size=100) # 주기적으로 Dashboard 출력 (별도 스레드) import threading def dashboard_loop(): while True: dashboard.print_dashboard() time.sleep(10) # 10초마다 업데이트 threading.Thread(target=dashboard_loop, daemon=True).start() 

## 🔗 관련 메트릭

메트릭 | 관계 | 설명  
---|---|---  
**Faithfulness** | 독립적 | 답변과 컨텍스트의 일치성 평가  
Answer Relevancy는 답변과 질문의 관련성 평가  
**Context Precision** | 보완 관계 | 검색된 컨텍스트의 관련성 평가 (입력 측면)  
Answer Relevancy는 생성된 답변의 관련성 (출력 측면)  
**Context Recall** | 보완 관계 | 검색된 컨텍스트의 완전성 평가  
Answer Relevancy는 답변의 적절성 평가  
**Answer Relevancy (DeepEval)** | 유사 (다른 구현) | DeepEval의 답변 관련성 메트릭  
동일 목적이지만 평가 방법 상이  
**Contextual Relevancy (DeepEval)** | 보완 관계 | 컨텍스트와 질문의 관련성 평가  
Answer Relevancy는 답변과 질문의 관련성 평가  
  
#### 💡 메트릭 조합 전략

**RAG 시스템 품질 보장** \- 3가지 Ragas 메트릭 함께 사용:

  * **Context Precision** (높을수록 좋음): 검색 품질
  * **Faithfulness** (높을수록 좋음): 사실적 일관성
  * **Answer Relevancy** (높을수록 좋음): 답변 관련성

→ 3가지 모두 0.8 이상이면 **고품질 RAG 시스템**

## 📚 참고 자료

  * [Ragas Answer Relevancy 공식 문서](<https://docs.ragas.io/en/latest/concepts/metrics/answer_relevance.html>)
  * [RAGAS: Automated Evaluation of RAG (논문)](<https://arxiv.org/abs/2309.15217>)
  * [Agent Evaluator RAG 평가 예시](<../examples/rag_evaluation.py>)
  * [Faithfulness (Ragas) 문서](<./22_FAITHFULNESS.html>)
  * [Context Precision 문서](<./24_CONTEXT_PRECISION.html>)
  * [Context Recall 문서](<./25_CONTEXT_RECALL.html>)

**Agent Evaluator v0.5.0** \- Layer 3 Ragas Metrics

Answer Relevancy: RAG 시스템의 답변 관련성 평가

Developed by Agent Evaluator Team | [GitHub](<https://github.com/your-repo/agent-evaluator>)
