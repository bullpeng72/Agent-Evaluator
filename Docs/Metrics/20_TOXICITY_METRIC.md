# 🛡️ Toxicity Detection

Harmful Content Detection with DeepEval

Agent Evaluator v0.5.0 - Layer 3 DeepEval Metric

## 🎯 개요

**Toxicity Detection** 은 LLM이 생성한 출력에 유해하거나 공격적인 콘텐츠가 포함되어 있는지 탐지하는 DeepEval의 안전성 메트릭입니다.   
  
욕설, 혐오 표현, 위협, 괴롭힘 등의 독성 콘텐츠를 자동으로 식별하여 안전하고 건전한 AI 서비스를 구축할 수 있습니다. LLM을 평가자로 사용하여 맥락을 고려한 정교한 탐지가 가능합니다. 

### ⚠️ 중요성

  * **사용자 보호** : 유해 콘텐츠로부터 사용자를 보호
  * **브랜드 신뢰** : 부적절한 출력 방지로 브랜드 이미지 보호
  * **법적 컴플라이언스** : 콘텐츠 규제 및 법적 요구사항 준수
  * **커뮤니티 건전성** : 건전한 온라인 커뮤니티 환경 유지
  * **윤리적 AI** : 책임 있는 AI 개발 실천

## 📊 다이어그램 시각화

### 1️⃣ 핵심 개념 및 유해성 탐지 (DeepEval)
```python
    graph TD
        A[Agent Output] --> B[ToxicityMetric  
    DeepEval]
        B --> C[LLM Judge  
    gpt-4o-mini]
    
        C --> D[Toxicity Categories Analysis]
        D --> E[1. 혐오 발언  
    Hate Speech]
        D --> F[2. 괴롭힘  
    Harassment]
        D --> G[3. 폭력적 내용  
    Violence]
        D --> H[4. 성적 내용  
    Sexual Content]
        D --> I[5. 차별적 언어  
    Discrimination]
    
        E --> J[Toxicity Score 0-1  
    0 = Safe, 1 = Toxic]
        F --> J
        G --> J
        H --> J
        I --> J
    
        J --> K{Safety Level}
        K -->|< 0.10| L[Safe: 안전한 콘텐츠]
        K -->|0.10-0.29| M[Low Risk: 경미한 문제]
        K -->|0.30-0.59| N[Moderate: 검토 필요]
        K -->|≥ 0.60| O[High Risk: 유해 콘텐츠]
    
        style A fill:#e1f5ff
        style J fill:#fff3cd
        style L fill:#d4edda
        style O fill:#f8d7da
        
```

### 2️⃣ 평가 파이프라인 (Content Moderation)
```python
    sequenceDiagram
        participant Agent as AI Agent
        participant Adapter as DeepEvalAdapter
        participant Metric as ToxicityMetric
        participant LLM as gpt-4o-mini
    
        Agent->>Adapter: evaluate(output_text)
        Adapter->>Adapter: Create LLMTestCase  
    actual_output=text
    
        Adapter->>Metric: ToxicityMetric(model, threshold)
        Note over Metric: threshold: 기본 0.5  
    이상이면 toxic 판정
    
        Metric->>LLM: Analyze toxicity
        LLM->>LLM: Check categories:  
    Hate, Harassment, Violence,  
    Sexual, Discrimination
    
        LLM-->>Metric: Score (0-1) + Category breakdown
        Metric-->>Adapter: toxicity_score, categories, reason
    
        Adapter-->>Agent: {'toxicity_score': 0.15, 'reason': '...'}
    
        alt Score ≥ threshold
            Agent->>Agent: Block output + Alert
        else Score < threshold
            Agent->>Agent: Pass output
        end
        
```

### 3️⃣ 비용 및 적용 전략
```python
    graph TD
        A[Toxicity Detection] --> B{Deployment Strategy}
    
        B -->|모든 출력 검사| C[100% Coverage  
    최대 안전성]
        B -->|샘플링 검사| D[10-20% Sampling  
    비용 절감]
        B -->|트리거 기반| E[Keyword Trigger  
    효율적 검사]
    
        C --> F[Cost: $0.01-0.02/output  
    1000 outputs/day = $10-20/day]
        D --> G[Cost: $0.002-0.004/output avg  
    1000 outputs/day = $2-4/day]
        E --> H[Cost: $0.003-0.006/output avg  
    Variable based on triggers]
    
        F --> I{Use Case}
        G --> I
        H --> I
    
        I -->|Public Chatbot| J[권장: 100% Coverage  
    Brand Safety Critical]
        I -->|Internal Tool| K[권장: Sampling  
    Cost-Effective]
        I -->|Low-Risk App| L[권장: Trigger-Based  
    Minimal Cost]
    
        style A fill:#e1f5ff
        style I fill:#fff3cd
        style J fill:#f8d7da
        
```

### 4️⃣ 임계값 및 컨텐츠 정책
```python
    graph TD
        A[Toxicity Score] --> B{임계값 비교}
        B -->|< 0.10| C[🌟 Safe  
    Clean Content]
        B -->|0.10-0.29| D[✅ Low Risk  
    Minor Concerns]
        B -->|0.30-0.59| E[⚠️ Moderate  
    Review Required]
        B -->|≥ 0.60| F[❌ High Risk  
    Block Content]
    
        C --> G[조치: 통과  
    정상 출력]
        D --> H[조치: 로깅  
    모니터링 강화]
        E --> I[조치: 사람 검토  
    컨텍스트 확인]
        F --> J[조치: 즉시 차단  
    알림 + 재생성]
    
        style C fill:#d4edda
        style D fill:#cfe2ff
        style E fill:#fff3cd
        style F fill:#f8d7da
        
```

## 📍 구현 위치

**파일:** `agent_evaluator/integrations/metric_adapters.py`  
**클래스:** `DeepEvalAdapter`  
**메서드:** `_evaluate_toxicity()`  
**라인:** 273-295 

### 핵심 메서드

메서드 | 라인 | 설명  
---|---|---  
`__init__()` | 87-128 | DeepEval 어댑터 초기화  
`evaluate()` | 133-198 | 모든 DeepEval 메트릭 평가 (독성 포함)  
`_evaluate_toxicity()` | 273-295 | 독성 콘텐츠 탐지 메트릭 실행  
  
## 📋 Toxicity 평가 원리

**Toxicity Detection** 은 다음 단계로 작동합니다:   
  


  1. **출력 분석** : LLM이 생성한 텍스트(actual_output)를 입력으로 받음
  2. **독성 패턴 검사** : 평가용 LLM이 욕설, 혐오 표현, 위협 등의 패턴 탐지
  3. **맥락 고려** : 단순 키워드 매칭이 아닌 문맥을 고려한 판단
  4. **Score 산출** : 0.0 ~ 1.0 범위의 점수 반환 (높을수록 독성 높음 = 나쁨)

### Toxicity Score 해석

#### ⚠️ 중요: Score 방향

**DeepEval ToxicityMetric은 "독성 수준" 점수입니다**

  * **0.0 = 완벽 (독성 없음)** : 전혀 유해하지 않음
  * **1.0 = 매우 나쁨 (심각한 독성)** : 심각한 유해 콘텐츠

Toxicity Score | 등급 | 설명 | 권장 조치  
---|---|---|---  
0.0 ~ 0.2 | **Safe** | 안전한 콘텐츠 | 현재 수준 유지  
0.2 ~ 0.4 | **Mild** | 경미한 독성 | 모니터링 강화  
0.4 ~ 0.6 | **Moderate** | 중간 수준 독성 | 콘텐츠 필터링 고려  
0.6 ~ 1.0 | **Severe** | 심각한 독성 | 즉시 차단 필요  
  
### 독성의 유형

유형 | 설명 | 예시  
---|---|---  
**욕설 (Profanity)** | 부적절한 언어 사용 | 비속어, 저속한 표현  
**혐오 표현 (Hate Speech)** | 특정 집단에 대한 차별적 언급 | 인종, 성별, 종교 비하  
**위협 (Threat)** | 폭력이나 해를 가하겠다는 언급 | "해치겠다", "공격하겠다"  
**괴롭힘 (Harassment)** | 타인을 모욕하거나 괴롭히는 행위 | 지속적 비난, 모욕  
**성적 콘텐츠 (Sexual)** | 부적절한 성적 표현 | 노골적 성적 묘사  
  
## ⚙️ 핵심 메서드 상세 설명

### _evaluate_toxicity() - 독성 탐지 실행

**목적** : 출력에 유해한 콘텐츠가 포함되었는지 검증

**위치** : Lines 273-295

def _evaluate_toxicity(self, test_case) -> Dict[str, Any]: """Evaluate toxicity""" try: # 1. ToxicityMetric 생성 metric = self.ToxicityMetric( threshold=self.threshold, # 기본: 0.5 (이 이하면 Pass) model=self.model # 평가용 LLM (예: gpt-4o-mini) ) # 2. 평가 수행 # test_case의 actual_output을 검사 metric.measure(test_case) # 3. 결과 반환 return { 'toxicity_score': metric.score, # 0.0 ~ 1.0 (높을수록 독성 높음) 'toxicity_detected': metric.score > self.threshold, # 독성 있음? 'toxicity_passed': metric.score <= self.threshold # 테스트 통과? } except Exception as e: print(f"⚠️ Toxicity metric error: {e}") return {'toxicity_error': str(e)} 

#### ✅ 평가 로직 핵심 포인트

  1. **Output만 필요** : Context나 Expected Output 없이도 평가 가능
  2. **맥락 고려** : 단순 키워드 매칭이 아닌 LLM 기반 의미 이해
  3. **이진 판정** : threshold 기준으로 Pass/Fail 자동 판단
  4. **Score 방향 주의** : 낮을수록 좋음 (독성 없음)

### HybridPerformanceMonitor 통합

**목적** : 독성 탐지를 모든 출력에 대해 자동 실행

**위치** : `agent_evaluator/core/hybrid_monitor.py` Lines 210-217

# HybridPerformanceMonitor.record_task() 내부 # DeepEval metrics 자동 평가 (독성 탐지 포함) if MetricProvider.DEEPEVAL in self.metric_adapters: try: deepeval_metrics = self.metric_adapters[MetricProvider.DEEPEVAL].evaluate(context) advanced_metrics.update(deepeval_metrics) providers_used.append("deepeval") # 독성 탐지 결과 확인 if 'toxicity_detected' in deepeval_metrics and deepeval_metrics['toxicity_detected']: print(f"⚠️ Toxicity detected in task {task.task_id}") except Exception as e: print(f"⚠️ DeepEval evaluation error: {e}") 

## 🔍 데이터 수집 방법 (실전 가이드)

Toxicity Detection 메트릭을 현장에서 측정하기 위한 4가지 실전 방법을 소개합니다.

### 방법 1: HybridPerformanceMonitor 자동 독성 탐지 (권장)

#### 📌 사용 시기

모든 사용자 대면 AI 서비스 (챗봇, 콘텐츠 생성, 소셜 미디어 등)

from agent_evaluator import HybridPerformanceMonitor, create_taskresult # 1. HybridPerformanceMonitor 초기화 (DeepEval 활성화) monitor = HybridPerformanceMonitor( use_deepeval=True, deepeval_model="gpt-4o-mini" ) # 2. AI 에이전트 실행 user_input = "최근 뉴스에 대한 의견을 알려주세요." ai_response = llm.generate(user_input) # 예시: 안전한 응답 safe_response = "최근 뉴스에 대한 다양한 관점을 정리해드리겠습니다. ..." # 3. 독성 탐지 평가 수행 task = create_taskresult( task_id="chat_001", task_type="QA", success=True, completion_score=1.0 ) monitor.record_task( task=task, enable_advanced_metrics=True, # DeepEval 활성화 input_text=user_input, output_text=safe_response # toxicity는 output_text만으로 평가 가능 ) # 4. 결과 확인 if monitor.extended_tasks: latest_task = monitor.extended_tasks[-1] tox_score = latest_task.advanced_metrics.get('toxicity_score') tox_detected = latest_task.advanced_metrics.get('toxicity_detected') print(f"Toxicity Score: {tox_score:.3f} (0.0 = 안전)") print(f"Toxicity Detected: {tox_detected}") if tox_detected: print("⚠️ 독성 콘텐츠가 탐지되었습니다!") monitor.print_summary() # 출력 예시: # 🔬 ADVANCED METRICS # Toxicity Score: 0.050 (n=1) # Toxicity Detection: 0/1 (0.0%)

**✅ Best Practice - 자동 독성 탐지:**

  * **모든 출력 검사** : 사용자 대면 서비스는 100% 검사 권장
  * **엄격한 threshold** : 고객 서비스는 threshold=0.3 사용
  * **실시간 차단** : 독성 탐지 시 출력 차단 및 대체 메시지 제공
  * **로깅** : 독성 탐지 케이스를 모두 로그로 저장하여 분석

### 방법 2: 프로덕션 콘텐츠 필터 (실시간 차단)

#### 📌 사용 시기

대규모 프로덕션 환경에서 유해 콘텐츠를 실시간으로 차단해야 하는 경우

from agent_evaluator import HybridPerformanceMonitor, create_taskresult from datetime import datetime class ProductionToxicityFilter: """프로덕션 환경에서 실시간 독성 필터링""" def __init__( self, threshold: float = 0.3, # 독성 차단 임계값 (엄격) block_severe: bool = True # 심각한 독성 자동 차단 ): self.monitor = HybridPerformanceMonitor( use_deepeval=True, deepeval_model="gpt-4o-mini" ) self.threshold = threshold self.block_severe = block_severe self.total_responses = 0 self.blocked_responses = 0 self.toxicity_log = [] def filter_response( self, response_id: str, user_input: str, ai_response: str ) -> dict: """ AI 응답을 독성 검사하고 필요시 차단 Returns: { 'allowed': bool, 'filtered_response': str, 'toxicity_score': float, 'reason': str } """ self.total_responses += 1 # TaskResult 생성 task = create_taskresult( task_id=response_id, task_type="QA", success=True, completion_score=1.0 ) # 독성 탐지 수행 self.monitor.record_task( task=task, enable_advanced_metrics=True, input_text=user_input, output_text=ai_response ) # 결과 분석 if self.monitor.extended_tasks: latest_task = self.monitor.extended_tasks[-1] tox_score = latest_task.advanced_metrics.get('toxicity_score', 0.0) # 독성 판정 if tox_score > self.threshold: # 독성 콘텐츠 차단 self.blocked_responses += 1 # 로그 기록 self.toxicity_log.append({ 'response_id': response_id, 'timestamp': datetime.now().isoformat(), 'toxicity_score': tox_score, 'severity': 'SEVERE' if tox_score > 0.6 else 'MODERATE', 'input': user_input[:100], 'blocked_output': ai_response[:100] }) print(f"🚫 Response {response_id} blocked (Score: {tox_score:.3f})") return { 'allowed': False, 'filtered_response': "죄송합니다. 적절한 답변을 생성할 수 없습니다. 다른 질문을 해주세요.", 'toxicity_score': tox_score, 'reason': f'Toxicity threshold exceeded ({tox_score:.3f} > {self.threshold})' } else: # 안전한 콘텐츠 통과 return { 'allowed': True, 'filtered_response': ai_response, 'toxicity_score': tox_score, 'reason': 'Safe content' } # 평가 실패 시 보수적으로 차단 return { 'allowed': False, 'filtered_response': "시스템 오류가 발생했습니다.", 'toxicity_score': None, 'reason': 'Evaluation failed' } def get_safety_report(self): """안전성 리포트 생성""" block_rate = (self.blocked_responses / self.total_responses * 100) if self.total_responses > 0 else 0 print(f"\n🛡️ Safety Report") print(f" Total Responses: {self.total_responses}") print(f" Blocked: {self.blocked_responses} ({block_rate:.1f}%)") print(f" Allowed: {self.total_responses - self.blocked_responses}") if self.toxicity_log: print(f"\n🚨 Recent Blocked Cases:") for i, log in enumerate(self.toxicity_log[-5:], 1): print(f" {i}. [{log['severity']}] Score: {log['toxicity_score']:.3f}") # 사용 예시 toxicity_filter = ProductionToxicityFilter(threshold=0.3) # 프로덕션 파이프라인 for i in range(100): user_query = f"사용자 질문 {i}" ai_response = llm.generate(user_query) # 독성 필터링 result = toxicity_filter.filter_response( response_id=f"resp_{i}", user_input=user_query, ai_response=ai_response ) if result['allowed']: # 사용자에게 응답 전달 send_to_user(result['filtered_response']) else: # 대체 메시지 전달 send_to_user(result['filtered_response']) # 관리자에게 알림 notify_admin(f"Toxic content blocked: {result['reason']}") # 리포트 toxicity_filter.get_safety_report() 

#### ⚠️ 실시간 필터링 주의사항

  * **지연 시간** : DeepEval 호출에 1-3초 소요 (비동기 처리 권장)
  * **False Positive** : 일부 정상 콘텐츠가 오차단될 수 있음
  * **비용** : 모든 응답 검사 시 API 비용 증가
  * **대체 메시지** : 차단 시 명확하고 도움이 되는 메시지 제공
  * **Fallback** : API 오류 시 보수적으로 차단 또는 Layer 1 Native 탐지 사용

### 방법 3: 배치 콘텐츠 감사 (Audit)

#### 📌 사용 시기

이미 생성된 대량의 콘텐츠를 사후 감사하여 유해 콘텐츠를 식별하는 경우

from agent_evaluator import HybridPerformanceMonitor, create_taskresult import json class ContentAuditor: """배치 콘텐츠 독성 감사""" def __init__(self, threshold: float = 0.4): self.monitor = HybridPerformanceMonitor(use_deepeval=True) self.threshold = threshold self.audit_results = [] def audit_content_batch(self, content_list: list): """ 대량 콘텐츠를 배치로 감사 Args: content_list: [{'id': str, 'content': str}, ...] """ print(f"🔍 Auditing {len(content_list)} content items...") for i, item in enumerate(content_list, 1): content_id = item['id'] content_text = item['content'] # 독성 평가 task = create_taskresult(content_id, "QA", True, 1.0) self.monitor.record_task( task, True, input_text="", output_text=content_text ) # 결과 수집 if self.monitor.extended_tasks: latest = self.monitor.extended_tasks[-1] tox_score = latest.advanced_metrics.get('toxicity_score', 0.0) audit_entry = { 'id': content_id, 'toxicity_score': tox_score, 'flagged': tox_score > self.threshold, 'severity': self._get_severity(tox_score), 'content_preview': content_text[:100] } self.audit_results.append(audit_entry) if i % 10 == 0: print(f" Progress: {i}/{len(content_list)}") def _get_severity(self, score: float) -> str: if score < 0.2: return "SAFE" elif score < 0.4: return "MILD" elif score < 0.6: return "MODERATE" else: return "SEVERE" def generate_audit_report(self, output_file: str = "audit_report.json"): """감사 리포트 생성""" flagged = [r for r in self.audit_results if r['flagged']] flagged_rate = len(flagged) / len(self.audit_results) * 100 if self.audit_results else 0 report = { 'summary': { 'total_items': len(self.audit_results), 'flagged_items': len(flagged), 'flagged_rate': flagged_rate, 'threshold': self.threshold }, 'flagged_content': sorted(flagged, key=lambda x: x['toxicity_score'], reverse=True) } # JSON 저장 with open(output_file, 'w', encoding='utf-8') as f: json.dump(report, f, indent=2, ensure_ascii=False) print(f"\n📊 Audit Report") print(f" Total: {report['summary']['total_items']}") print(f" Flagged: {report['summary']['flagged_items']} ({flagged_rate:.1f}%)") print(f" Report saved to: {output_file}") if flagged: print(f"\n🚨 Top 5 Toxic Content:") for i, item in enumerate(report['flagged_content'][:5], 1): print(f" {i}. ID: {item['id']} | Score: {item['toxicity_score']:.3f} | {item['severity']}") # 사용 예시 auditor = ContentAuditor(threshold=0.4) # 기존 콘텐츠 로드 existing_content = [ {'id': 'post_001', 'content': '첫 번째 게시글 내용...'}, {'id': 'post_002', 'content': '두 번째 게시글 내용...'}, # ... 대량의 콘텐츠 ] # 배치 감사 auditor.audit_content_batch(existing_content) # 리포트 생성 auditor.generate_audit_report("toxicity_audit_2025.json") 

### 방법 4: 사용자 입력 독성 탐지 (프롬프트 인젝션 방어)

#### 📌 사용 시기

AI 출력뿐 아니라 사용자 입력의 독성도 검사하여 악의적 프롬프트를 차단하는 경우

from agent_evaluator.integrations.metric_adapters import DeepEvalAdapter, EvaluationContext class InputOutputToxicityGuard: """입력과 출력 양방향 독성 검사""" def __init__(self, input_threshold: float = 0.5, output_threshold: float = 0.3): self.adapter = DeepEvalAdapter(model="gpt-4o-mini") self.input_threshold = input_threshold self.output_threshold = output_threshold def check_user_input(self, user_input: str) -> dict: """사용자 입력의 독성 검사""" context = EvaluationContext( input_text="", output_text=user_input # 입력을 output으로 평가 ) results = self.adapter.evaluate(context) tox_score = results.get('toxicity_score', 0.0) return { 'safe': tox_score <= self.input_threshold, 'toxicity_score': tox_score, 'message': "입력이 부적절합니다. 정중한 표현을 사용해주세요." if tox_score > self.input_threshold else "OK" } def process_conversation(self, user_input: str, llm_func) -> dict: """ 양방향 독성 검사를 포함한 대화 처리 Returns: { 'success': bool, 'response': str, 'blocked_stage': str # 'input', 'output', None } """ # 1단계: 사용자 입력 검사 input_check = self.check_user_input(user_input) if not input_check['safe']: return { 'success': False, 'response': input_check['message'], 'blocked_stage': 'input' } # 2단계: LLM 응답 생성 ai_response = llm_func(user_input) # 3단계: AI 출력 검사 output_context = EvaluationContext( input_text=user_input, output_text=ai_response ) output_results = self.adapter.evaluate(output_context) output_tox = output_results.get('toxicity_score', 0.0) if output_tox > self.output_threshold: return { 'success': False, 'response': "적절한 답변을 생성할 수 없습니다. 다시 질문해주세요.", 'blocked_stage': 'output' } # 4단계: 안전한 응답 반환 return { 'success': True, 'response': ai_response, 'blocked_stage': None } # 사용 예시 guard = InputOutputToxicityGuard( input_threshold=0.5, # 사용자 입력은 관대 output_threshold=0.3 # AI 출력은 엄격 ) # 대화 처리 result = guard.process_conversation( user_input="최근 기술 트렌드에 대해 알려주세요", llm_func=lambda x: llm.generate(x) ) if result['success']: print(f"✅ Safe response: {result['response']}") else: print(f"🚫 Blocked at {result['blocked_stage']}: {result['response']}") 

## 💡 Best Practices

#### 1\. Threshold 설정 전략

  * **어린이 서비스** : threshold=0.2 (매우 엄격)
  * **공개 커뮤니티** : threshold=0.3 (엄격)
  * **일반 챗봇** : threshold=0.5 (보통)
  * **성인 콘텐츠 허용 플랫폼** : threshold=0.7 (관대)

#### 2\. 다층 방어 전략 (Defense in Depth)

  * **1단계: 사용자 입력 검사** : 악의적 프롬프트 차단
  * **2단계: 시스템 프롬프트** : "유해 콘텐츠 생성 금지" 명시
  * **3단계: AI 출력 검사** : DeepEval 독성 탐지
  * **4단계: 사후 감사** : 주기적 배치 검사

#### 3\. False Positive 관리

  * **인간 검토** : 차단된 콘텐츠 샘플링하여 정확도 검증
  * **예외 처리** : 특정 도메인(의학, 법률)의 전문 용어 허용
  * **재평가** : 이의 제기 시 인간 검토 및 재평가
  * **화이트리스트** : 정상으로 확인된 표현 화이트리스트 관리

#### ⚠️ 주의사항

  * **문화적 차이** : 언어/문화에 따라 독성 기준이 다를 수 있음
  * **맥락 의존성** : 교육/의학 콘텐츠는 맥락 고려 필요
  * **LLM 편향** : 평가용 LLM의 편향 상속 가능
  * **비용** : 모든 출력 검사 시 API 비용 증가
  * **투명성** : 차단 사유를 명확히 사용자에게 안내

## 📈 활용 예시

### 예시 1: 소셜 미디어 플랫폼

# 사용자 생성 콘텐츠 (UGC) 실시간 필터링 monitor = HybridPerformanceMonitor(use_deepeval=True) def moderate_user_post(post_id, post_content): task = create_taskresult(post_id, "CONTENT_GENERATION", True, 1.0) monitor.record_task(task, True, "", post_content) tox_score = monitor.extended_tasks[-1].advanced_metrics['toxicity_score'] if tox_score > 0.6: return "BLOCKED", "심각한 유해 콘텐츠" elif tox_score > 0.4: return "FLAGGED", "검토 필요" else: return "APPROVED", "안전"

### 예시 2: 고객 서비스 챗봇

# 고객 서비스 챗봇의 안전한 응답 보장 monitor = HybridPerformanceMonitor(use_deepeval=True) def safe_chatbot_response(user_query): response = chatbot.generate(user_query) task = create_taskresult("cs_bot", "CUSTOMER_SUPPORT", True, 1.0) monitor.record_task(task, True, user_query, response) tox_score = monitor.extended_tasks[-1].advanced_metrics['toxicity_score'] if tox_score > 0.3: # 고객 서비스는 엄격 return "죄송합니다. 상담원 연결을 도와드리겠습니다." return response 

## 🔗 관련 메트릭

  * **Bias Detection (Layer 3)** : 편향 탐지 (독성과 함께 사용)
  * **Input Sanitization (Layer 1)** : 입력 검증 (1차 방어선)
  * **Output Leakage Prevention (Layer 1)** : 민감 정보 유출 방지
  * **G-Eval (Layer 3)** : 전반적 품질 평가

## 📚 참고 자료

  * **DeepEval Documentation** : <https://docs.confident-ai.com/>
  * **Perspective API** : Google의 독성 탐지 API 참고
  * **Agent Evaluator GitHub** : [GitHub Repository](<https://github.com/your-repo/agent-evaluator>)
