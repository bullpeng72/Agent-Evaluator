# 🎯 Answer Relevancy

Question-Answer Relevance Assessment with DeepEval

Agent Evaluator v0.5.0 - Layer 3 DeepEval Metric

## 🎯 개요

**Answer Relevancy** 는 AI가 생성한 답변이 사용자의 질문과 얼마나 관련성이 있는지 평가하는 DeepEval의 QA(Question-Answering) 품질 메트릭입니다.   
  
답변이 질문의 핵심을 다루고 있는지, 불필요한 정보가 포함되어 있지 않은지를 자동으로 평가하여 질문에 직접적으로 답하는 고품질 응답을 보장합니다. 

### ⚠️ 중요성

  * **사용자 만족도** : 질문에 정확히 답하는 응답으로 사용자 경험 향상
  * **효율성** : 불필요한 정보 제거로 간결하고 명확한 답변 제공
  * **신뢰성** : 질문 회피 없이 직접적으로 답변
  * **검색 품질** : 검색 엔진, FAQ 봇 등에서 결과 품질 측정
  * **대화 품질** : 챗봇의 대화 적합성 평가

## 📊 다이어그램 시각화

### 1️⃣ 핵심 개념 및 관련성 평가 (DeepEval)
```python
    graph TD
        A[Query + Answer] --> B[AnswerRelevancyMetric  
    DeepEval]
        B --> C[LLM Judge  
    gpt-4o-mini]
    
        C --> D[질문-답변 관련성 분석]
        D --> E[Relevance Factors]
    
        E --> F[1. 질문에 직접 답변하는가?]
        E --> G[2. 정확한 정보를 포함하는가?]
        E --> H[3. 불필요한 정보는 없는가?]
        E --> I[4. 컨텍스트가 적절한가?]
    
        F --> J[Relevancy Score 0-1]
        G --> J
        H --> J
        I --> J
    
        J --> K{Quality Assessment}
        K -->|≥ 0.90| L[Excellent: 매우 관련성 높음]
        K -->|0.75-0.89| M[Good: 관련성 있음]
        K -->|0.60-0.74| N[Moderate: 부분 관련]
        K -->|< 0.60| O[Poor: 관련성 낮음]
    
        style A fill:#e1f5ff
        style J fill:#fff3cd
        style L fill:#d4edda
        style O fill:#f8d7da
        
```

### 2️⃣ 평가 파이프라인 (QA Task)
```python
    sequenceDiagram
        participant QA as QA System
        participant Adapter as DeepEvalAdapter
        participant Metric as AnswerRelevancyMetric
        participant LLM as gpt-4o-mini
    
        QA->>Adapter: evaluate(input, output, task_type='qa')
        Note over Adapter: task_type이 'qa' 또는  
    'information_retrieval'일 때만 실행
    
        Adapter->>Adapter: Create LLMTestCase  
    input=query, actual_output=answer
    
        Adapter->>Metric: AnswerRelevancyMetric(model, threshold)
        Metric->>LLM: Evaluate answer relevancy
    
        LLM->>LLM: Analyze:  
    1. Direct answer?  
    2. Accurate info?  
    3. No redundancy?  
    4. Proper context?
    
        LLM-->>Metric: Score (0-1) + Reasoning
        Metric-->>Adapter: answer_relevancy_score, reason
    
        Adapter-->>QA: {'answer_relevancy_score': 0.88, 'reason': '...'}
        
```

### 3️⃣ 비용 및 적용 범위
```python
    graph TD
        A[Answer Relevancy Config] --> B{Task Type Check}
        B -->|qa, information_retrieval| C[평가 실행]
        B -->|other types| D[평가 스킵  
    비용 절약]
    
        C --> E[Model Selection]
        E --> F[gpt-4o-mini: $0.01-0.02/eval  
    2-4 sec]
        E --> G[gpt-4o: $0.10-0.15/eval  
    3-6 sec]
    
        F --> H[Use Cases]
        G --> H
    
        H --> I[Chatbot QA  
    FAQ Systems  
    Information Retrieval  
    Document Q&A]
    
        I --> J[Cost Estimation]
        J --> K[100 QA/day:  
    mini: $1-2/day  
    4o: $10-15/day]
    
        K --> L[Monthly:  
    mini: $30-60  
    4o: $300-450]
    
        style A fill:#e1f5ff
        style J fill:#fff3cd
        style L fill:#ffc107
        
```

### 4️⃣ 임계값 및 최적화 가이드
```python
    graph TD
        A[Relevancy Score] --> B{임계값 비교}
        B -->|≥ 0.90| C[🌟 Excellent  
    Highly Relevant]
        B -->|0.75-0.89| D[✅ Good  
    Relevant]
        B -->|0.60-0.74| E[⚠️ Moderate  
    Partially Relevant]
        B -->|< 0.60| F[❌ Poor  
    Not Relevant]
    
        C --> G[권장: 현재 품질 유지  
    Best Practice 문서화]
        D --> H[권장: 0.90 목표  
    프롬프트 튜닝]
        E --> I[권장: Context 개선  
    Retrieval 최적화]
        F --> J[권장: 즉시 개선  
    모델 재학습 or RAG 개선]
    
        style C fill:#d4edda
        style D fill:#cfe2ff
        style E fill:#fff3cd
        style F fill:#f8d7da
        
```

## 📍 구현 위치

**파일:** `agent_evaluator/integrations/metric_adapters.py`  
**클래스:** `DeepEvalAdapter`  
**메서드:** `_evaluate_answer_relevancy()`  
**라인:** 321-342 

### 핵심 메서드

메서드 | 라인 | 설명  
---|---|---  
`__init__()` | 87-128 | DeepEval 어댑터 초기화  
`evaluate()` | 133-198 | 모든 DeepEval 메트릭 평가 (Answer Relevancy 포함)  
`_evaluate_answer_relevancy()` | 321-342 | 답변 관련성 메트릭 실행  
  
## 📋 Answer Relevancy 평가 원리

**Answer Relevancy** 는 다음 단계로 작동합니다:   
  


  1. **질문 분석** : 사용자의 질문(input)과 AI 답변(actual_output) 수신
  2. **의미적 정렬** : 평가용 LLM이 답변이 질문의 의도와 일치하는지 검증
  3. **불필요한 정보 탐지** : 질문과 무관한 추가 정보가 있는지 확인
  4. **완전성 검사** : 질문의 모든 부분에 답했는지 확인
  5. **Score 산출** : 0.0 ~ 1.0 범위의 점수 반환 (높을수록 관련성 높음 = 좋음)

### Answer Relevancy Score 해석

#### ⚠️ 중요: Score 방향

**DeepEval AnswerRelevancyMetric은 "관련성 점수"입니다**

  * **1.0 = 완벽 (완전 관련)** : 질문에 정확히 답함
  * **0.0 = 매우 나쁨 (무관)** : 질문과 전혀 관련 없음

Relevancy Score | 등급 | 설명 | 권장 조치  
---|---|---|---  
0.9 ~ 1.0 | **Excellent** | 매우 높은 관련성 | 현재 수준 유지  
0.7 ~ 0.89 | **Good** | 좋은 관련성 | 미세 조정 고려  
0.5 ~ 0.69 | **Acceptable** | 부분적으로 관련 | 프롬프트 개선 필요  
0.0 ~ 0.49 | **Poor** | 낮은 관련성 | 즉각적인 개선 필요  
  
### 관련성 문제의 유형

문제 유형 | 설명 | 예시  
---|---|---  
**질문 회피 (Evasion)** | 질문에 직접 답하지 않음 | Q: "가격은?" A: "품질이 우수합니다"  
**과도한 정보 (Verbosity)** | 질문과 무관한 정보 포함 | Q: "파이썬이란?" A: 파이썬 설명 + 자바 역사 + C++ 장단점  
**부분 답변 (Incompleteness)** | 질문의 일부만 답함 | Q: "장단점은?" A: "장점만 나열"  
**주제 이탈 (Off-topic)** | 완전히 다른 주제로 이탈 | Q: "머신러닝이란?" A: "데이터베이스 설명"  
**모호한 답변 (Vagueness)** | 구체적이지 않은 일반론 | Q: "사용법은?" A: "간단합니다"  
  
## ⚙️ 핵심 메서드 상세 설명

### _evaluate_answer_relevancy() - 답변 관련성 평가 실행

**목적** : 답변이 질문에 얼마나 관련되어 있는지 검증

**위치** : Lines 321-342

def _evaluate_answer_relevancy(self, test_case) -> Dict[str, Any]: """Evaluate answer relevancy""" try: # 1. AnswerRelevancyMetric 생성 metric = self.AnswerRelevancyMetric( threshold=self.threshold, # 기본: 0.5 (이 이상이면 Pass) model=self.model # 평가용 LLM (예: gpt-4o-mini) ) # 2. 평가 수행 # test_case에는 input(질문)과 actual_output(답변)이 필요 metric.measure(test_case) # 3. 결과 반환 return { 'answer_relevancy_score': metric.score, # 0.0 ~ 1.0 (높을수록 관련성 높음) 'answer_relevancy_passed': metric.score >= self.threshold # 테스트 통과? } except Exception as e: print(f"⚠️ Answer relevancy metric error: {e}") return {'answer_relevancy_error': str(e)} 

#### ✅ 평가 로직 핵심 포인트

  1. **Input과 Output 필요** : 질문과 답변 모두 필수
  2. **의미적 평가** : 단순 키워드 매칭이 아닌 LLM 기반 의미 이해
  3. **QA 작업 전용** : task_type이 'qa' 또는 'information_retrieval'일 때 주로 사용
  4. **Score 방향 주의** : 높을수록 좋음 (관련성 높음)

### DeepEvalAdapter에서 자동 트리거

**조건부 평가** : QA 타입 작업에서 자동 실행

**위치** : Lines 179-181

# DeepEvalAdapter.evaluate() 내부 # 5. Answer relevancy (for QA tasks) if context.task_type in ['qa', 'information_retrieval']: results.update(self._evaluate_answer_relevancy(test_case)) 

#### 📌 자동 평가 조건

Answer Relevancy는 다음 조건에서 **자동으로** 평가됩니다:

  * `task_type = "qa"`: 질의응답 작업
  * `task_type = "information_retrieval"`: 정보 검색 작업

다른 task_type에서는 수동으로 평가 필요합니다.

## 🔍 데이터 수집 방법 (실전 가이드)

Answer Relevancy 메트릭을 현장에서 측정하기 위한 4가지 실전 방법을 소개합니다.

### 방법 1: HybridPerformanceMonitor QA 평가 (권장)

#### 📌 사용 시기

QA 챗봇, FAQ 시스템, 정보 검색 서비스에서 답변 품질 평가

from agent_evaluator import HybridPerformanceMonitor, create_taskresult # 1. HybridPerformanceMonitor 초기화 (DeepEval 활성화) monitor = HybridPerformanceMonitor( use_deepeval=True, deepeval_model="gpt-4o-mini" ) # 2. QA 시스템 실행 user_question = "파이썬에서 리스트와 튜플의 차이점은 무엇인가요?" # 좋은 답변 예시 (관련성 높음) good_answer = """ 리스트와 튜플의 주요 차이점: 1\. 가변성: 리스트는 변경 가능(mutable), 튜플은 불변(immutable) 2\. 문법: 리스트는 [], 튜플은 () 사용 3\. 성능: 튜플이 리스트보다 약간 빠름 4\. 용도: 리스트는 동적 데이터, 튜플은 고정 데이터에 적합 """ # 나쁜 답변 예시 (관련성 낮음) bad_answer = """ 파이썬은 1991년 귀도 반 로섬이 개발한 프로그래밍 언어입니다. 파이썬은 다양한 자료구조를 제공하며, 딕셔너리와 세트도 있습니다. 객체지향 프로그래밍을 지원하며 동적 타이핑을 사용합니다. """ # 3. 답변 관련성 평가 수행 task = create_taskresult( task_id="qa_001", task_type="qa", # QA 타입 지정 → Answer Relevancy 자동 평가 success=True, completion_score=1.0 ) monitor.record_task( task=task, enable_advanced_metrics=True, # DeepEval 활성화 input_text=user_question, output_text=good_answer # 또는 bad_answer로 테스트 ) # 4. 결과 확인 if monitor.extended_tasks: latest_task = monitor.extended_tasks[-1] relevancy_score = latest_task.advanced_metrics.get('answer_relevancy_score') relevancy_passed = latest_task.advanced_metrics.get('answer_relevancy_passed') print(f"Answer Relevancy Score: {relevancy_score:.3f} (1.0 = 완전 관련)") print(f"Test Passed: {relevancy_passed}") if relevancy_score < 0.7: print("⚠️ 관련성이 낮습니다. 답변을 개선하세요.") monitor.print_summary() # 출력 예시: # 🔬 ADVANCED METRICS # Answer Relevancy: 0.920/1.0 (n=1)

**✅ Best Practice - QA 관련성 평가:**

  * **명확한 질문** : 질문이 구체적일수록 관련성 평가가 정확
  * **task_type 지정** : "qa" 또는 "information_retrieval"로 설정
  * **Threshold 조정** : FAQ는 0.7, 일반 챗봇은 0.5 권장
  * **정기 모니터링** : 관련성 낮은 답변 패턴 분석

### 방법 2: 프로덕션 QA 품질 모니터

#### 📌 사용 시기

대규모 QA 시스템에서 실시간 답변 품질 모니터링 및 낮은 관련성 답변 탐지

from agent_evaluator import HybridPerformanceMonitor, create_taskresult from datetime import datetime import random class QAQualityMonitor: """프로덕션 QA 시스템 품질 모니터링""" def __init__( self, sample_rate: float = 0.15, # 15% 샘플링 relevancy_threshold: float = 0.6 # 관련성 기준 ): self.monitor = HybridPerformanceMonitor( use_deepeval=True, deepeval_model="gpt-4o-mini" ) self.sample_rate = sample_rate self.relevancy_threshold = relevancy_threshold self.total_qa = 0 self.evaluated_qa = 0 self.low_relevancy_cases = [] def track_qa_interaction( self, qa_id: str, user_question: str, bot_answer: str, user_feedback: str = None # 선택적: 사용자 피드백 ): """QA 상호작용 추적 및 관련성 평가""" self.total_qa += 1 # 샘플링: 비용 절감 should_evaluate = random.random() < self.sample_rate if should_evaluate: self.evaluated_qa += 1 # TaskResult 생성 task = create_taskresult( task_id=qa_id, task_type="qa", # QA 타입 → Answer Relevancy 자동 success=True, completion_score=1.0 ) # 관련성 평가 수행 self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=user_question, output_text=bot_answer ) # 낮은 관련성 탐지 if self.monitor.extended_tasks: latest_task = self.monitor.extended_tasks[-1] relevancy_score = latest_task.advanced_metrics.get('answer_relevancy_score') if relevancy_score is not None and relevancy_score < self.relevancy_threshold: # 낮은 관련성 → 알림 case = { 'qa_id': qa_id, 'timestamp': datetime.now().isoformat(), 'relevancy_score': relevancy_score, 'question': user_question[:100], 'answer': bot_answer[:100], 'user_feedback': user_feedback, 'severity': 'HIGH' if relevancy_score < 0.4 else 'MEDIUM' } self.low_relevancy_cases.append(case) print(f"⚠️ [{case['severity']}] Low relevancy detected!") print(f" QA ID: {qa_id}") print(f" Score: {relevancy_score:.3f} (< {self.relevancy_threshold})") print(f" Q: {user_question[:80]}...") def get_daily_report(self): """일일 QA 품질 리포트""" low_relevancy_rate = ( len(self.low_relevancy_cases) / self.evaluated_qa * 100 if self.evaluated_qa > 0 else 0 ) print(f"\n📊 Daily QA Quality Report") print(f" Date: {datetime.now().strftime('%Y-%m-%d')}") print(f" Total QA: {self.total_qa}") print(f" Evaluated: {self.evaluated_qa} ({self.sample_rate*100:.0f}%)") print(f" Low Relevancy: {len(self.low_relevancy_cases)} ({low_relevancy_rate:.1f}%)") if self.low_relevancy_cases: print(f"\n🚨 Top 5 Low Relevancy Cases:") for i, case in enumerate(sorted( self.low_relevancy_cases, key=lambda x: x['relevancy_score'] )[:5], 1): print(f" {i}. [{case['severity']}] Score: {case['relevancy_score']:.3f}") print(f" Q: {case['question']}") print(f" A: {case['answer']}") self.monitor.print_summary() # 사용 예시 qa_monitor = QAQualityMonitor( sample_rate=0.15, # 15% 평가 (비용 85% 절감) relevancy_threshold=0.6 # 0.6 미만이면 알림 ) # 프로덕션 QA 봇 for i in range(100): user_q = f"사용자 질문 {i}" bot_a = qa_bot.answer(user_q) # 관련성 모니터링 qa_monitor.track_qa_interaction( qa_id=f"qa_{i}", user_question=user_q, bot_answer=bot_a ) # 일일 리포트 qa_monitor.get_daily_report() 

#### ⚠️ 프로덕션 모니터링 주의사항

  * **샘플링 비율** : 초기에는 20-30%로 시작하여 안정화 후 10-15%로 감소
  * **비용 관리** : DeepEval API 호출 비용 월 예산 설정
  * **False Negative** : 창의적/유머러스 답변도 낮게 평가될 수 있음
  * **사용자 피드백 통합** : 관련성 점수와 사용자 평점 비교 분석

### 방법 3: FAQ 시스템 관련성 검증

#### 📌 사용 시기

FAQ 데이터베이스의 질문-답변 쌍이 적절하게 매칭되어 있는지 검증

from agent_evaluator import HybridPerformanceMonitor, create_taskresult import json class FAQRelevancyValidator: """FAQ 데이터베이스 관련성 검증""" def __init__(self, min_relevancy: float = 0.7): self.monitor = HybridPerformanceMonitor(use_deepeval=True) self.min_relevancy = min_relevancy self.validation_results = [] def validate_faq_database(self, faq_list: list): """ FAQ 데이터베이스 검증 Args: faq_list: [{'question': str, 'answer': str, 'id': str}, ...] """ print(f"🔍 Validating {len(faq_list)} FAQ entries...") for i, faq in enumerate(faq_list, 1): faq_id = faq.get('id', f"faq_{i}") question = faq['question'] answer = faq['answer'] # 관련성 평가 task = create_taskresult(faq_id, "qa", True, 1.0) self.monitor.record_task( task, True, input_text=question, output_text=answer ) # 결과 수집 if self.monitor.extended_tasks: relevancy = self.monitor.extended_tasks[-1].advanced_metrics.get( 'answer_relevancy_score', 0.0 ) result = { 'id': faq_id, 'question': question, 'answer': answer[:100], 'relevancy_score': relevancy, 'valid': relevancy >= self.min_relevancy } self.validation_results.append(result) if not result['valid']: print(f" ⚠️ FAQ {faq_id}: Low relevancy {relevancy:.3f}") if i % 10 == 0: print(f" Progress: {i}/{len(faq_list)}") def generate_validation_report(self, output_file: str = "faq_validation.json"): """검증 리포트 생성""" invalid = [r for r in self.validation_results if not r['valid']] invalid_rate = len(invalid) / len(self.validation_results) * 100 if self.validation_results else 0 report = { 'summary': { 'total_faqs': len(self.validation_results), 'valid_faqs': len(self.validation_results) - len(invalid), 'invalid_faqs': len(invalid), 'invalid_rate': invalid_rate, 'min_relevancy': self.min_relevancy }, 'invalid_entries': sorted( invalid, key=lambda x: x['relevancy_score'] ) } with open(output_file, 'w', encoding='utf-8') as f: json.dump(report, f, indent=2, ensure_ascii=False) print(f"\n✅ FAQ Validation Report") print(f" Total FAQs: {report['summary']['total_faqs']}") print(f" Valid: {report['summary']['valid_faqs']}") print(f" Invalid: {report['summary']['invalid_faqs']} ({invalid_rate:.1f}%)") print(f" Report saved to: {output_file}") if invalid: print(f"\n🚨 Top 5 Invalid FAQs:") for i, entry in enumerate(report['invalid_entries'][:5], 1): print(f" {i}. ID: {entry['id']} | Score: {entry['relevancy_score']:.3f}") print(f" Q: {entry['question']}") # 사용 예시 validator = FAQRelevancyValidator(min_relevancy=0.7) # FAQ 데이터베이스 faq_database = [ { 'id': 'faq_001', 'question': '배송 기간은 얼마나 걸리나요?', 'answer': '일반 배송은 2-3일, 빠른 배송은 익일 도착합니다.' }, { 'id': 'faq_002', 'question': '환불 정책은 어떻게 되나요?', 'answer': '저희 회사는 1995년에 설립되었으며 고객 만족을 최우선으로 합니다.' # 낮은 관련성 }, # ... more FAQs ] # FAQ 검증 validator.validate_faq_database(faq_database) # 리포트 생성 validator.generate_validation_report("faq_validation_2025.json") 

### 방법 4: A/B 테스트 - 답변 스타일 비교

#### 📌 사용 시기

여러 답변 스타일(간결형 vs 상세형) 중 어느 것이 더 관련성이 높은지 비교

from agent_evaluator import HybridPerformanceMonitor, create_taskresult class AnswerStyleABTest: """답변 스타일 A/B 테스트""" def __init__(self): self.monitor_concise = HybridPerformanceMonitor(use_deepeval=True) self.monitor_detailed = HybridPerformanceMonitor(use_deepeval=True) def test_answer_styles( self, test_questions: list, concise_generator, detailed_generator ): """두 답변 스타일의 관련성 비교""" print(f"Testing {len(test_questions)} questions with 2 styles...") for i, question in enumerate(test_questions, 1): # 간결형 답변 concise_answer = concise_generator(question) task_c = create_taskresult(f"concise_{i}", "qa", True, 1.0) self.monitor_concise.record_task( task_c, True, question, concise_answer ) # 상세형 답변 detailed_answer = detailed_generator(question) task_d = create_taskresult(f"detailed_{i}", "qa", True, 1.0) self.monitor_detailed.record_task( task_d, True, question, detailed_answer ) def get_winner(self): """더 관련성 높은 스타일 선택""" report_c = self.monitor_concise.generate_hybrid_report() report_d = self.monitor_detailed.generate_hybrid_report() relevancy_c = report_c.advanced_metrics_summary.get( 'answer_relevancy_score', {} ).get('mean', 0) relevancy_d = report_d.advanced_metrics_summary.get( 'answer_relevancy_score', {} ).get('mean', 0) print(f"\n📊 Answer Style A/B Test Results") print(f" Concise Style Relevancy: {relevancy_c:.3f}") print(f" Detailed Style Relevancy: {relevancy_d:.3f}") winner = "Concise" if relevancy_c > relevancy_d else "Detailed" improvement = abs(relevancy_c - relevancy_d) / min(relevancy_c, relevancy_d) * 100 print(f" Winner: {winner} Style") print(f" Improvement: {improvement:.1f}%") return winner # 사용 예시 ab_test = AnswerStyleABTest() test_questions = [ "파이썬이란 무엇인가요?", "머신러닝의 종류는?", "REST API 설명해주세요" ] # 간결형 생성기 def generate_concise(q): return llm.generate(q, max_length=100) # 상세형 생성기 def generate_detailed(q): return llm.generate(q, max_length=500) ab_test.test_answer_styles( test_questions, generate_concise, generate_detailed ) winner = ab_test.get_winner() print(f"\n✅ Deploy {winner} style in production") 

## 💡 Best Practices

#### 1\. Threshold 설정 전략

  * **FAQ 시스템** : threshold=0.7 (엄격)
  * **정보 검색** : threshold=0.6 (보통)
  * **일반 챗봇** : threshold=0.5 (관대)
  * **창의적 대화** : threshold=0.4 (매우 관대)

#### 2\. 관련성 향상 전략

  * **프롬프트 명시** : "질문에 직접적으로 답하세요" 추가
  * **템플릿 사용** : "질문: {Q}에 대한 답변: ..." 형식
  * **불필요 정보 제거** : 질문과 무관한 배경 설명 최소화
  * **완전성 보장** : 질문의 모든 부분에 답변

#### 3\. 낮은 관련성 처리

  * **자동 재생성** : 관련성 낮으면 다른 전략으로 재시도
  * **폴백 답변** : "죄송하지만 정확히 이해하지 못했습니다" 제공
  * **질문 명확화** : 사용자에게 질문을 구체화하도록 요청
  * **인간 에스컬레이션** : 중요한 경우 인간 상담원 연결

#### ⚠️ 주의사항

  * **맥락 의존성** : 대화 맥락이 필요한 경우 이전 대화 포함
  * **창의적 답변** : 유머/비유적 표현은 낮게 평가될 수 있음
  * **복합 질문** : 여러 질문이 하나에 포함되면 평가 어려움
  * **모호한 질문** : 질문이 불명확하면 관련성 평가도 부정확
  * **LLM 편향** : 평가용 LLM의 선호도 영향

## 📈 활용 예시

### 예시 1: 고객 지원 챗봇 품질 모니터링

# 고객 지원 챗봇의 답변 관련성 실시간 모니터링 monitor = HybridPerformanceMonitor(use_deepeval=True) def handle_customer_query(customer_id, query): # 챗봇 응답 생성 response = chatbot.generate(query) # 관련성 평가 task = create_taskresult(f"cs_{customer_id}", "qa", True, 1.0) monitor.record_task(task, True, query, response) relevancy = monitor.extended_tasks[-1].advanced_metrics['answer_relevancy_score'] if relevancy < 0.5: # 관련성 낮으면 재생성 또는 인간 상담원 연결 return escalate_to_human(customer_id, query) return response 

### 예시 2: 검색 엔진 결과 품질 평가

# 검색 결과의 관련성 평가 monitor = HybridPerformanceMonitor(use_deepeval=True) def evaluate_search_results(query, results): for i, result in enumerate(results): task = create_taskresult(f"search_{i}", "information_retrieval", True, 1.0) monitor.record_task( task, True, query, result['title'] + " " \+ result['snippet'] ) # 평균 관련성 계산 relevancies = [ t.advanced_metrics['answer_relevancy_score'] for t in monitor.extended_tasks ] avg_relevancy = sum(relevancies) / len(relevancies) print(f"Search Quality for '{query}': {avg_relevancy:.3f}") return avg_relevancy 

## 🔗 관련 메트릭

  * **G-Eval (Layer 3)** : 사용자 정의 품질 기준으로 관련성 평가 가능
  * **Accuracy (Layer 1)** : 답변의 정확성 평가
  * **Quality Score (Layer 1)** : 전반적 품질 평가
  * **Ragas Answer Relevancy (Layer 3)** : RAG 시스템 전용 관련성 평가

## 📚 참고 자료

  * **DeepEval Documentation** : <https://docs.confident-ai.com/>
  * **Answer Relevancy Research** : "Evaluating Answer Relevance in Question Answering Systems"
  * **Agent Evaluator GitHub** : [GitHub Repository](<https://github.com/your-repo/agent-evaluator>)
