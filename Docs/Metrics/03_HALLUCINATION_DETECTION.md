# 🚨 Hallucination Detection

AI Agent Hallucination Detection and Analysis

Agent Evaluator v0.5.1 - Layer 1 Foundation Metric

## 🎯 개요

**Hallucination Detection (환각 감지)** 은 AI Agent가 제공된 컨텍스트나 사실에 근거하지 않은 정보를 생성하는 현상을 탐지하고 측정하는 Layer 1 Foundation Metric입니다. 

  * **측정 대상** : AI Agent가 근거 없는 정보를 생성하는 비율
  * **탐지 방법** : Unsupported Claims (단어 겹침 기반), Numerical Inconsistency (숫자 비교)
  * **정확도** : 70-80% (규칙 기반), Layer 3 DeepEval은 90-95% (의미 기반)
  * **구현 위치** : `agent_evaluator/core/agent_evaluator.py` (Lines 412-622)

#### ⚠️ Hallucination의 위험성

  * **잘못된 의사결정** : 거짓 정보 기반의 판단
  * **법적/윤리적 문제** : 의료, 법률, 금융 분야에서 치명적
  * **브랜드 신뢰도 하락** : 사용자가 Agent를 신뢰하지 않음
  * **비용 증가** : 사람이 모든 응답을 검증해야 함

#### 🏗️ 구현 특징

  * **클래스** : `HallucinationDetector` (agent_evaluator.py:412-622)
  * **탐지 방식** : 2가지 규칙 기반 알고리즘 (Unsupported Claims, Numerical Inconsistency)
  * **외부 의존성** : 없음 (Layer 1 Native Metric)
  * **성능** : 매우 빠름 (0.01초), 무료
  * **한계** : 패러프레이징/요약 오탐, 의미적 환각 미탐지

## 📊 Hallucination 유형

### 유형 분류

유형 | 설명 | 예시 | 심각도  
---|---|---|---  
**Unsupported Claims** | 컨텍스트에 없는 주장 | 문서: "서울의 인구"  
응답: "서울의 인구는 2천만명" | Medium  
**Numerical Inconsistency** | 숫자 조작/추가 | 문서: "100명 참석"  
응답: "500명이 참석했음" | High  
**Semantic Hallucination** | 의미적으로 틀린 정보 | 문서: "강아지는 포유류"  
응답: "강아지는 파충류" | High  
**Temporal Inconsistency** | 시간 정보 오류 | 문서: "2023년 발생"  
응답: "1990년에 일어남" | High  
  
### Layer 1 vs Layer 3 비교

#### 📊 두 가지 탐지 방식 비교

특성 | Layer 1 (Rule-Based) | Layer 3 (DeepEval Semantic)  
---|---|---  
**정확도** | 70-80% | 90-95%  
**속도** | 매우 빠름 (0.01초) | 느림 (1-3초, API 호출)  
**비용** | 무료 | LLM API 비용 발생  
**탐지 방식** | 단어 겹침, 숫자 비교 | 의미적 분석 (LLM 기반)  
**False Positive** | 높음 (패러프레이징 오탐) | 낮음  
**사용 권장** | 개발/테스트, 빠른 체크 | 프로덕션, 정확도 중요  
  
## 🏗️ 구현 위치 및 클래스 구조

### 파일 위치

# 구현 파일 agent_evaluator/core/agent_evaluator.py # 클래스 정의 class HallucinationDetector: # Lines 412-622 """ Rule-based hallucination detector (Layer 1 Native Metric) ⚠️ LIMITATIONS: \- Pattern-based detection (70-80% accuracy) \- May flag valid paraphrasing/summarization as hallucination \- Cannot detect semantic hallucinations (e.g., factual errors) ✅ STRENGTHS: \- Fast execution (no API calls) \- Free (no external dependencies) \- Good for detecting obvious inconsistencies 📈 FOR PRODUCTION USE: \- Use HybridPerformanceMonitor with DeepEval \- DeepEval provides 90-95% accuracy with LLM-based analysis """

### 클래스 구조

메서드 | 라인 | 설명  
---|---|---  
`__init__()` | 442-443 | 탐지 결과 목록 초기화  
`detect_hallucination()` | 445-518 | **환각 탐지 (2가지 방법)**  
`get_hallucination_rate()` | 520-555 | 전체 환각 통계  
`get_hallucination_by_type()` | 557-621 | 유형별/심각도별 분석  
  
## ⚙️ 핵심 탐지 알고리즘

#### 📊 Hallucination Detection 흐름 다이어그램

graph TD A[response, context, ground_truth] --> B[1. Unsupported Claims 검사] B --> B1[response를 문장 단위로 분리] B1 --> B2{각 문장 loop} B2 --> B3[context와 단어 겹침 비율 계산] B3 --> B4{overlap < 30%?} B4 -->|Yes| B5[unsupported_claim 추가  
severity: medium] B4 -->|No| B2 A --> C[2. Numerical Inconsistency 검사] C --> C1[response에서 숫자 추출] C --> C2[context에서 숫자 추출] C1 --> C3{response 숫자가  
context에 없음?} C3 -->|Yes| C4[numerical_inconsistency 추가  
severity: high] B5 --> D[hallucination_rate 계산] C4 --> D D --> E[result 반환  
indicators, rate, severity] style A fill:#667eea,color:#fff style B fill:#48bb78,color:#fff style C fill:#48bb78,color:#fff style D fill:#3182ce,color:#fff style E fill:#667eea,color:#fff style B5 fill:#e53e3e,color:#fff style C4 fill:#e53e3e,color:#fff 

### 알고리즘 1: Unsupported Claims 탐지

**목적** : 컨텍스트에 근거하지 않은 문장 찾기

**기준** : 문장과 컨텍스트 간 단어 겹침 < 30%

def detect_unsupported_claims(response, context): # 1. 응답을 문장으로 분리 response_sentences = [s.strip() for s in response.split('.') if s.strip()] # 2. 컨텍스트 단어 집합 context_words = set(context.lower().split()) hallucination_indicators = [] for sentence in response_sentences: sentence_words = set(sentence.lower().split()) # 빈 문장 스킵 (ZeroDivisionError 방지) if len(sentence_words) == 0: continue # 3. 단어 겹침 계산 overlap = len(sentence_words & context_words) overlap_ratio = overlap / len(sentence_words) # 4. 30% 미만 겹침 + 5단어 이상 → 환각 의심 if len(sentence_words) > 5 and overlap_ratio < 0.3: hallucination_indicators.append({ "type": "unsupported_claim", "sentence": sentence.strip(), "overlap_ratio": overlap_ratio, "severity": "medium" }) return hallucination_indicators 

#### 💡 30% 임계값 선택 이유

  * **너무 낮으면** : False Negative 증가 (진짜 환각을 놓침)
  * **너무 높으면** : False Positive 증가 (정상 문장을 환각으로 오탐)
  * **30%** : 경험적으로 적절한 균형점 (조정 가능)

#### ⚠️ Unsupported Claims 탐지의 한계

  * **패러프레이징 오탐** : "자동차" vs "차량" → 다른 단어로 인식
  * **요약 오탐** : 요약은 원문 단어를 적게 사용하므로 환각으로 오판
  * **번역 오탐** : 영한 번역 시 단어 겹침이 0%
  * **해결책** : Layer 3 DeepEval 사용 (의미적 유사도 분석)

### 알고리즘 2: Numerical Inconsistency 탐지

**목적** : 응답의 숫자가 컨텍스트/정답에 없으면 환각

**정확도** : 매우 높음 (숫자는 명확하므로)

import re def detect_numerical_inconsistency(response, context, ground_truth): # 1. 정규표현식으로 숫자 추출 response_numbers = re.findall(r'\d+\\.?\d*', response) context_numbers = re.findall(r'\d+\\.?\d*', context) ground_truth_numbers = re.findall(r'\d+\\.?\d*', ground_truth) if ground_truth else [] hallucination_indicators = [] # 2. 응답의 각 숫자가 원본에 있는지 확인 for num in response_numbers: if num not in context_numbers and num not in ground_truth_numbers: hallucination_indicators.append({ "type": "numerical_inconsistency", "value": num, "severity": "high" # 숫자 환각은 심각 }) return hallucination_indicators # 예시: # Context: "2023년 서울 인구는 약 970만명" # Response: "2023년 서울 인구는 1500만명" # → "1500" 탐지 (컨텍스트에 없음)

#### ✅ Numerical Inconsistency의 강점

  * **높은 정확도** : 숫자는 명확하여 오탐률 낮음
  * **심각한 오류 탐지** : 재무, 통계, 측정값 오류 발견
  * **즉시 적용 가능** : 추가 설정 없이 동작

### Hallucination Rate 계산

# 공식: # Hallucination Rate = (환각 지표 수) / (전체 문장 수) if not response_sentences: hallucination_rate = 1.0 # 빈 응답 = 100% 환각 else: hallucination_rate = len(hallucination_indicators) / len(response_sentences) # 예시: # Response: 5개 문장 # 환각 지표: 2개 (unsupported claim 1개, numerical error 1개) # Rate: 2 / 5 = 0.4 = 40%

## 💻 사용 예제

### 기본 사용 예제

from agent_evaluator import PerformanceMonitor # 1. 환각 감지 활성화 monitor = PerformanceMonitor( enable_hallucination_detection=True ) # 2. RAG 작업 수행 context = """ 2023년 서울의 인구는 약 970만명입니다. 서울은 대한민국의 수도이자 최대 도시입니다. """ question = "서울의 인구는?" agent_response = "서울의 인구는 약 1500만명이며, 한국에서 가장 큰 도시입니다." ground_truth = "970만명" # 3. 작업 기록 (환각 자동 감지) monitor.record_task( task_id="rag_001", task_type="QA", success=True, latency=1.2, completion_score=0.7, # 부분 정답 (1500 틀림) expected_output=ground_truth, actual_output=agent_response, ground_truth=ground_truth, context=context # 환각 탐지에 필요 ) # 4. 환각 통계 확인 hall_stats = monitor.hallucination_detector.get_hallucination_rate() print(f"Overall Hallucination Rate: {hall_stats['overall_rate']}%") print(f"Tasks with Hallucinations: {hall_stats['tasks_with_hallucinations']}") print(f"Unsupported Claims: {hall_stats['unsupported_claims_count']}") print(f"Numerical Errors: {hall_stats['numerical_inconsistencies_count']}") # 예상 출력: # Overall Hallucination Rate: 50% (1개 환각 / 2개 문장) # Tasks with Hallucinations: 1 # Numerical Errors: 1 ("1500" 탐지)

### 상세 환각 분석

from agent_evaluator import PerformanceMonitor monitor = PerformanceMonitor(enable_hallucination_detection=True) # 여러 작업 평가 test_cases = [ { "context": "AI는 인공지능의 약자입니다.", "response": "AI는 Artificial Intelligence의 약자이며 1956년에 처음 개발되었습니다.", "ground_truth": "인공지능의 약자" }, { "context": "파이썬 3.11이 2022년 10월에 출시되었습니다.", "response": "파이썬 3.11은 2021년 5월에 출시되어 30% 성능 향상을 보여줍니다.", "ground_truth": "2022년 10월" } ] for i, case in enumerate(test_cases): monitor.record_task( task_id=f"test_{i}", task_type="QA", success=True, latency=1.0, completion_score=0.8, expected_output=case["ground_truth"], actual_output=case["response"], ground_truth=case["ground_truth"], context=case["context"] ) # 유형별 환각 분석 by_type = monitor.hallucination_detector.get_hallucination_by_type() print("\n=== Hallucination Analysis ===") print(f"Total Hallucinations: {by_type['total_hallucinations']}") print(f"Unsupported Claims: {by_type['unsupported_claims']}") print(f"Numerical Errors: {by_type['numerical_errors']}") print(f"Temporal Errors: {by_type['temporal_errors']}") print(f"\nBy Severity:") print(f" High: {by_type['by_severity']['high']}") print(f" Medium: {by_type['by_severity']['medium']}") print(f" Low: {by_type['by_severity']['low']}") 

### Production 환경 - DeepEval 통합

from agent_evaluator import HybridPerformanceMonitor # Layer 1 + Layer 3 결합 (권장) monitor = HybridPerformanceMonitor( use_deepeval=True, # 의미적 환각 탐지 enable_hallucination_detection=True, # 규칙 기반 환각 탐지 deepeval_model="gpt-4o-mini" ) # 작업 실행 monitor.record_task( task_id="prod_001", task_type="QA", success=True, latency=2.5, completion_score=1.0, expected_output="Expected answer", actual_output=agent_response, ground_truth=ground_truth, context=context ) # Layer 1 환각률 layer1_hall = monitor.hallucination_detector.get_hallucination_rate() print(f"Layer 1 Hallucination: {layer1_hall['overall_rate']}%") # Layer 3 환각률 (DeepEval) report = monitor.generate_hybrid_report() if 'deepeval_hallucination' in report.get('advanced_metrics', {}): deepeval_hall = report['advanced_metrics']['deepeval_hallucination'] print(f"DeepEval Hallucination Score: {deepeval_hall['score']}") print(f"Hallucination Detected: {deepeval_hall['detected']}") 

## 📦 Layer 1 평가를 위한 데이터 수집 가이드

**Hallucination Detection (Layer 1)** 은 context와 response를 비교하여 환각을 탐지합니다.  
Accuracy와 달리 **ground_truth는 선택 사항** 이며, context만 있으면 평가가 가능합니다. 

### 필수 데이터 vs 선택 데이터

데이터 종류 | 필수/선택 | 목적 | 수집 방법  
---|---|---|---  
**context** | 필수 | 환각 탐지 기준 (참조 문서) | RAG 검색 결과, 수동 작성  
**response** | 필수 | 평가 대상 (Agent 응답) | Agent 실행 결과  
**ground_truth** | 선택 | 숫자 검증 정확도 향상 | 수동 작성, Golden Dataset  
**question** | 선택 | 테스트 케이스 식별 | 수동 작성  
  
### 데이터 수집 방법 1: RAG 시스템 활용 (자동화)

#### ✅ 가장 효율적인 방법

RAG 시스템을 사용하면 **context를 자동으로 수집** 할 수 있어 가장 효율적입니다.

from langchain.vectorstores import FAISS from langchain.embeddings import OpenAIEmbeddings from agent_evaluator import PerformanceMonitor, TaskType # 1. RAG 시스템 구축 embeddings = OpenAIEmbeddings() vectorstore = FAISS.load_local("my_knowledge_base", embeddings) # 2. Hallucination Detection 활성화 monitor = PerformanceMonitor(enable_hallucination_detection=True) # 3. 질문 리스트 (수동 준비) questions = [ "서울의 인구는?", "Python은 언제 만들어졌나요?", "지구의 자전 주기는?" ] # 4. 각 질문에 대해 평가 for i, question in enumerate(questions): # Context 자동 검색 (RAG) retrieved_docs = vectorstore.similarity_search(question, k=3) context = "\n\n".join([doc.page_content for doc in retrieved_docs]) # Agent 실행 agent_response = your_agent.run(question) # 평가 기록 (context 자동 제공!) monitor.record_task( task_id=f"rag_{i:03d}", task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, context=context, ← RAG에서 자동 수집 response=agent_response ) # 5. 환각 통계 확인 hall_stats = monitor.hallucination_detector.get_hallucination_rate() print(f"Hallucination Rate: {hall_stats['overall_rate']}%") 

**💡 RAG 활용 장점**

  * **완전 자동화** : Context 수동 작성 불필요
  * **실제 환경 반영** : 프로덕션과 동일한 검색 결과 사용
  * **확장성** : 수백 개 질문도 자동 처리

### 데이터 수집 방법 2: Golden Dataset 활용 (반자동화)

**Golden Dataset에 context 필드 추가** 하여 체계적으로 관리합니다.

#### Step 1: Golden Dataset JSON 작성

# hallucination_test_dataset.json { "dataset_id": "hallucination_test_001", "source_document": "Hallucination Detection Test Cases", "created_at": "2024-12-16", "total_qa_pairs": 3, "metadata": { "dataset_name": "Hallucination Detection Dataset", "version": "0.5.0", "description": "Context 포함 환각 탐지 테스트용" }, "qa_pairs": [ { "qa_id": "qa_001", "question": "서울의 인구는?", "context": "서울은 대한민국의 수도이며, 약 970만 명의 인구가 살고 있습니다.", "ground_truth": "970만명", "task_type": "qa" }, { "qa_id": "qa_002", "question": "Python은 언제 만들어졌나요?", "context": "Python은 1991년 Guido van Rossum이 개발한 프로그래밍 언어입니다.", "ground_truth": "1991년", "task_type": "qa" }, { "qa_id": "qa_003", "question": "지구의 자전 주기는?", "context": "지구는 약 24시간(정확히는 23시간 56분)에 한 바퀴 자전합니다.", "ground_truth": "24시간", "task_type": "qa" } ] } 

#### Step 2: Golden Dataset 로드 및 평가

import json from pathlib import Path from agent_evaluator import PerformanceMonitor, TaskType # 1. Golden Dataset 로드 dataset_path = Path("hallucination_test_dataset.json") with open(dataset_path, 'r', encoding='utf-8') as f: golden_data = json.load(f) # 2. Monitor 초기화 monitor = PerformanceMonitor(enable_hallucination_detection=True) print(f"✅ Golden Dataset 로드: {golden_data['metadata']['dataset_name']}") print(f" 총 {golden_data['total_qa_pairs']}개 테스트 케이스\n") # 3. 각 케이스 평가 for qa_pair in golden_data["qa_pairs"]: print(f"평가 중: {qa_pair['qa_id']} - {qa_pair['question']}") # Agent 실행 agent_response = your_agent.run(qa_pair["question"]) # 평가 기록 (context 자동 제공) monitor.record_task( task_id=qa_pair["qa_id"], task_type=getattr(TaskType, qa_pair["task_type"].upper(), TaskType.QA), success=True, latency=1.0, completion_score=1.0, context=qa_pair["context"], ← Golden Dataset에서 response=agent_response, ground_truth=qa_pair["ground_truth"] ← 선택 (숫자 검증) ) # 4. 결과 확인 hall_stats = monitor.hallucination_detector.get_hallucination_rate() print(f"\n=== Hallucination Detection Results ===") print(f"Overall Rate: {hall_stats['overall_rate']}%") print(f"Tasks with Hallucinations: {hall_stats['tasks_with_hallucinations']}") print(f"Unsupported Claims: {hall_stats['unsupported_claims_count']}") print(f"Numerical Errors: {hall_stats['numerical_inconsistencies_count']}") 

### 데이터 수집 방법 3: 수동 작성 (완전 수동)

RAG 시스템이 없고 Golden Dataset도 없는 경우, **context를 직접 작성** 합니다.

#### Context 작성 가이드

#### ⚠️ Context 작성 시 주의사항

  * **사실 기반** : 검증 가능한 정보만 포함
  * **명확성** : 모호한 표현 피하기
  * **관련성** : 질문과 직접 관련된 정보만
  * **충분한 정보** : 답변에 필요한 모든 근거 포함

from agent_evaluator import PerformanceMonitor, TaskType # 1. Context 수동 작성 (딕셔너리로 관리) test_data = { "qa_001": { "question": "서울의 인구는?", "context": """ 서울은 대한민국의 수도이며, 약 970만 명의 인구가 살고 있습니다. 서울은 한강을 중심으로 발전한 대도시입니다. 2023년 기준 서울의 면적은 약 605km²입니다. """.strip(), "ground_truth": "970만명" }, "qa_002": { "question": "Python은 언제 만들어졌나요?", "context": """ Python은 1991년 네덜란드 프로그래머 Guido van Rossum이 개발한 프로그래밍 언어입니다. Python이라는 이름은 BBC 코미디 프로그램 'Monty Python's Flying Circus'에서 따왔습니다. """.strip(), "ground_truth": "1991년" }, "qa_003": { "question": "지구의 자전 주기는?", "context": """ 지구는 약 24시간(정확히는 23시간 56분 4초)에 한 바퀴 자전합니다. 이를 항성일이라고 합니다. """.strip(), "ground_truth": "24시간" } } # 2. Monitor 초기화 monitor = PerformanceMonitor(enable_hallucination_detection=True) # 3. 평가 실행 for task_id, data in test_data.items(): print(f"평가: {task_id} - {data['question']}") # Agent 실행 agent_response = your_agent.run(data["question"]) # 평가 기록 monitor.record_task( task_id=task_id, task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, context=data["context"], ← 수동 작성한 Context response=agent_response, ground_truth=data["ground_truth"] ← 선택 ) # 4. 결과 확인 hall_stats = monitor.hallucination_detector.get_hallucination_rate() print(f"\nHallucination Rate: {hall_stats['overall_rate']}%") 

### Context 작성 예시 비교

항목 | 좋은 예시 ✅ | 나쁜 예시 ❌  
---|---|---  
**명확성** | "서울의 인구는 970만명입니다." | "서울 인구는 많아요."  
**구체성** | "Python은 1991년에 개발되었습니다." | "Python은 오래전에 만들어졌습니다."  
**검증 가능성** | "지구는 23시간 56분 4초에 한 바퀴 자전합니다." | "지구는 하루에 한 번 돕니다."  
**관련성** | "서울 인구: 970만명, 면적: 605km²" | "서울은 아름다운 도시이며 관광지가 많습니다."  
  
### 데이터 수집 워크플로우 선택 가이드

**🎯 상황별 최적 방법**  
  
**RAG 시스템 있음** | → 방법 1 (자동화) 추천  
---|---  
**체계적 관리 필요** | → 방법 2 (Golden Dataset) 추천  
**소규모 테스트** | → 방법 3 (수동 작성) 추천  
**대량 평가 (100+ 케이스)** | → 방법 1 필수  
  
### Dashboard 연계 저장

수집한 데이터로 평가한 결과를 Dashboard에 저장하여 시각화합니다.

from agent_evaluator.utils.dashboard_integration import save_to_dashboard # 평가 완료 후 Dashboard 저장 result_path = save_to_dashboard( monitor, filename="hallucination_test_results.json", prefer_dashboard=True, verbose=True ) # 출력: # 📁 Dashboard 저장소에 저장됨 # 경로: .../Dashboard/data/evaluation_results/hallucination_test_results.json # 💡 Dashboard에서 바로 확인 가능합니다!

### 데이터 품질 검증

#### ✅ Context 품질 체크리스트

  1. **정확성** : 모든 정보가 사실인가?
  2. **완전성** : 답변에 필요한 모든 정보 포함?
  3. **명확성** : 모호한 표현 없이 명확한가?
  4. **관련성** : 질문과 직접 관련된 정보만 있나?
  5. **일관성** : 내부적으로 모순이 없나?

# Context 품질 검증 예시 # ✅ 좋은 Context good_context = """ 서울은 대한민국의 수도입니다. 2023년 기준 서울의 인구는 약 970만 명입니다. 서울의 면적은 약 605km²입니다. """ # ❌ 나쁜 Context (모호함) bad_context = """ 서울은 큰 도시입니다. 많은 사람들이 살고 있습니다. 아름다운 곳입니다. """ # Context 검증 함수 def validate_context(context: str) -> bool: \"\"\"Context에 숫자나 구체적 정보가 있는지 확인\"\"\" import re has_numbers = bool(re.search(r'\d+', context)) has_specifics = len(context.split()) > 10 return has_numbers and has_specifics print(validate_context(good_context)) # True print(validate_context(bad_context)) # False

## 🤖 평가 데이터 자동 처리 방안

**실제 프로젝트에서는 수백~수천 개의 응답을 환각 탐지해야 합니다.**  
Hallucination Detection은 context (참조 문서)가 핵심이므로, context를 자동으로 수집하고 관리하는 전략이 중요합니다. 

### 자동화 수준별 전략

레벨 | 자동화 범위 | Context 수집 방법 | 적용 시나리오  
---|---|---|---  
**Level 1** | RAG 자동 연계 | Vector DB 자동 검색 | RAG 시스템 보유  
**Level 2** | Golden Dataset 기반 | 사전 준비된 context | 벤치마크, 반복 평가  
**Level 3** | LLM 기반 Context 생성 | 지식 베이스 → Context 추출 | Context 자동 생성 필요  
**Level 4** | 웹 크롤링 기반 | 실시간 웹 검색 | 최신 정보 검증  
**Level 5** | 하이브리드 | 복합 전략 | 프로덕션 환경  
  
### Level 1: RAG 시스템 자동 연계 (완전 자동화)

#### 💡 핵심 아이디어

RAG 시스템의 검색 결과를 context로 자동 사용합니다.

**장점** : Context 수동 작성 불필요, 프로덕션과 동일한 환경

**단점** : RAG 시스템 필요

from langchain.vectorstores import FAISS from langchain.embeddings import OpenAIEmbeddings from agent_evaluator import PerformanceMonitor, TaskType from concurrent.futures import ThreadPoolExecutor class RAGHallucinationAutoEvaluator: """RAG 시스템 기반 완전 자동 환각 탐지""" def __init__(self, vectorstore, monitor: PerformanceMonitor): self.vectorstore = vectorstore self.monitor = monitor def evaluate_question(self, question: str, task_id: str) -> dict: """단일 질문에 대한 환각 탐지""" try: # 1. Context 자동 검색 (RAG) retrieved_docs = self.vectorstore.similarity_search( question, k=3 # Top 3 문서 ) context = "\n\n".join([doc.page_content for doc in retrieved_docs]) # 2. Agent 실행 agent_response = your_agent.run(question, context=context) # 3. 환각 탐지 (자동) self.monitor.record_task( task_id=task_id, task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, context=context, ← 자동 수집된 Context response=agent_response ) return { "task_id": task_id, "question": question, "context_length": len(context.split()), "success": True } except Exception as e: return { "task_id": task_id, "success": False, "error": str(e) } def batch_evaluate(self, questions: list[str], parallel: bool = True): """대량 질문 배치 평가""" print(f"🚀 {len(questions)}개 질문 환각 탐지 시작...\n") if parallel: # 병렬 처리 (10배 빠름) with ThreadPoolExecutor(max_workers=10) as executor: tasks = [ (q, f"rag_{i:03d}") for i, q in enumerate(questions) ] results = list(executor.starmap( self.evaluate_question, tasks )) else: # 순차 처리 results = [ self.evaluate_question(q, f"rag_{i:03d}") for i, q in enumerate(questions) ] # 통계 출력 success_count = sum(1 for r in results if r["success"]) print(f"\n✅ 평가 완료: {success_count}/{len(questions)}") # 환각 통계 hall_stats = self.monitor.hallucination_detector.get_hallucination_rate() print(f"Overall Hallucination Rate: {hall_stats['overall_rate']}%") print(f"Tasks with Hallucinations: {hall_stats['tasks_with_hallucinations']}") return results # ============================================================ # 사용 예시 # ============================================================ # 1. RAG 시스템 로드 embeddings = OpenAIEmbeddings() vectorstore = FAISS.load_local("my_knowledge_base", embeddings) # 2. 환각 탐지 활성화 monitor = PerformanceMonitor(enable_hallucination_detection=True) # 3. 자동 평가기 초기화 evaluator = RAGHallucinationAutoEvaluator(vectorstore, monitor) # 4. 질문 리스트 (수동 준비 또는 자동 생성) questions = [ "서울의 인구는 얼마인가요?", "Python은 언제 만들어졌나요?", "지구의 자전 주기는?", # ... 수백 개 더 ] # 5. 배치 평가 (병렬) results = evaluator.batch_evaluate(questions, parallel=True) # 6. Dashboard 저장 from agent_evaluator.utils.dashboard_integration import save_to_dashboard save_to_dashboard(monitor, filename="hallucination_auto_eval.json") 

### Level 2: Golden Dataset 기반 자동 평가

#### 💡 핵심 아이디어

사전 준비된 Golden Dataset에 context 필드를 포함하여 반복 평가합니다.

**장점** : 재현 가능, 벤치마킹 용이

**단점** : Golden Dataset 작성 필요

import json from pathlib import Path from agent_evaluator import PerformanceMonitor, TaskType # ============================================================ # Golden Dataset 구조 (context 포함) # ============================================================ # hallucination_golden_dataset.json golden_dataset_structure = { "dataset_id": "hallucination_test_v1", "metadata": { "dataset_name": "Hallucination Detection Golden Dataset", "version": "0.5.0" }, "qa_pairs": [ { "qa_id": "qa_001", "question": "서울의 인구는?", "context": "서울은 대한민국의 수도이며 약 970만명이 거주합니다.", "ground_truth": "970만명", # 선택 (숫자 검증용) "task_type": "qa" } ] } # ============================================================ # Golden Dataset 로드 및 평가 # ============================================================ dataset_path = Path("Evaluator_Examples/Dashboard/data/golden_datasets/hallucination_test.json") with open(dataset_path, 'r', encoding='utf-8') as f: golden_data = json.load(f) monitor = PerformanceMonitor(enable_hallucination_detection=True) print(f"📦 Golden Dataset: {golden_data['metadata']['dataset_name']}") print(f" 총 {len(golden_data['qa_pairs'])}개 테스트 케이스\n") # 각 케이스 평가 for qa_pair in golden_data["qa_pairs"]: print(f"평가: {qa_pair['qa_id']}") # Agent 실행 agent_response = your_agent.run(qa_pair["question"]) # 환각 탐지 (context 자동 제공) monitor.record_task( task_id=qa_pair["qa_id"], task_type=getattr(TaskType, qa_pair["task_type"].upper(), TaskType.QA), success=True, latency=1.0, completion_score=1.0, context=qa_pair["context"], ← Golden Dataset에서 response=agent_response, ground_truth=qa_pair.get("ground_truth") ← 선택 ) # 결과 확인 hall_stats = monitor.hallucination_detector.get_hallucination_rate() print(f"\n✅ Hallucination Rate: {hall_stats['overall_rate']}%") print(f"Unsupported Claims: {hall_stats['unsupported_claims_count']}") print(f"Numerical Errors: {hall_stats['numerical_inconsistencies_count']}") 

### Level 3: LLM 기반 Context 자동 생성

#### 💡 핵심 아이디어

지식 베이스나 문서가 있지만 RAG 시스템이 없는 경우, LLM을 사용해 Context를 추출합니다.

**장점** : RAG 없이도 자동화 가능

**단점** : LLM 비용, 추출 품질 의존

from agent_evaluator import PerformanceMonitor, TaskType from openai import OpenAI class LLMContextGenerator: """LLM을 사용한 Context 자동 생성""" def __init__(self, api_key: str, knowledge_base: str): self.client = OpenAI(api_key=api_key) self.knowledge_base = knowledge_base # 전체 지식 베이스 텍스트 def generate_context(self, question: str) -> str: """질문에 대한 Context를 지식 베이스에서 추출""" prompt = f""" 다음 지식 베이스에서 질문에 답변하는 데 필요한 정보만 추출하세요. 관련 없는 정보는 제외하고, 핵심 사실만 간결하게 정리하세요. 지식 베이스: {self.knowledge_base[:3000]} # 토큰 제한 고려 질문: {question} 추출된 Context (사실 기반, 100-200 단어):""" completion = self.client.chat.completions.create( model="gpt-4o-mini", # 비용 절감 messages=[ {"role": "system", "content": "당신은 정확한 정보 추출 전문가입니다."}, {"role": "user", "content": prompt} ], temperature=0.0 ) context = completion.choices[0].message.content.strip() return context def evaluate_with_generated_context( self, questions: list[str], monitor: PerformanceMonitor ): """Context 생성 + 환각 탐지""" for i, question in enumerate(questions): print(f"\n[{i+1}/{len(questions)}] {question}") # 1. Context 자동 생성 print(" 🔍 Context 생성 중...") context = self.generate_context(question) print(f" ✅ Context ({len(context.split())} 단어)") # 2. Agent 실행 agent_response = your_agent.run(question) # 3. 환각 탐지 monitor.record_task( task_id=f"llm_gen_{i:03d}", task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, context=context, ← LLM이 생성한 Context response=agent_response ) # 결과 통계 hall_stats = monitor.hallucination_detector.get_hallucination_rate() print(f"\n📊 Hallucination Rate: {hall_stats['overall_rate']}%") # ============================================================ # 사용 예시 # ============================================================ # 지식 베이스 로드 (예: 회사 문서, 제품 매뉴얼 등) with open("knowledge_base.txt", 'r') as f: knowledge_base = f.read() # Context 생성기 초기화 context_gen = LLMContextGenerator( api_key="your-api-key", knowledge_base=knowledge_base ) # 환각 탐지 모니터 monitor = PerformanceMonitor(enable_hallucination_detection=True) # 평가할 질문 리스트 questions = [ "제품 A의 가격은?", "배송 기간은 얼마나 걸리나요?", "환불 정책은?" ] # Context 자동 생성 + 평가 context_gen.evaluate_with_generated_context(questions, monitor) 

### Level 4: 웹 크롤링 기반 실시간 검증

#### 💡 핵심 아이디어

최신 정보나 실시간 데이터에 대해 웹 검색으로 Context를 자동 수집합니다.

**장점** : 최신 정보 검증 가능

**단점** : 느림, 웹 검색 API 필요

from agent_evaluator import PerformanceMonitor, TaskType import requests from bs4 import BeautifulSoup class WebSearchContextCollector: """웹 검색 기반 Context 자동 수집""" def __init__(self, search_api_key: str): self.api_key = search_api_key def search_and_extract(self, query: str) -> str: """Google Custom Search API 사용""" # Google Custom Search API 호출 search_url = f"https://www.googleapis.com/customsearch/v1" params = { "key": self.api_key, "cx": "your-search-engine-id", "q": query, "num": 3 # Top 3 결과 } response = requests.get(search_url, params=params) search_results = response.json() # 검색 결과에서 snippet 추출 snippets = [] for item in search_results.get("items", []): snippets.append(item["snippet"]) context = "\n\n".join(snippets) return context def evaluate_with_web_search( self, questions: list[str], monitor: PerformanceMonitor ): """웹 검색 Context + 환각 탐지""" for i, question in enumerate(questions): print(f"\n[{i+1}/{len(questions)}] {question}") # 1. 웹 검색으로 Context 수집 print(" 🌐 웹 검색 중...") context = self.search_and_extract(question) print(f" ✅ Context 수집 완료") # 2. Agent 실행 agent_response = your_agent.run(question) # 3. 환각 탐지 monitor.record_task( task_id=f"web_{i:03d}", task_type=TaskType.QA, success=True, latency=2.0, # 웹 검색 시간 포함 completion_score=1.0, context=context, ← 웹 검색 결과 response=agent_response ) hall_stats = monitor.hallucination_detector.get_hallucination_rate() print(f"\n📊 Hallucination Rate: {hall_stats['overall_rate']}%") # ============================================================ # 사용 예시 (최신 정보 검증) # ============================================================ web_collector = WebSearchContextCollector(search_api_key="your-api-key") monitor = PerformanceMonitor(enable_hallucination_detection=True) # 최신 정보 질문 questions = [ "2024년 한국 GDP는?", "최신 iPhone 모델의 가격은?", "오늘 서울 날씨는?" ] web_collector.evaluate_with_web_search(questions, monitor) 

### Level 5: 하이브리드 Context 수집 전략

#### 💡 핵심 아이디어

여러 소스를 조합하여 최적의 Context를 구성합니다.

from agent_evaluator import PerformanceMonitor, TaskType class HybridContextCollector: """복합 전략 Context 수집""" def __init__( self, vectorstore=None, knowledge_base: str = None, web_search_api: str = None ): self.vectorstore = vectorstore self.knowledge_base = knowledge_base self.web_search_api = web_search_api def collect_context(self, question: str) -> dict: """질문 유형에 따라 최적 방법 선택""" contexts = [] sources = [] # 전략 1: RAG 시스템 (최우선) if self.vectorstore: try: docs = self.vectorstore.similarity_search(question, k=2) rag_context = "\n".join([d.page_content for d in docs]) contexts.append(rag_context) sources.append("rag") except: pass # 전략 2: 지식 베이스 (보조) if self.knowledge_base and len(contexts) < 2: # 간단한 키워드 검색 keywords = question.lower().split()[:3] for keyword in keywords: if keyword in self.knowledge_base.lower(): # 관련 단락 추출 (간단한 휴리스틱) idx = self.knowledge_base.lower().find(keyword) snippet = self.knowledge_base[max(0, idx-200):idx+200] contexts.append(snippet) sources.append("knowledge_base") break # 전략 3: 웹 검색 (최신 정보 필요 시) if self.web_search_api and self.is_recent_info_query(question): # 웹 검색 로직 (생략) pass # 최종 Context 결합 final_context = "\n\n---\n\n".join(contexts) if contexts else "" return { "context": final_context, "sources": sources, "confidence": len(contexts) / 3.0 # 소스 다양성 } def is_recent_info_query(self, question: str) -> bool: """최신 정보 질문인지 판단""" recent_keywords = ["2024", "최신", "오늘", "현재", "지금"] return any(kw in question for kw in recent_keywords) def evaluate_with_hybrid( self, questions: list[str], monitor: PerformanceMonitor ): """하이브리드 전략 평가""" for i, question in enumerate(questions): print(f"\n[{i+1}/{len(questions)}] {question}") # Context 수집 (자동 전략 선택) context_data = self.collect_context(question) print(f" 📚 Sources: {', '.join(context_data['sources'])}") print(f" 🎯 Confidence: {context_data['confidence']*100:.0f}%") # Agent 실행 agent_response = your_agent.run(question) # 환각 탐지 monitor.record_task( task_id=f"hybrid_{i:03d}", task_type=TaskType.QA, success=True, latency=1.5, completion_score=1.0, context=context_data["context"], response=agent_response ) hall_stats = monitor.hallucination_detector.get_hallucination_rate() print(f"\n📊 Final Hallucination Rate: {hall_stats['overall_rate']}%") # ============================================================ # 사용 예시 # ============================================================ hybrid_collector = HybridContextCollector( vectorstore=vectorstore, # RAG knowledge_base=knowledge_base_text, # 보조 web_search_api=api_key # 최신 정보 ) monitor = PerformanceMonitor(enable_hallucination_detection=True) questions = [ "서울의 인구는?", # → RAG "회사 휴가 정책은?", # → Knowledge Base "2024년 최신 뉴스는?" # → Web Search ] hybrid_collector.evaluate_with_hybrid(questions, monitor) 

### 성능 최적화 팁

**⚡ 대량 환각 탐지 최적화**

#### 1\. Context 캐싱

  * **동일 질문 재사용** : Context를 메모리에 캐싱
  * **유사 질문 그룹화** : 같은 Context로 평가
  * **Vector 검색 최적화** : 배치 검색으로 속도 향상

#### 2\. 병렬 처리

  * **Context 수집 병렬화** : ThreadPoolExecutor 사용
  * **Agent 실행 병렬화** : API 호출 동시 처리
  * **배치 크기 조정** : 100-200개씩 처리

#### 3\. 점진적 평가

  * **중간 저장** : 50개마다 결과 저장
  * **체크포인트** : 중단 시 이어서 평가
  * **진행 상황 로깅** : 실시간 모니터링

# Context 캐싱 예시 from functools import lru_cache class CachedRAGEvaluator: def __init__(self, vectorstore): self.vectorstore = vectorstore self.context_cache = {} @lru_cache(maxsize=500) def get_context_cached(self, question: str) -> str: """질문 해시 기반 Context 캐싱""" docs = self.vectorstore.similarity_search(question, k=3) context = "\n".join([d.page_content for d in docs]) return context def batch_evaluate_with_cache(self, questions: list[str], monitor): for i, question in enumerate(questions): # 캐시에서 Context 가져오기 (빠름) context = self.get_context_cached(question) agent_response = your_agent.run(question) monitor.record_task( task_id=f"cached_{i:03d}", task_type=TaskType.QA, success=True, latency=0.5, # 캐싱으로 빠름 completion_score=1.0, context=context, response=agent_response ) # 중간 저장 (50개마다) if (i + 1) % 50 == 0: from agent_evaluator.utils.dashboard_integration import save_to_dashboard save_to_dashboard( monitor, filename=f"checkpoint_{i+1}.json" ) print(f"✅ Checkpoint saved: {i+1} tasks") 

#### ⚠️ 자동화 주의사항

  * **Context 품질 검증** : 자동 수집된 Context는 샘플링 검토 필수
  * **RAG 검색 품질** : 관련 없는 문서 검색 시 오탐 증가
  * **비용 모니터링** : LLM 기반 Context 생성 비용 추적
  * **타임아웃 설정** : 웹 검색 등 외부 API 호출 타임아웃
  * **에러 핸들링** : Context 수집 실패 시 대체 전략

## 🔌 Framework Integration

### LangChain RAG 통합

from langchain.chains import RetrievalQA from agent_evaluator.integrations import LangChainEvaluator evaluator = LangChainEvaluator( enable_hallucination_detection=True ) # RAG 체인 실행 및 평가 result = evaluator.run_and_evaluate( agent=qa_chain, task_input="What is the capital of France?", task_id="rag_001", task_type="QA", ground_truth="Paris", context=retrieved_docs # 환각 탐지에 사용 ) # 환각 통계 hall_rate = evaluator.monitor.hallucination_detector.get_hallucination_rate() print(f"Hallucination Rate: {hall_rate['overall_rate']}%") 

## ✨ Best Practices

#### ✅ Hallucination Detection Best Practices

  1. **개발 단계**
     * Layer 1 규칙 기반 사용 (빠르고 무료)
     * 30% 임계값 조정 테스트
     * False Positive 패턴 수집
  2. **프로덕션 단계**
     * Layer 3 DeepEval 사용 (높은 정확도)
     * 중요 작업은 Layer 1 + Layer 3 병행
     * 환각률 > 10% 시 알림 설정
  3. **컨텍스트 품질**
     * 관련성 높은 컨텍스트 제공
     * 충분한 정보 포함 (너무 짧으면 오탐)
  4. **모니터링**
     * 환각 패턴 정기 분석
     * 사용자 피드백과 연계
     * 프롬프트 엔지니어링으로 개선

#### ⚠️ 주의사항

  * **패러프레이징 허용** : "자동차" = "차량"은 환각 아님
  * **요약 작업** : 요약은 단어 겹침이 낮아도 정상
  * **창의적 작업** : 소설/시 생성은 환각 탐지 부적절
  * **다국어** : 번역 작업은 단어 겹침 0% (환각 아님)

## 🔗 관련 지표

관련 지표 | 관계 | 문서 링크  
---|---|---  
**Accuracy** | 환각은 낮은 Accuracy의 원인 | [Accuracy 가이드](<02_ACCURACY.html>)  
**Quality Score** | 환각은 품질 저하 요인 | [Quality 가이드](<04_QUALITY_SCORE.html>)  
**DeepEval (Layer 3)** | 의미적 환각 탐지 (고정확도) | [Layer 3 가이드](<../AGENTIC_AI_METRICS_GUIDE.html>)  
  
## 📋 요약

**Hallucination Detection (환각 감지)** 는 AI Agent의 신뢰성을 보장하는 핵심 메트릭입니다. 

  * **Layer 1 규칙 기반** : Unsupported Claims (단어 겹침 <30%) + Numerical Inconsistency (숫자 비교)
  * **정확도** : 70-80% (빠르고 무료, 개발/테스트용)
  * **Layer 3 DeepEval** : 90-95% 정확도 (의미 기반, 프로덕션용)
  * **위험도** : 의료/법률/금융 등 중요 분야에서 치명적
  * **모니터링 필수** : 환각률 >10% 시 알림 설정 권장

  
Layer 1 네이티브 메트릭으로 빠르고 무료로 기본 환각을 탐지하며, 프로덕션 환경에서는 Layer 3 DeepEval과 병행하여 높은 정확도를 확보하는 것이 권장됩니다. 

## 📚 참고 자료

  * [Agent Evaluator 메인 문서](<../README.html>)
  * [종합 학습 가이드](<../LEARNING_GUIDE.html>)
  * [DeepEval Hallucination Metric](<https://docs.confident-ai.com/docs/metrics-hallucination>)

**최종 업데이트** : 2025-12-16 | **버전** : Agent Evaluator v0.5.1

**문서** : Hallucination Detection 상세 가이드

© 2025 Agent Evaluator. All rights reserved.
