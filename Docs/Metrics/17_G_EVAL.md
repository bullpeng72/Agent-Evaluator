# 🎯 G-Eval Quality Assessment

LLM-based Custom Quality Evaluation with DeepEval

Agent Evaluator v0.5.2 - Layer 3 DeepEval Metric

## 🎯 개요

**G-Eval** 은 사용자 정의 품질 기준(Custom Criteria)을 기반으로 LLM의 출력 품질을 평가하는 DeepEval의 고급 메트릭입니다.   
  
평가 프레임워크로 GPT-4나 다른 LLM을 사용하여 복잡한 품질 차원을 유연하게 평가할 수 있으며, 단순한 정확도를 넘어 응답의 완전성(Completeness), 관련성(Relevance), 일관성(Coherence) 등을 종합적으로 평가합니다. 

### ⚠️ 중요성

  * **유연한 평가 기준** : 비즈니스 요구사항에 맞춘 맞춤형 평가 가능
  * **복합적 품질 측정** : 단일 메트릭으로 다차원 품질 평가
  * **인간 평가 근사** : LLM을 평가자로 활용하여 인간 판단 모방
  * **비용 효율적** : 인간 평가 대비 빠르고 저렴한 평가
  * **일관성 보장** : 평가자의 주관성을 줄이고 일관된 평가 제공

## 📊 다이어그램 시각화

### 1️⃣ 핵심 개념 및 평가 흐름 (LLM-as-Judge)
```python
    graph TD
        A[Input + Actual Output + Expected Output + Context] --> B[DeepEval G-Eval Metric]
        B --> C[Custom Evaluation Criteria  
    사용자 정의 평가 기준]
    
        C --> D[LLM Judge  
    gpt-4o-mini default]
        D --> E[Criteria-Based Assessment]
    
        E --> F[평가 파라미터]
        F --> G[INPUT: 입력 쿼리]
        F --> H[ACTUAL_OUTPUT: 실제 응답]
        F --> I[EXPECTED_OUTPUT: 기대값 optional]
        F --> J[CONTEXT: 검색 문맥 optional]
    
        G --> K[Chain-of-Thought Reasoning]
        H --> K
        I --> K
        J --> K
    
        K --> L[G-Eval Score 0-1  
    1 = Perfect Quality]
    
        L --> M{Quality Level}
        M -->|≥ 0.9| N[Excellent: 기준 충족]
        M -->|0.7-0.89| O[Good: 양호]
        M -->|0.5-0.69| P[Moderate: 개선 필요]
        M -->|< 0.5| Q[Poor: 기준 미달]
    
        style A fill:#e1f5ff
        style L fill:#fff3cd
        style N fill:#d4edda
        style Q fill:#f8d7da
        
```

### 2️⃣ G-Eval 평가 파이프라인 (DeepEval Integration)
```python
    sequenceDiagram
        participant Agent as AI Agent
        participant Adapter as DeepEvalAdapter
        participant GEval as G-Eval Metric
        participant LLM as OpenAI API  
    gpt-4o-mini
    
        Agent->>Adapter: evaluate(context)
        Adapter->>Adapter: Create LLMTestCase  
    input, actual, expected, context
    
        Adapter->>GEval: GEval(criteria, evaluation_params, model)
        Note over GEval: criteria: 커스텀 평가 기준  
    evaluation_params: [INPUT, ACTUAL_OUTPUT, ...]
    
        GEval->>LLM: Generate evaluation prompt
        LLM->>LLM: Chain-of-Thought reasoning  
    기준에 따라 평가
    
        LLM-->>GEval: Score (0-1) + Reason
        GEval-->>Adapter: g_eval_score, g_eval_reason
    
        Adapter-->>Agent: {'g_eval_score': 0.85, 'g_eval_reason': '...'}
        
```

### 3️⃣ 비용 및 성능 고려사항
```python
    graph TD
        A[G-Eval Configuration] --> B[Model Selection]
        B --> C[gpt-4o-mini  
    Default, Cost-Effective]
        B --> D[gpt-4o  
    High Quality, Expensive]
    
        C --> E[Cost: ~$0.01-0.03 per eval  
    Speed: ~2-5 sec  
    Quality: Good 85%+]
        D --> F[Cost: ~$0.10-0.30 per eval  
    Speed: ~3-7 sec  
    Quality: Excellent 95%+]
    
        E --> G{Use Case}
        F --> G
    
        G -->|Development/Testing| H[권장: gpt-4o-mini  
    빠른 반복, 낮은 비용]
        G -->|Production/Critical| I[권장: gpt-4o  
    높은 정확도, 신뢰성]
    
        H --> J[Budget Planning]
        I --> J
    
        J --> K[1000 evals/day:  
    mini: $10-30/day  
    4o: $100-300/day]
    
        style A fill:#e1f5ff
        style J fill:#fff3cd
        style K fill:#ffc107
        
```

### 4️⃣ 임계값 및 품질 관리
```python
    graph TD
        A[G-Eval Score] --> B{임계값 비교}
        B -->|≥ 0.90| C[🌟 Excellent  
    Criteria Met]
        B -->|0.70-0.89| D[✅ Good  
    Acceptable Quality]
        B -->|0.50-0.69| E[⚠️ Moderate  
    Needs Improvement]
        B -->|< 0.50| F[❌ Poor  
    Criteria Failed]
    
        C --> G[권장: 현재 품질 유지  
    벤치마크 활용]
        D --> H[권장: 0.90 목표  
    프롬프트 최적화]
        E --> I[권장: 기준 재검토  
    응답 개선 필요]
        F --> J[권장: 즉시 개선  
    모델/프롬프트 재설계]
    
        style C fill:#d4edda
        style D fill:#cfe2ff
        style E fill:#fff3cd
        style F fill:#f8d7da
        
```

## 📍 구현 위치

**파일:** `agent_evaluator/integrations/metric_adapters.py`  
**클래스:** `DeepEvalAdapter`  
**메서드:** `_evaluate_geval()`  
**라인:** 200-247 

### 핵심 메서드

메서드 | 라인 | 설명  
---|---|---  
`__init__()` | 87-128 | DeepEval 어댑터 초기화 (모델, 임계값 설정)  
`evaluate()` | 133-198 | 모든 DeepEval 메트릭 평가 (G-Eval 포함)  
`_evaluate_geval()` | 200-247 | G-Eval 메트릭 실행 및 결과 반환  
  
## 📋 G-Eval 평가 원리

**G-Eval** 은 다음 단계로 작동합니다:   
  


  1. **평가 기준 정의** : 사용자가 평가하고자 하는 품질 차원 정의 (예: "답변이 사용자 질문에 완전하고 정확하게 응답했는가?")
  2. **평가 파라미터 선택** : INPUT, ACTUAL_OUTPUT, EXPECTED_OUTPUT, CONTEXT 중 평가에 사용할 요소 선택
  3. **LLM 평가** : 평가용 LLM (예: gpt-4o-mini)이 정의된 기준에 따라 출력 평가
  4. **스코어 산출** : 0.0 ~ 1.0 범위의 점수 반환 (높을수록 품질 우수)

### 평가 파라미터 (LLMTestCaseParams)

파라미터 | 설명 | 사용 시점  
---|---|---  
`INPUT` | 사용자 입력 (질문, 프롬프트) | 항상 사용  
`ACTUAL_OUTPUT` | AI 에이전트의 실제 출력 | 항상 사용  
`EXPECTED_OUTPUT` | 기대되는 정답 (Ground Truth) | Ground Truth가 있을 때만  
`CONTEXT` | 검색된 컨텍스트 (RAG용) | RAG 시스템에서만  
  
### 스코어 해석

G-Eval Score | 등급 | 설명 | 권장 조치  
---|---|---|---  
0.8 ~ 1.0 | **Excellent** | 매우 우수한 품질 | 현재 수준 유지  
0.6 ~ 0.79 | **Good** | 우수한 품질 | 미세 조정 고려  
0.4 ~ 0.59 | **Acceptable** | 허용 가능 | 프롬프트 개선 필요  
0.0 ~ 0.39 | **Poor** | 품질 미달 | 즉각적인 개선 필요  
  
## ⚙️ 핵심 메서드 상세 설명

### _evaluate_geval() - G-Eval 평가 실행

**목적** : 사용자 정의 평가 기준에 따라 G-Eval 수행

**위치** : Lines 200-247

def _evaluate_geval(self, test_case, criteria: str) -> Dict[str, Any]: """ Evaluate using G-Eval with custom criteria G-Eval evaluates based on the test case parameters you specify. Uses INPUT, ACTUAL_OUTPUT, and EXPECTED_OUTPUT by default. """ try: # 1. 평가 파라미터 정의 (어떤 요소를 평가에 사용할지) eval_params = [ self.LLMTestCaseParams.INPUT, self.LLMTestCaseParams.ACTUAL_OUTPUT ] # 2. Expected Output이 있으면 추가 if test_case.expected_output: eval_params.append(self.LLMTestCaseParams.EXPECTED_OUTPUT) # 3. Context가 있으면 추가 (RAG 시스템) if test_case.context and len(test_case.context) > 0: eval_params.append(self.LLMTestCaseParams.CONTEXT) # 4. G-Eval 메트릭 생성 metric = self.GEval( name="quality_assessment", criteria=criteria, # 사용자 정의 평가 기준 evaluation_params=eval_params, # 평가에 사용할 요소 model=self.model, # 평가용 LLM (예: gpt-4o-mini) threshold=self.threshold, # Pass/Fail 기준 (기본: 0.5) async_mode=False # 동기 실행 ) # 5. 평가 수행 metric.measure(test_case) # 6. 결과 반환 return { 'g_eval_score': metric.score, # 0.0 ~ 1.0 'g_eval_reason': metric.reason if hasattr(metric, 'reason') else None, 'g_eval_passed': metric.score >= self.threshold } except Exception as e: print(f"⚠️ G-Eval error: {e}") return {'g_eval_error': str(e)} 

#### ✅ 평가 로직 핵심 포인트

  1. **동적 파라미터 선택** : 사용 가능한 데이터(expected_output, context)에 따라 자동으로 평가 파라미터 구성
  2. **유연한 기준** : 사용자가 자연어로 평가 기준을 정의하면 LLM이 이해하고 평가
  3. **Pass/Fail 판정** : 임계값(threshold) 기반 이진 판정 제공
  4. **설명 제공** : 점수와 함께 평가 이유(reason) 반환 가능

### HybridPerformanceMonitor 통합

**목적** : G-Eval을 HybridPerformanceMonitor에서 자동 실행

**위치** : `agent_evaluator/core/hybrid_monitor.py` Lines 200-217

# HybridPerformanceMonitor.record_task() 내부 # DeepEval metrics 실행 if MetricProvider.DEEPEVAL in self.metric_adapters: try: deepeval_metrics = self.metric_adapters[MetricProvider.DEEPEVAL].evaluate(context) advanced_metrics.update(deepeval_metrics) providers_used.append("deepeval") except Exception as e: print(f"⚠️ DeepEval evaluation error: {e}") # G-Eval 결과가 있으면 QualityEvaluator에도 자동 반영 if 'g_eval_score' in advanced_metrics: # G-Eval score를 5점 척도로 변환 g_eval_score_5pt = advanced_metrics['g_eval_score'] * 5 # Quality Evaluator에 자동 추가 quality_evaluation = { "task_id": task.task_id, "dimension_scores": { "completeness": g_eval_score_5pt, "relevance": g_eval_score_5pt, "clarity": g_eval_score_5pt, "accuracy": g_eval_score_5pt, "usefulness": g_eval_score_5pt }, "total_score": g_eval_score_5pt } self.quality_evaluator.evaluations.append(quality_evaluation) 

## 🔍 데이터 수집 방법 (실전 가이드)

G-Eval 메트릭을 현장에서 측정하기 위한 4가지 실전 방법을 소개합니다.

### 방법 1: HybridPerformanceMonitor 직접 사용 (권장)

#### 📌 사용 시기

품질 기준이 명확하고, 평가용 데이터(input, output, expected_output)가 준비된 경우

from agent_evaluator import HybridPerformanceMonitor, create_taskresult # 1. HybridPerformanceMonitor 초기화 (DeepEval 활성화) monitor = HybridPerformanceMonitor( use_deepeval=True, deepeval_model="gpt-4o-mini", # 비용 효율적 use_ragas=False, use_langsmith=False ) # 2. 사용자 정의 평가 기준 정의 quality_criteria = """ 답변이 다음 기준을 충족하는지 평가하세요: 1\. 질문에 완전하고 정확하게 응답했는가? 2\. 제공된 정보가 관련성 있고 유용한가? 3\. 답변이 명확하고 이해하기 쉬운가? 4\. 사실적 오류나 모순이 없는가? 5\. 전문적이고 적절한 어조를 유지하는가? """ # 3. 에이전트 실행 및 데이터 수집 task = create_taskresult( task_id="task_001", task_type="QA", success=True, completion_score=1.0, accuracy_score=0.95 ) # 4. G-Eval 평가 수행 monitor.record_task( task=task, enable_advanced_metrics=True, # DeepEval 활성화 input_text="파이썬으로 피보나치 수열을 구현하는 방법을 설명해주세요.", output_text="파이썬에서 피보나치 수열은 재귀 또는 반복문으로 구현할 수 있습니다...", expected_output="재귀와 반복문 방식의 차이를 설명하고, 각각의 시간 복잡도를 비교해야 함", quality_criteria=quality_criteria # G-Eval 트리거 ) # 5. 결과 확인 monitor.print_summary() # 출력 예시: # 🔬 ADVANCED METRICS # G-Eval Quality Score: 0.850/1.0 (n=1) # Pass Rate: 1/1 (100.0%)

**✅ Best Practice:**

  * **명확한 기준** : 평가 기준은 구체적이고 측정 가능하게 작성 (예: "완전성", "정확성"보다 "질문의 모든 부분에 답했는가?", "사실적 오류가 없는가?" 등)
  * **적절한 모델 선택** : 일반적인 경우 `gpt-4o-mini`로 충분, 고도로 정교한 평가가 필요하면 `gpt-4o` 사용
  * **Expected Output 활용** : Ground Truth가 있으면 반드시 제공하여 평가 정확도 향상
  * **배치 평가** : 비용 절감을 위해 중요한 작업만 샘플링하여 G-Eval 수행 (예: 10% 샘플링)

### 방법 2: DeepEvalAdapter 직접 사용 (고급)

#### 📌 사용 시기

HybridPerformanceMonitor 없이 G-Eval만 독립적으로 사용하고 싶은 경우

from agent_evaluator.integrations.metric_adapters import ( DeepEvalAdapter, EvaluationContext ) # 1. DeepEvalAdapter 초기화 adapter = DeepEvalAdapter( model="gpt-4o-mini", threshold=0.7, # Pass/Fail 기준 timeout=60 ) if not adapter.is_available(): print("⚠️ DeepEval not installed. Install with: pip install deepeval") exit(1) # 2. 평가 컨텍스트 생성 context = EvaluationContext( input_text="머신러닝에서 Overfitting이란 무엇인가요?", output_text="Overfitting은 모델이 훈련 데이터에 지나치게 적합되어 새로운 데이터에 대한 일반화 성능이 떨어지는 현상입니다.", expected_output="Overfitting 정의, 발생 원인, 해결 방법을 포함해야 함", quality_criteria=""" 답변이 다음을 충족하는지 평가: 1\. Overfitting의 정확한 정의 2\. 발생 원인 설명 3\. 해결 방법 제시 4\. 실무적 예시 포함 """ ) # 3. G-Eval 평가 수행 results = adapter.evaluate(context) # 4. 결과 확인 if 'g_eval_score' in results: print(f"G-Eval Score: {results['g_eval_score']:.3f}") print(f"Passed: {results['g_eval_passed']}") if results.get('g_eval_reason'): print(f"Reason: {results['g_eval_reason']}") else: print(f"Error: {results.get('g_eval_error', 'Unknown error')}") 

### 방법 3: 프로덕션 모니터링 (샘플링 기반)

#### 📌 사용 시기

대규모 프로덕션 환경에서 비용을 절감하면서 품질 모니터링이 필요한 경우

import random from agent_evaluator import HybridPerformanceMonitor, create_taskresult class ProductionQualityMonitor: """프로덕션 환경에서 샘플링 기반 G-Eval 모니터링""" def __init__(self, sample_rate: float = 0.1, quality_criteria: str = None): """ Args: sample_rate: G-Eval 실행 비율 (0.1 = 10%, 비용 절감) quality_criteria: 평가 기준 (프로젝트별 정의) """ self.monitor = HybridPerformanceMonitor( use_deepeval=True, deepeval_model="gpt-4o-mini" ) self.sample_rate = sample_rate self.quality_criteria = quality_criteria or """ 답변 품질 평가 기준: 1\. 질문에 완전하게 답했는가? 2\. 정확하고 사실에 기반한가? 3\. 명확하고 이해하기 쉬운가? """ self.evaluated_count = 0 self.total_count = 0 self.low_quality_alerts = [] def track_interaction( self, task_id: str, input_text: str, output_text: str, expected_output: str = None, task_type: str = "QA" ): """사용자 상호작용 추적 및 샘플링 평가""" self.total_count += 1 # 샘플링: 일부만 G-Eval 실행 (비용 절감) should_evaluate = random.random() < self.sample_rate if should_evaluate: self.evaluated_count += 1 # TaskResult 생성 task = create_taskresult( task_id=task_id, task_type=task_type, success=True, completion_score=1.0 ) # G-Eval 수행 self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=input_text, output_text=output_text, expected_output=expected_output, quality_criteria=self.quality_criteria ) # 저품질 경고 확인 if hasattr(self.monitor, 'extended_tasks') and self.monitor.extended_tasks: latest_task = self.monitor.extended_tasks[-1] g_eval_score = latest_task.advanced_metrics.get('g_eval_score', 1.0) if g_eval_score < 0.5: # 저품질 임계값 self.low_quality_alerts.append({ 'task_id': task_id, 'score': g_eval_score, 'input': input_text[:100], 'output': output_text[:100] }) print(f"⚠️ Low quality detected: {task_id} (Score: {g_eval_score:.3f})") def get_summary(self): """모니터링 요약 리포트""" print(f"\n📊 Quality Monitoring Summary") print(f" Total Interactions: {self.total_count}") print(f" Evaluated (G-Eval): {self.evaluated_count} ({self.sample_rate*100:.1f}%)") print(f" Low Quality Alerts: {len(self.low_quality_alerts)}") self.monitor.print_summary() # 사용 예시 monitor = ProductionQualityMonitor( sample_rate=0.1, # 10%만 평가 (비용 90% 절감) quality_criteria=""" 고객 지원 챗봇 품질 평가: 1\. 고객 문의를 정확히 이해했는가? 2\. 해결책이 명확하고 실행 가능한가? 3\. 친절하고 전문적인 어조인가? """ ) # 프로덕션 트래픽 처리 for i in range(100): monitor.track_interaction( task_id=f"chat_{i}", input_text=f"고객 질문 {i}", output_text=f"챗봇 답변 {i}" ) # 결과 확인 monitor.get_summary() 

#### ⚠️ 프로덕션 모니터링 주의사항

  * **샘플링 비율 조정** : 초기에는 20-30%로 시작하여 데이터 확보 후 10%로 감소
  * **비용 모니터링** : DeepEval은 OpenAI API를 호출하므로 월 비용 예산 설정 필요
  * **타임아웃 설정** : 프로덕션 환경에서는 평가 타임아웃을 30-60초로 제한
  * **비동기 처리** : 실시간 응답이 필요한 경우 G-Eval을 백그라운드 작업으로 실행

### 방법 4: 맞춤형 평가 기준 라이브러리 구축

#### 📌 사용 시기

여러 유형의 작업(QA, 코드 생성, 요약 등)에 대해 표준화된 평가 기준을 적용하고 싶은 경우

from agent_evaluator import HybridPerformanceMonitor, create_taskresult class QualityCriteriaLibrary: """작업 유형별 표준 평가 기준 라이브러리""" # 작업 유형별 평가 기준 정의 CRITERIA = { "QA": """ 질의응답 품질 평가: 1\. 질문을 정확히 이해하고 모든 부분에 답했는가? 2\. 답변이 사실적으로 정확한가? 3\. 설명이 명확하고 이해하기 쉬운가? 4\. 불필요한 정보 없이 간결한가? 5\. 출처나 근거를 제시했는가? """, "CODE_GENERATION": """ 코드 생성 품질 평가: 1\. 요구사항을 완전히 구현했는가? 2\. 코드가 문법적으로 올바르고 실행 가능한가? 3\. 가독성과 유지보수성이 좋은가? 4\. 에러 처리와 엣지 케이스를 고려했는가? 5\. 주석과 문서화가 적절한가? """, "SUMMARIZATION": """ 요약 품질 평가: 1\. 원문의 핵심 내용을 모두 포함했는가? 2\. 중요도에 따라 적절히 선별했는가? 3\. 간결하면서도 이해하기 쉬운가? 4\. 원문의 의미를 왜곡하지 않았는가? 5\. 논리적 흐름이 자연스러운가? """, "TRANSLATION": """ 번역 품질 평가: 1\. 원문의 의미를 정확히 전달했는가? 2\. 대상 언어로 자연스러운가? 3\. 문화적 맥락을 고려했는가? 4\. 전문 용어를 적절히 번역했는가? 5\. 원문의 어조와 뉘앙스를 유지했는가? """, "CUSTOMER_SUPPORT": """ 고객 지원 품질 평가: 1\. 고객 문의를 정확히 이해했는가? 2\. 해결책이 명확하고 실행 가능한가? 3\. 친절하고 공감적인 어조를 유지했는가? 4\. 적절한 수준의 기술적 세부사항을 제공했는가? 5\. 추가 도움이나 후속 조치를 제안했는가? """ } @classmethod def get_criteria(cls, task_type: str) -> str: """작업 유형에 맞는 평가 기준 반환""" return cls.CRITERIA.get(task_type, cls.CRITERIA["QA"]) @classmethod def evaluate_with_criteria( cls, monitor: HybridPerformanceMonitor, task_id: str, task_type: str, input_text: str, output_text: str, expected_output: str = None ): """표준 기준으로 G-Eval 평가""" criteria = cls.get_criteria(task_type) task = create_taskresult( task_id=task_id, task_type=task_type, success=True, completion_score=1.0 ) monitor.record_task( task=task, enable_advanced_metrics=True, input_text=input_text, output_text=output_text, expected_output=expected_output, quality_criteria=criteria ) # 사용 예시 monitor = HybridPerformanceMonitor(use_deepeval=True) # QA 작업 평가 QualityCriteriaLibrary.evaluate_with_criteria( monitor=monitor, task_id="qa_001", task_type="QA", input_text="머신러닝에서 Regularization이란?", output_text="Regularization은 과적합을 방지하기 위한 기법입니다..." ) # 코드 생성 평가 QualityCriteriaLibrary.evaluate_with_criteria( monitor=monitor, task_id="code_001", task_type="CODE_GENERATION", input_text="이진 탐색 알고리즘을 구현해주세요", output_text="def binary_search(arr, target): ..." ) monitor.print_summary() 

#### ✅ 평가 기준 라이브러리의 장점

  * **일관성** : 모든 작업에 표준화된 기준 적용
  * **확장성** : 새로운 작업 유형 쉽게 추가
  * **유지보수** : 평가 기준을 중앙에서 관리
  * **비교 가능성** : 동일 기준으로 시간에 따른 품질 변화 추적

## 💡 Best Practices

#### 1\. 평가 기준 작성 가이드라인

  * **구체적으로** : "좋은 답변"보다 "질문의 모든 부분에 답했는가?" 사용
  * **측정 가능하게** : 주관적 표현 대신 명확한 체크리스트 제공
  * **3-7개 항목** : 너무 많으면 LLM이 혼란스러워함
  * **예시 제공** : 가능하면 Good/Bad 예시를 기준에 포함

#### 2\. 비용 최적화 전략

  * **gpt-4o-mini 사용** : 일반 평가는 mini로 충분 (비용 1/10)
  * **샘플링 적용** : 프로덕션에서는 10-20%만 평가
  * **캐싱 활용** : 동일 input-output 쌍은 결과 재사용
  * **배치 처리** : 실시간이 아닌 경우 배치로 모아서 평가

#### 3\. 정확도 향상 방법

  * **Expected Output 제공** : Ground Truth가 있으면 반드시 포함
  * **Context 활용** : RAG 시스템은 retrieved_context도 전달
  * **다중 평가** : 중요한 작업은 2-3회 평가하여 평균 사용
  * **임계값 조정** : 프로젝트 특성에 맞게 threshold 튜닝

#### ⚠️ 주의사항

  * **LLM 편향** : G-Eval은 평가용 LLM의 편향을 상속할 수 있음
  * **일관성 변동** : 동일 입력도 평가 시점에 따라 점수 변동 가능
  * **비용 누적** : 대규모 평가 시 API 비용 급증 주의
  * **타임아웃** : 네트워크 지연이나 API 장애 대비 타임아웃 설정
  * **Rate Limiting** : OpenAI API Rate Limit 고려하여 속도 조절

## 📈 활용 예시

### 예시 1: 챗봇 품질 모니터링

# 고객 지원 챗봇의 답변 품질을 G-Eval로 모니터링 monitor = HybridPerformanceMonitor(use_deepeval=True) chatbot_criteria = """ 고객 지원 챗봇 답변 품질: 1\. 고객 문의의 핵심 문제를 파악했는가? 2\. 구체적이고 실행 가능한 해결책을 제시했는가? 3\. 친절하고 공감적인 어조를 유지했는가? 4\. 필요한 경우 추가 지원을 안내했는가? """ for interaction in customer_interactions: task = create_taskresult( task_id=interaction['id'], task_type="CUSTOMER_SUPPORT", success=True, completion_score=1.0 ) monitor.record_task( task=task, enable_advanced_metrics=True, input_text=interaction['customer_message'], output_text=interaction['chatbot_response'], quality_criteria=chatbot_criteria ) # 월간 품질 리포트 생성 report = monitor.generate_hybrid_report() print(f"G-Eval 평균 점수: {report.advanced_metrics_summary['g_eval_score']['mean']:.3f}") 

### 예시 2: A/B 테스트 - 프롬프트 비교

# 두 가지 프롬프트 버전의 품질을 G-Eval로 비교 monitor_a = HybridPerformanceMonitor(use_deepeval=True) monitor_b = HybridPerformanceMonitor(use_deepeval=True) criteria = """코드 생성 품질 평가: 정확성, 가독성, 효율성""" # Version A: 간단한 프롬프트 for task in test_tasks: result_a = agent_a.generate_code(task) monitor_a.record_task( create_taskresult("A", "CODE_GENERATION", True, 1.0), enable_advanced_metrics=True, input_text=task['prompt'], output_text=result_a, quality_criteria=criteria ) # Version B: 상세한 프롬프트 for task in test_tasks: result_b = agent_b.generate_code(task) monitor_b.record_task( create_taskresult("B", "CODE_GENERATION", True, 1.0), enable_advanced_metrics=True, input_text=task['prompt'], output_text=result_b, quality_criteria=criteria ) # 결과 비교 report_a = monitor_a.generate_hybrid_report() report_b = monitor_b.generate_hybrid_report() score_a = report_a.advanced_metrics_summary['g_eval_score']['mean'] score_b = report_b.advanced_metrics_summary['g_eval_score']['mean'] print(f"Version A G-Eval: {score_a:.3f}") print(f"Version B G-Eval: {score_b:.3f}") print(f"Winner: {'B' if score_b > score_a else 'A'}") 

## 🔗 관련 메트릭

  * **Quality Score (Layer 1)** : Native 품질 평가 (더 빠르지만 덜 유연)
  * **Hallucination Metric (Layer 3)** : 환각 탐지 (컨텍스트 일치도)
  * **Answer Relevancy (Layer 3)** : 답변 관련성 평가
  * **Ragas Metrics (Layer 3)** : RAG 시스템 전용 품질 평가

## 📚 참고 자료

  * **DeepEval Documentation** : <https://docs.confident-ai.com/>
  * **G-Eval Paper** : "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment"
  * **Agent Evaluator GitHub** : [GitHub Repository](<https://github.com/your-repo/agent-evaluator>)
