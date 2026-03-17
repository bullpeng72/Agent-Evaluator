# ⭐ Quality Score

Multi-Dimensional AI Response Quality Evaluation

Agent Evaluator v0.5.1 - Layer 1 Foundation Metric

## 🎯 개요

**Quality Score (품질 점수)** 는 AI Agent 응답의 종합적인 품질을 다차원으로 평가하는 Layer 1 Foundation Metric입니다. 

  * **측정 대상** : AI Agent 응답의 종합 품질 (5개 차원)
  * **평가 차원** : Relevance (25%), Completeness (25%), Accuracy (20%), Clarity (15%), Usefulness (15%)
  * **점수 범위** : 0-5점 (등급: A, B, C, D, F)
  * **구현 위치** : `agent_evaluator/core/agent_evaluator.py` (Lines 628-921)

#### ⚠️ 품질 평가의 중요성

  * **다차원 평가** : 단순 정확도를 넘어 종합적 품질 측정
  * **조기 품질 문제 발견** : 배포 전 낮은 품질 응답 탐지
  * **개선 방향 제시** : 어떤 차원이 약한지 파악하여 개선
  * **사용자 만족도** : 높은 품질이 사용자 경험 향상

#### 🏗️ 구현 특징

  * **클래스** : `ResponseQualityEvaluator` (agent_evaluator.py:628-921)
  * **평가 방식** : 5가지 차원 × 가중치 합산
  * **외부 의존성** : 없음 (Layer 1 Native Metric)
  * **커스터마이징** : 도메인별 가중치 조정 가능
  * **등급 시스템** : A (4.5-5.0) ~ F (0-2.9) 5단계

**Quality Score 공식 (0-5점 척도)**  
  
Quality = 0.25 × Relevance + 0.25 × Completeness + 0.20 × Accuracy  
\+ 0.15 × Clarity + 0.15 × Usefulness 

## 📊 5가지 품질 차원

#### 📌 1. Relevance (관련성) - 가중치 25%

**측정 내용** : 응답이 사용자 질문과 얼마나 관련 있는가?

**계산 방식** : 질문 키워드와 응답 키워드의 겹침 비율

# 예시 질문: "파이썬에서 리스트 정렬 방법은?" 응답: "파이썬 리스트는 sort() 메서드로 정렬할 수 있습니다" # 키워드 겹침: {파이썬, 리스트, 정렬} → 3/3 = 100% # Relevance Score: 5.0 / 5.0

#### 📋 2. Completeness (완전성) - 가중치 25%

**측정 내용** : 기대하는 요소들이 모두 포함되었는가?

**계산 방식** : 기대 요소 중 실제로 응답에 포함된 비율

# 예시 기대 요소: ["정의", "예시", "사용법"] 응답에 포함: ["정의", "사용법"] # 예시 누락 # Completeness: 2/3 = 0.67 # Score: 0.67 × 5 = 3.35 / 5.0

#### 🎯 3. Accuracy (정확성) - 가중치 20%

**측정 내용** : Ground Truth와 얼마나 일치하는가?

**계산 방식** : Ground Truth가 있으면 유사도 계산, 없으면 완전성 기반 추정

# Ground Truth가 있는 경우 ground_truth = "서울의 인구는 약 970만명" response = "서울 인구는 대략 1000만명" # Token Similarity: ~0.8 # Accuracy Score: 0.8 × 5 = 4.0 / 5.0 # Ground Truth가 없는 경우 # Completeness 기반 휴리스틱 사용 # Score: completeness × 4.5

#### 💬 4. Clarity (명확성) - 가중치 15%

**측정 내용** : 응답이 이해하기 쉽고 잘 구조화되었는가?

**계산 방식** : 응답 길이 + 구조화 여부 (줄바꿈, 문장 부호)

# 계산 로직 word_count = len(response.split()) has_structure = '\n' in response or '.' in response clarity = min(word_count / 100, 1.0) × (1.2 if has_structure else 1.0) score = min(clarity × 5, 5.0) # 예시: # 50단어 + 구조화 → (0.5 × 1.2) × 5 = 3.0 # 150단어 + 구조화 → (1.0 × 1.2) × 5 = 5.0 (최대)

#### 💡 5. Usefulness (유용성) - 가중치 15%

**측정 내용** : 실제로 도움이 되는 응답인가?

**계산 방식** : 길이 + 구조 + 예시 + 구체적 데이터

# 4가지 요소 체크 has_examples = any(word in response for word in ['예를 들어', 'example', ':', '•']) has_numbers = any(char.isdigit() for char in response) has_structure = '\n' in response or '.' in response usefulness = ( 0.4 × min(word_count / 150, 1.0) + # 적절한 길이 0.3 × (1.0 if has_structure else 0.5) + # 구조화 0.2 × (1.0 if has_examples else 0.5) + # 예시 0.1 × (1.0 if has_numbers else 0.5) # 구체적 데이터 ) score = usefulness × 5 

### Grade 시스템

점수 범위 | 등급 | 설명 | 권장 조치  
---|---|---|---  
4.5 ~ 5.0 | **A** | 탁월한 품질 | 현재 수준 유지  
4.0 ~ 4.4 | **B** | 우수한 품질 | 세부 개선 기회 탐색  
3.5 ~ 3.9 | **C** | 보통 품질 | 주요 차원 개선 필요  
3.0 ~ 3.4 | **D** | 미흡한 품질 | 즉각적인 개선 필요  
0.0 ~ 2.9 | **F** | 불합격 | 재설계 고려  
  
## 🏗️ 구현 위치 및 클래스 구조

### 파일 위치

# 구현 파일 agent_evaluator/core/agent_evaluator.py # 클래스 정의 class ResponseQualityEvaluator: # Lines 628-921 """Evaluate response quality across multiple dimensions"""

### 클래스 구조

메서드 | 라인 | 설명  
---|---|---  
`__init__()` | 631-639 | 평가자 초기화, 가중치 설정  
`evaluate_response()` | 641-727 | **5차원 품질 평가**  
`_assign_grade()` | 729-740 | 점수 → 등급 변환 (A-F)  
`_calculate_similarity()` | 742-782 | Ground Truth 유사도  
`get_quality_metrics()` | 784-837 | 통계 집계  
`get_quality_by_dimension()` | 839-897 | 차원별 상세 분석  
`_get_score_distribution()` | 899-921 | 점수 분포 계산  
  
## ⚙️ 핵심 평가 알고리즘

**이 섹션에서는** `ResponseQualityEvaluator` 클래스의 핵심 메서드들이 **어떻게 동작하는지** 상세히 설명합니다.

### 1️⃣ evaluate_response() - 5차원 품질 평가 메서드

**목적** : AI Agent 응답을 5가지 차원에서 평가하고 가중 평균 점수 계산

**위치** : Lines 641-727

def evaluate_response(self, task_id: str, response: str, request: str, expected_elements: List[str], ground_truth: Optional[str] = None) -> Dict[str, Any]: """5차원 품질 평가 수행""" scores = {} # === 1. Relevance (관련성) 평가 === (Lines 659-668) request_words = set(request.lower().split()) response_words = set(response.lower().split()) if not request_words: relevance = 0.0 else: # 키워드 겹침 비율 계산 relevance = len(request_words & response_words) / len(request_words) scores["relevance"] = min(relevance * 5, 5.0) # === 2. Completeness (완전성) 평가 === (Lines 670-679) found_elements = sum(1 for elem in expected_elements if elem.lower() in response.lower()) if expected_elements and len(expected_elements) > 0: completeness = found_elements / len(expected_elements) else: completeness = 1.0 # 요구사항 없으면 100% 완료 scores["completeness"] = completeness * 5 # === 3. Clarity (명확성) 평가 === (Lines 681-685) word_count = len(response.split()) has_structure = '\n' in response or '.' in response clarity = min(word_count / 100, 1.0) * (1.2 if has_structure else 1.0) scores["clarity"] = min(clarity * 5, 5.0) # === 4. Accuracy (정확성) 평가 === (Lines 687-694) if ground_truth: similarity = self._calculate_similarity(response, ground_truth) scores["accuracy"] = similarity * 5 else: # Heuristic: 완전성 기반 추정 scores["accuracy"] = min(completeness * 4.5, 5.0) # === 5. Usefulness (유용성) 평가 === (Lines 696-708) has_examples = any(word in response.lower() for word in ['예를 들어', 'example', ':', '•', '-']) has_numbers = any(char.isdigit() for char in response) usefulness = ( 0.4 * min(word_count / 150, 1.0) + # 적절한 길이 0.3 * (1.0 if has_structure else 0.5) + # 잘 구조화됨 0.2 * (1.0 if has_examples else 0.5) + # 예시 포함 0.1 * (1.0 if has_numbers else 0.5) # 구체적 데이터 ) scores["usefulness"] = usefulness * 5 # === 6. 가중 평균 계산 === (Lines 710-714) total_score = sum( scores[dim] * weight for dim, weight in self.dimensions.items() ) # === 7. 등급 부여 === (Line 716) grade = self._assign_grade(total_score) return { "task_id": task_id, "dimension_scores": scores, "total_score": round(total_score, 2), "grade": grade, "timestamp": datetime.now() } 

#### 🔍 5가지 평가 차원 상세 알고리즘

#### 📌 1. Relevance (관련성) - 키워드 겹침 비율

**계산식** : `len(request_words ∩ response_words) / len(request_words)`

  * 질문 키워드와 응답 키워드의 교집합 비율
  * 점수 스케일링: `min(relevance × 5, 5.0)`
  * 빈 질문 처리: request_words가 비어있으면 0.0 반환

#### 📋 2. Completeness (완전성) - 기대 요소 포함 비율

**계산식** : `found_elements / len(expected_elements)`

  * expected_elements 리스트의 각 요소가 응답에 포함되는지 체크
  * 대소문자 무시: `elem.lower() in response.lower()`
  * 요구사항 없는 경우: 100% 완료로 간주 (completeness = 1.0)

#### 💬 3. Clarity (명확성) - 길이 + 구조화

**계산식** : `min(word_count/100, 1.0) × (1.2 if has_structure else 1.0)`

  * 100단어 기준으로 정규화 (100단어 이상 = 1.0)
  * 구조화 보너스: 줄바꿈 또는 마침표 포함 시 1.2배
  * 최대 5.0 제한: `min(clarity × 5, 5.0)`

#### 🎯 4. Accuracy (정확성) - Ground Truth 유사도 또는 휴리스틱

**Ground Truth 제공 시** : Jaccard Similarity 기반 유사도 계산

**Ground Truth 없는 경우** : `min(completeness × 4.5, 5.0)`

  * 완전성이 높으면 정확도도 높다고 가정
  * 최대 4.5점까지만 부여 (불확실성 고려)

#### 🔧 5. Usefulness (유용성) - 4가지 지표 가중 합산

**계산식** :

usefulness = 0.4 × min(word_count/150, 1.0) + # 40%: 적절한 길이 (150단어 기준) 0.3 × (1.0 if has_structure else 0.5) + # 30%: 구조화 0.2 × (1.0 if has_examples else 0.5) + # 20%: 예시 포함 0.1 × (1.0 if has_numbers else 0.5) # 10%: 구체적 숫자

  * **예시 탐지 키워드** : '예를 들어', 'example', ':', '•', '-'
  * **숫자 탐지** : `any(char.isdigit() for char in response)`

### 2️⃣ _calculate_similarity() - Ground Truth 유사도 계산

**목적** : 응답과 Ground Truth 간의 Jaccard Similarity 계산

**위치** : Lines 742-782

def _calculate_similarity(self, response: str, ground_truth: str) -> float: """Jaccard Similarity + Coverage 가중 조합""" import re # === 1. 텍스트 정규화 === (Lines 751-755) def normalize(text): text = text.lower() text = re.sub(r'\s+', ' ', text).strip() # 공백 정규화 text = re.sub(r'[^\w\s]', '', text) # 특수문자 제거 return text response_norm = normalize(response) gt_norm = normalize(ground_truth) if not gt_norm: return 0.0 # === 2. 토큰 분리 === (Lines 763-765) response_tokens = set(response_norm.split()) gt_tokens = set(gt_norm.split()) if not gt_tokens: return 0.0 intersection = len(response_tokens & gt_tokens) union = len(response_tokens | gt_tokens) # === 3. Jaccard Similarity === (Line 774) jaccard = intersection / union if union > 0 else 0.0 # === 4. Coverage (Ground Truth 커버리지) === (Line 777) coverage = intersection / len(gt_tokens) # === 5. 가중 조합 (Coverage 우선) === (Line 780) similarity = 0.6 * coverage + 0.4 * jaccard return min(similarity, 1.0) 

#### ✅ 유사도 계산 핵심 포인트

  1. **2가지 유사도 지표 사용** : 
     * **Jaccard Similarity** : `|A ∩ B| / |A ∪ B|` (대칭적)
     * **Coverage** : `|A ∩ B| / |B|` (Ground Truth 기준)
  2. **Coverage 우선 (60:40 비율)** : Ground Truth의 핵심 내용을 얼마나 포함했는지 중요
  3. **텍스트 정규화** : 소문자 변환, 공백/특수문자 제거로 순수 의미 비교
  4. **Zero Division 방지** : gt_tokens가 비어있으면 0.0 반환

### 3️⃣ _assign_grade() - 점수 → 등급 변환

**목적** : 0-5점 범위의 total_score를 A-F 등급으로 변환

**위치** : Lines 729-740

def _assign_grade(self, score: float) -> str: """5단계 등급 체계""" if score >= 4.5: # 90% 이상 return "A" elif score >= 4.0: # 80-89% return "B" elif score >= 3.5: # 70-79% return "C" elif score >= 3.0: # 60-69% return "D" else: # 60% 미만 return "F"

등급 | 점수 범위 | 백분율 | 의미  
---|---|---|---  
**A** | 4.5 - 5.0 | 90-100% | 탁월한 품질  
**B** | 4.0 - 4.49 | 80-89% | 우수한 품질  
**C** | 3.5 - 3.99 | 70-79% | 양호한 품질  
**D** | 3.0 - 3.49 | 60-69% | 개선 필요  
**F** | 0 - 2.99 | 0-59% | 품질 불량  
  
### 4️⃣ get_quality_metrics() - 통계 집계

**목적** : 모든 평가 결과를 집계하여 통계 생성

**위치** : Lines 784-837

def get_quality_metrics(self) -> Dict[str, Any]: """전체 품질 통계 계산""" if not self.evaluations: return {} # === 1. DataFrame 변환 === (Line 789) df = pd.DataFrame(self.evaluations) # === 2. 등급 분포 === (Line 791) grade_dist = df["grade"].value_counts().to_dict() # === 3. 표준편차 계산 (NaN 처리) === (Line 794) std_val = df["total_score"].std() # === 4. High Quality 카운트 (A or B) === (Line 797) high_quality_count = len(df[df["grade"].isin(["A", "B"])]) # === 5. 차원별 평균 점수 === (Lines 800-806) dimension_averages = { dim: round( df["dimension_scores"].apply(lambda x: x[dim]).mean(), 2 ) for dim in self.dimensions.keys() } return { "average_score": round(df["total_score"].mean(), 2), "std_dev": round(std_val, 2) if pd.notna(std_val) else 0.0, "grade_distribution": grade_dist, "high_quality_percentage": round( (high_quality_count / len(df)) * 100, 2 ), "dimension_averages": dimension_averages, "total_evaluations": len(df) } 

#### 📊 반환되는 통계 지표

  * **average_score** : 전체 평가의 평균 품질 점수 (0-5)
  * **std_dev** : 점수의 표준편차 (일관성 측정, NaN 처리 포함)
  * **grade_distribution** : 등급별 개수 딕셔너리 `{'A': 15, 'B': 20, ...}`
  * **high_quality_percentage** : A 또는 B 등급 비율
  * **dimension_averages** : 5가지 차원별 평균 점수
  * **total_evaluations** : 총 평가 건수

#### ⚠️ 구현 한계 및 개선 방안

  * **휴리스틱 기반 평가** : 
    * 현재는 규칙 기반(단어 수, 키워드 매칭)으로 평가
    * **개선** : LLM-as-a-Judge 또는 임베딩 기반 의미 유사도 도입
  * **도메인 특화 부족** : 
    * 모든 작업 유형에 동일한 평가 기준 적용
    * **개선** : 작업 유형별 가중치 조정 (코드 생성 vs QA)
  * **Ground Truth 의존성** : 
    * Accuracy 평가는 Ground Truth가 있어야 정확
    * 없으면 Completeness 기반 추정 (불완전)
    * **개선** : Reference-free 평가 메트릭 (BERTScore, BLEURT) 통합
  * **주관적 차원 평가** : 
    * Clarity, Usefulness는 주관적 요소가 많음
    * **개선** : 사용자 피드백 학습 또는 Readability 지표 도입

#### 📊 Response Quality 5차원 평가 흐름

graph TD A[response, request, expected_elements] --> B[1. Relevance 계산  
키워드 겹침 비율] A --> C[2. Completeness 계산  
기대 요소 포함 여부] A --> D[3. Clarity 계산  
길이 + 구조화] A --> E[4. Accuracy 계산  
Ground Truth 유사도] A --> F[5. Usefulness 계산  
예시/숫자/구조 포함] B --> G[가중 평균  
25% + 25% + 15% + 20% + 15%] C --> G D --> G E --> G F --> G G --> H[total_score 0-5점] H --> I{점수 등급 판정} I -->|≥4.5| J1[Grade: A] I -->|≥4.0| J2[Grade: B] I -->|≥3.5| J3[Grade: C] I -->|≥3.0| J4[Grade: D] I -->|<3.0| J5[Grade: F] style A fill:#667eea,color:#fff style B fill:#ed8936,color:#fff style C fill:#ed8936,color:#fff style D fill:#ed8936,color:#fff style E fill:#ed8936,color:#fff style F fill:#ed8936,color:#fff style G fill:#3182ce,color:#fff style H fill:#48bb78,color:#fff style I fill:#667eea,color:#fff 

## 💻 사용 예제

### 기본 사용 예제

from agent_evaluator import PerformanceMonitor # 모니터 초기화 monitor = PerformanceMonitor() # AI Agent 작업 request = "파이썬에서 리스트를 정렬하는 방법을 알려주세요" response = """ 파이썬 리스트를 정렬하는 방법은 두 가지가 있습니다. 1\. sort() 메서드: 원본 리스트를 직접 정렬합니다. 예: numbers = [3, 1, 2]; numbers.sort() 2\. sorted() 함수: 새로운 정렬된 리스트를 반환합니다. 예: sorted_list = sorted([3, 1, 2]) """ expected_elements = ["sort", "sorted", "예시"] ground_truth = "sort() 메서드와 sorted() 함수를 사용" # 작업 기록 (품질 자동 평가) monitor.record_task( task_id="qa_001", task_type="QA", success=True, latency=1.5, completion_score=1.0, expected_output=expected_elements, actual_output=response, ground_truth=ground_truth, request=request ) # 품질 메트릭 확인 quality_metrics = monitor.quality_evaluator.get_quality_metrics() print(f"Average Quality Score: {quality_metrics['avg_total_score']}") print(f"Grade Distribution: {quality_metrics['grade_distribution']}") print(f"High Quality Count (A/B): {quality_metrics['high_quality_count']}") # 차원별 점수 dimensions = quality_metrics['dimension_averages'] print(f"\n=== Dimension Scores ===") print(f"Relevance: {dimensions['relevance']}") print(f"Completeness: {dimensions['completeness']}") print(f"Accuracy: {dimensions['accuracy']}") print(f"Clarity: {dimensions['clarity']}") print(f"Usefulness: {dimensions['usefulness']}") 

### 다중 응답 품질 비교

from agent_evaluator import PerformanceMonitor monitor = PerformanceMonitor() # 3가지 응답 비교 responses = [ { "id": "response_a", "text": "리스트를 정렬하려면 sort()를 쓰세요.", # 짧고 불완전 }, { "id": "response_b", "text": "파이썬에서는 sort() 메서드와 sorted() 함수 두 가지 방법으로 리스트를 정렬할 수 있습니다. sort()는 원본을 변경하고, sorted()는 새 리스트를 반환합니다.", # 명확하고 완전 }, { "id": "response_c", "text": "정렬하려면 sort()를 사용하세요. 예: [3,1,2].sort() 결과는 [1,2,3]입니다. sorted()도 있습니다.", # 예시 포함 } ] request = "파이썬 리스트 정렬 방법" expected_elements = ["sort", "sorted", "차이점"] for resp in responses: monitor.record_task( task_id=resp["id"], task_type="QA", success=True, latency=1.0, completion_score=1.0, expected_output=expected_elements, actual_output=resp["text"], request=request ) # 각 응답의 품질 분석 for eval_data in monitor.quality_evaluator.evaluations: print(f"\n{eval_data['task_id']}:") print(f" Total Score: {eval_data['total_score']} ({eval_data['grade']})") print(f" Dimensions: {eval_data['dimension_scores']}") # 예상 결과: # response_a: ~3.0 (D) - 짧고 불완전 # response_b: ~4.5 (A) - 명확하고 완전 # response_c: ~4.0 (B) - 예시 포함으로 유용성 높음

### 차원별 상세 분석

from agent_evaluator import PerformanceMonitor monitor = PerformanceMonitor() # 여러 작업 수행 (생략) # ... # 차원별 상세 통계 by_dimension = monitor.quality_evaluator.get_quality_by_dimension() print("=== Quality by Dimension ===") for dim, stats in by_dimension['by_dimension_detailed'].items(): print(f"\n{dim.upper()}:") print(f" Average: {stats['average']}") print(f" Median: {stats['median']}") print(f" Range: {stats['min']} ~ {stats['max']}") print(f" Std Dev: {stats['std']}") print(f" Distribution: {stats['distribution']}") # 출력 예시: # RELEVANCE: # Average: 4.2 # Median: 4.5 # Range: 3.0 ~ 5.0 # Std Dev: 0.8 # Distribution: {'0-1': 0, '1-2': 0, '2-3': 1, '3-4': 2, '4-5': 7}

## 🤖 평가 데이터 자동 처리 방안

**실제 프로젝트에서는 수백~수천 개의 응답 품질을 평가해야 합니다.**  
Quality Score는 5가지 차원 (Relevance, Completeness, Accuracy, Clarity, Usefulness)을 측정하므로, Expected Elements와 Ground Truth 자동 생성이 핵심입니다. 

### 자동화 수준별 전략

레벨 | 자동화 범위 | 데이터 수집 방법 | 적용 시나리오  
---|---|---|---  
**Level 1** | 기본 품질 평가 | Request만으로 자동 평가 | 빠른 프로토타입  
**Level 2** | Golden Dataset 기반 | 사전 준비된 Expected Elements | 벤치마크, 반복 평가  
**Level 3** | LLM 기반 자동 생성 | Expected Elements 자동 추출 | Expected 없는 경우  
**Level 4** | 템플릿 기반 | 작업 유형별 템플릿 | 정형화된 작업  
**Level 5** | 하이브리드 | 복합 전략 | 프로덕션 환경  
  
### Level 1: 기본 자동 평가 (Expected Elements 없이)

#### 💡 핵심 아이디어

Request만 제공하면 자동으로 품질 평가 (Expected Elements, Ground Truth 없음)

**장점** : 가장 빠르고 간단, 별도 준비 불필요

**단점** : Completeness, Accuracy 차원은 제한적 평가

from agent_evaluator import PerformanceMonitor, TaskType from concurrent.futures import ThreadPoolExecutor class BasicQualityEvaluator: """Expected Elements 없이 기본 품질 평가""" def __init__(self, monitor: PerformanceMonitor): self.monitor = monitor def evaluate_response(self, task_id: str, request: str, response: str): """기본 품질 평가 (Expected 없음)""" # Request만으로 평가 # - Relevance: Request 키워드 겹침으로 측정 # - Completeness: 0.7 (기본값) # - Accuracy: Completeness 기반 휴리스틱 # - Clarity: 응답 길이 + 구조로 측정 # - Usefulness: 예시, 숫자, 구조로 측정 self.monitor.record_task( task_id=task_id, task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, request=request, ← Relevance 평가에 사용 actual_output=response # expected_output 없음 → Completeness 0.7 기본값 # ground_truth 없음 → Accuracy는 휴리스틱 ) def batch_evaluate(self, qa_pairs: list[dict], parallel: bool = True): """배치 평가""" print(f"🚀 {len(qa_pairs)}개 응답 품질 평가 시작...\n") if parallel: with ThreadPoolExecutor(max_workers=10) as executor: futures = [ executor.submit( self.evaluate_response, qa["qa_id"], qa["question"], qa["response"] ) for qa in qa_pairs ] for future in futures: future.result() else: for qa in qa_pairs: self.evaluate_response( qa["qa_id"], qa["question"], qa["response"] ) # 결과 통계 quality_stats = self.monitor.quality_evaluator.get_quality_metrics() print(f"\n✅ 평가 완료!") print(f"Average Quality Score: {quality_stats['avg_total_score']:.2f}") print(f"Grade Distribution: {quality_stats['grade_distribution']}") # ============================================================ # 사용 예시 # ============================================================ monitor = PerformanceMonitor() evaluator = BasicQualityEvaluator(monitor) # Agent 응답 수집 (실제 환경) qa_pairs = [ { "qa_id": "qa_001", "question": "파이썬 리스트 정렬 방법은?", "response": your_agent.run("파이썬 리스트 정렬 방법은?") }, # ... 수백 개 ] # 배치 평가 (병렬) evaluator.batch_evaluate(qa_pairs, parallel=True) # Dashboard 저장 from agent_evaluator.utils.dashboard_integration import save_to_dashboard save_to_dashboard(monitor, filename="quality_basic_eval.json") 

### Level 2: Golden Dataset 기반 완전 평가

#### 💡 핵심 아이디어

Expected Elements와 Ground Truth가 포함된 Golden Dataset으로 정확한 품질 평가

**장점** : 5가지 차원 모두 정확 평가

**단점** : Golden Dataset 작성 필요

import json from pathlib import Path from agent_evaluator import PerformanceMonitor, TaskType # ============================================================ # Golden Dataset 구조 (Quality 평가용) # ============================================================ golden_dataset_structure = { "dataset_id": "quality_eval_v1", "metadata": { "dataset_name": "Quality Score Golden Dataset", "version": "0.5.0" }, "qa_pairs": [ { "qa_id": "qa_001", "question": "파이썬 리스트 정렬 방법은?", "expected_elements": [ "sort", # Completeness 평가용 "sorted", "차이점", "예시" ], "ground_truth": "sort() 메서드와 sorted() 함수를 사용. sort()는 원본 변경, sorted()는 새 리스트 반환", # Accuracy 평가용 "task_type": "qa" } ] } # ============================================================ # Golden Dataset 로드 및 평가 # ============================================================ dataset_path = Path("Evaluator_Examples/Dashboard/data/golden_datasets/quality_eval_dataset.json") with open(dataset_path, 'r', encoding='utf-8') as f: golden_data = json.load(f) monitor = PerformanceMonitor() print(f"📦 Golden Dataset: {golden_data['metadata']['dataset_name']}") print(f" 총 {len(golden_data['qa_pairs'])}개 테스트 케이스\n") for qa_pair in golden_data["qa_pairs"]: print(f"평가: {qa_pair['qa_id']}") # Agent 실행 agent_response = your_agent.run(qa_pair["question"]) # 품질 평가 (5차원 모두 정확) monitor.record_task( task_id=qa_pair["qa_id"], task_type=getattr(TaskType, qa_pair["task_type"].upper(), TaskType.QA), success=True, latency=1.0, completion_score=1.0, request=qa_pair["question"], ← Relevance expected_output=qa_pair["expected_elements"], ← Completeness ground_truth=qa_pair["ground_truth"], ← Accuracy actual_output=agent_response ← Clarity, Usefulness ) # 결과 확인 quality_stats = monitor.quality_evaluator.get_quality_metrics() print(f"\n✅ Average Quality: {quality_stats['avg_total_score']:.2f}") print(f"Grade Distribution: {quality_stats['grade_distribution']}") # 차원별 점수 dimensions = quality_stats['dimension_averages'] print(f"\n=== Dimension Scores ===") print(f"Relevance: {dimensions['relevance']:.2f}") print(f"Completeness: {dimensions['completeness']:.2f}") print(f"Accuracy: {dimensions['accuracy']:.2f}") print(f"Clarity: {dimensions['clarity']:.2f}") print(f"Usefulness: {dimensions['usefulness']:.2f}") 

### Level 3: LLM 기반 Expected Elements 자동 생성

#### 💡 핵심 아이디어

질문에 대해 LLM이 Expected Elements를 자동 생성

**장점** : Golden Dataset 없이도 Completeness 정확 평가

**단점** : LLM 비용, 품질 의존

from agent_evaluator import PerformanceMonitor, TaskType from openai import OpenAI class LLMExpectedElementsGenerator: """LLM을 사용한 Expected Elements 자동 생성""" def __init__(self, api_key: str, monitor: PerformanceMonitor): self.client = OpenAI(api_key=api_key) self.monitor = monitor def generate_expected_elements(self, question: str) -> list[str]: """질문에 대한 Expected Elements 생성""" prompt = f""" 다음 질문에 대한 좋은 답변에 반드시 포함되어야 할 핵심 요소들을 나열하세요. 각 요소는 간단한 키워드나 짧은 구문으로 표현하세요. 질문: {question} 예시: 질문: "파이썬 리스트 정렬 방법은?" 필수 요소: 1\. sort() 메서드 2\. sorted() 함수 3\. 두 방법의 차이점 4\. 사용 예시 질문: {question} 필수 요소:""" completion = self.client.chat.completions.create( model="gpt-4o-mini", messages=[ {"role": "system", "content": "당신은 교육 전문가입니다."}, {"role": "user", "content": prompt} ], temperature=0.0 ) # 응답 파싱 (1. ... 2. ... 형식) response_text = completion.choices[0].message.content.strip() elements = [] for line in response_text.split('\n'): if line.strip() and ('.' in line or '-' in line): # "1. sort() 메서드" → "sort" element = line.split('.', 1)[-1].strip() \ .split('-', 1)[-1].strip() elements.append(element) return elements[:5] # 최대 5개 def evaluate_with_generated_elements( self, qa_pairs: list[dict] ): """Expected Elements 자동 생성 + 품질 평가""" for i, qa in enumerate(qa_pairs): print(f"\n[{i+1}/{len(qa_pairs)}] {qa['question']}") # 1. Expected Elements 자동 생성 print(" 🔍 Expected Elements 생성 중...") expected_elements = self.generate_expected_elements(qa["question"]) print(f" ✅ Generated: {expected_elements}") # 2. Agent 실행 agent_response = your_agent.run(qa["question"]) # 3. 품질 평가 self.monitor.record_task( task_id=qa["qa_id"], task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, request=qa["question"], expected_output=expected_elements, ← LLM 생성 actual_output=agent_response, ground_truth=qa.get("ground_truth") ← 선택 ) # 결과 통계 quality_stats = self.monitor.quality_evaluator.get_quality_metrics() print(f"\n📊 Average Quality: {quality_stats['avg_total_score']:.2f}") # ============================================================ # 사용 예시 # ============================================================ monitor = PerformanceMonitor() generator = LLMExpectedElementsGenerator( api_key="your-api-key", monitor=monitor ) qa_pairs = [ { "qa_id": "qa_001", "question": "파이썬 리스트 정렬 방법은?" }, { "qa_id": "qa_002", "question": "머신러닝이란 무엇인가요?" }, # ... 수백 개 ] # Expected Elements 자동 생성 + 평가 generator.evaluate_with_generated_elements(qa_pairs) 

### Level 4: 템플릿 기반 자동 평가

#### 💡 핵심 아이디어

작업 유형별로 사전 정의된 템플릿으로 Expected Elements 자동 생성

**장점** : 빠르고 일관성 있음

**단점** : 정형화된 작업에만 적용

from agent_evaluator import PerformanceMonitor, TaskType class TemplateBasedQualityEvaluator: """작업 유형별 템플릿 기반 품질 평가""" def __init__(self, monitor: PerformanceMonitor): self.monitor = monitor self.templates = self._init_templates() def _init_templates(self) -> dict: """작업 유형별 Expected Elements 템플릿""" return { "how_to": [ "정의", "방법", "단계", "예시", "주의사항" ], "what_is": [ "정의", "특징", "용도", "예시" ], "comparison": [ "A 설명", "B 설명", "차이점", "유사점", "사용 상황" ], "troubleshooting": [ "문제 진단", "원인 분석", "해결 방법", "예방책" ], "code_explanation": [ "코드 구조", "주요 함수", "동작 원리", "예시" ] } def classify_question_type(self, question: str) -> str: """질문 유형 자동 분류""" question_lower = question.lower() if any(kw in question_lower for kw in ["어떻게", "방법", "how to"]): return "how_to" elif any(kw in question_lower for kw in ["무엇", "뭐", "what is"]): return "what_is" elif any(kw in question_lower for kw in ["차이", "vs", "비교", "difference"]): return "comparison" elif any(kw in question_lower for kw in ["오류", "에러", "해결", "error"]): return "troubleshooting" elif any(kw in question_lower for kw in ["코드", "함수", "code"]): return "code_explanation" else: return "what_is" # 기본값 def evaluate_with_template( self, task_id: str, question: str, response: str ): """템플릿 기반 자동 평가""" # 1. 질문 유형 자동 분류 question_type = self.classify_question_type(question) print(f" 📋 Question Type: {question_type}") # 2. 템플릿에서 Expected Elements 가져오기 expected_elements = self.templates[question_type] print(f" ✅ Expected: {expected_elements}") # 3. 품질 평가 self.monitor.record_task( task_id=task_id, task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, request=question, expected_output=expected_elements, ← 템플릿에서 actual_output=response ) def batch_evaluate(self, qa_pairs: list[dict]): """배치 평가""" print(f"🚀 {len(qa_pairs)}개 응답 템플릿 기반 평가\n") for i, qa in enumerate(qa_pairs): print(f"\n[{i+1}/{len(qa_pairs)}] {qa['question']}") self.evaluate_with_template( qa["qa_id"], qa["question"], qa["response"] ) quality_stats = self.monitor.quality_evaluator.get_quality_metrics() print(f"\n📊 Average Quality: {quality_stats['avg_total_score']:.2f}") # ============================================================ # 사용 예시 # ============================================================ monitor = PerformanceMonitor() evaluator = TemplateBasedQualityEvaluator(monitor) qa_pairs = [ { "qa_id": "qa_001", "question": "파이썬 리스트를 정렬하는 방법은?", # → how_to "response": your_agent.run("...") }, { "qa_id": "qa_002", "question": "머신러닝이란 무엇인가요?", # → what_is "response": your_agent.run("...") }, { "qa_id": "qa_003", "question": "sort()와 sorted()의 차이는?", # → comparison "response": your_agent.run("...") } ] evaluator.batch_evaluate(qa_pairs) 

### Level 5: 하이브리드 품질 평가 전략

#### 💡 핵심 아이디어

Golden Dataset, 템플릿, LLM 생성을 상황에 따라 조합

from agent_evaluator import PerformanceMonitor, TaskType class HybridQualityEvaluator: """하이브리드 품질 평가 전략""" def __init__( self, monitor: PerformanceMonitor, golden_dataset: dict = None, template_evaluator: TemplateBasedQualityEvaluator = None, llm_generator: LLMExpectedElementsGenerator = None ): self.monitor = monitor self.golden_dataset = golden_dataset self.template_evaluator = template_evaluator self.llm_generator = llm_generator # Golden Dataset을 딕셔너리로 변환 (빠른 조회) self.golden_lookup = {} if golden_dataset: for qa in golden_dataset.get("qa_pairs", []): self.golden_lookup[qa["qa_id"]] = qa def evaluate(self, task_id: str, question: str, response: str): """최적 전략 선택하여 평가""" # 전략 1: Golden Dataset에 있으면 우선 사용 if task_id in self.golden_lookup: golden_qa = self.golden_lookup[task_id] print(f" 📦 Using Golden Dataset") self.monitor.record_task( task_id=task_id, task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, request=question, expected_output=golden_qa["expected_elements"], ground_truth=golden_qa.get("ground_truth"), actual_output=response ) return "golden" # 전략 2: 템플릿 적용 가능하면 사용 if self.template_evaluator: question_type = self.template_evaluator.classify_question_type(question) if question_type in self.template_evaluator.templates: print(f" 📋 Using Template ({question_type})") self.template_evaluator.evaluate_with_template( task_id, question, response ) return "template" # 전략 3: LLM으로 Expected Elements 생성 if self.llm_generator: print(f" 🤖 Using LLM Generation") expected_elements = self.llm_generator.generate_expected_elements(question) self.monitor.record_task( task_id=task_id, task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, request=question, expected_output=expected_elements, actual_output=response ) return "llm" # 전략 4: 기본 평가 (Request만) print(f" ⚡ Using Basic Evaluation") self.monitor.record_task( task_id=task_id, task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, request=question, actual_output=response ) return "basic" def batch_evaluate(self, qa_pairs: list[dict]): """배치 평가 (자동 전략 선택)""" print(f"🚀 {len(qa_pairs)}개 하이브리드 평가\n") strategy_counts = {"golden": 0, "template": 0, "llm": 0, "basic": 0} for i, qa in enumerate(qa_pairs): print(f"\n[{i+1}/{len(qa_pairs)}] {qa['question'][:50]}...") strategy = self.evaluate( qa["qa_id"], qa["question"], qa["response"] ) strategy_counts[strategy] += 1 # 전략 사용 통계 print(f"\n=== Strategy Usage ===") for strategy, count in strategy_counts.items(): print(f"{strategy}: {count}") # 품질 통계 quality_stats = self.monitor.quality_evaluator.get_quality_metrics() print(f"\n📊 Average Quality: {quality_stats['avg_total_score']:.2f}") # ============================================================ # 사용 예시 # ============================================================ monitor = PerformanceMonitor() # Golden Dataset 로드 (선택) with open("golden_dataset.json") as f: golden_data = json.load(f) # 하이브리드 평가기 초기화 hybrid = HybridQualityEvaluator( monitor=monitor, golden_dataset=golden_data, # 전략 1 template_evaluator=TemplateBasedQualityEvaluator(monitor), # 전략 2 llm_generator=LLMExpectedElementsGenerator("api-key", monitor) # 전략 3 ) qa_pairs = [ {"qa_id": "qa_001", "question": "...", "response": "..."}, # → Golden {"qa_id": "qa_999", "question": "어떻게 ...", "response": "..."}, # → Template {"qa_id": "qa_1000", "question": "...", "response": "..."}, # → LLM ] hybrid.batch_evaluate(qa_pairs) 

### 성능 최적화 팁

**⚡ 대량 품질 평가 최적화**

#### 1\. Expected Elements 캐싱

  * **템플릿 재사용** : 동일 질문 유형은 템플릿 캐싱
  * **LLM 생성 캐싱** : 유사 질문은 캐시에서 재사용
  * **Golden Dataset 인덱싱** : 딕셔너리 변환으로 빠른 조회

#### 2\. 병렬 처리

  * **Agent 실행 병렬화** : ThreadPoolExecutor 사용
  * **LLM 호출 배치** : 10-20개씩 동시 처리
  * **평가 병렬화** : 독립적인 평가는 병렬 실행

#### 3\. 선택적 평가

  * **샘플링** : 전체 데이터의 10-20% 샘플로 평가
  * **차등 평가** : 중요 응답은 정밀 평가, 나머지는 기본 평가
  * **임계값 기반** : 낮은 품질만 상세 분석

#### ⚠️ 자동화 주의사항

  * **Expected Elements 품질** : LLM 생성 시 샘플링 검증 필수
  * **템플릿 적합성** : 도메인 특성에 맞게 템플릿 커스터마이징
  * **비용 관리** : LLM 호출 비용 모니터링 (GPT-4o-mini 권장)
  * **차원별 검증** : 자동 평가 결과를 차원별로 검증
  * **Grade 분포 확인** : A/B 등급이 너무 많으면 기준 재조정

## 🔌 Framework Integration

### LangChain 통합

from langchain.chains import LLMChain from agent_evaluator.integrations import LangChainEvaluator evaluator = LangChainEvaluator() result = evaluator.run_and_evaluate( agent=chain, task_input="Explain machine learning", task_id="qa_001", task_type="QA", expected_output=["definition", "examples", "use cases"], ground_truth="Machine learning is..." ) # 품질 점수 자동 계산 quality = evaluator.monitor.quality_evaluator.get_quality_metrics() print(f"Quality Score: {quality['avg_total_score']}") 

## ✨ Best Practices

#### ✅ Quality Score 측정 Best Practices

  1. **Expected Elements 정의**
     * 명확한 기대 요소 목록 작성
     * 작업 유형별 템플릿 활용
  2. **가중치 조정**
     * 도메인 특성에 맞게 차원 가중치 조정
     * 예: 기술 문서 → Accuracy 40%, Clarity 30%
  3. **Ground Truth 제공**
     * 가능하면 항상 Ground Truth 제공
     * Accuracy 차원의 정확도 향상
  4. **Grade 기준 활용**
     * A/B 등급: 프로덕션 배포 가능
     * C 등급: 개선 후 재평가
     * D/F 등급: 즉시 수정 필요
  5. **차원별 분석**
     * 전체 점수가 낮을 때 어느 차원이 문제인지 파악
     * 약한 차원 집중 개선

#### ⚠️ 주의사항

  * **주관성** : Quality는 일부 주관적 요소 포함 (Usefulness)
  * **도메인 의존성** : 시/소설 등 창의적 작업에는 부적합
  * **길이 편향** : 너무 긴 응답이 높은 점수를 받을 수 있음
  * **가중치 재조정** : 프로젝트 특성에 맞게 가중치 변경 필요

## 🎨 가중치 커스터마이징

from agent_evaluator import ResponseQualityEvaluator # 기본 가중치 evaluator = ResponseQualityEvaluator() print(evaluator.dimensions) # {'relevance': 0.25, 'completeness': 0.25, 'accuracy': 0.20, # 'clarity': 0.15, 'usefulness': 0.15} # 커스텀 가중치 (예: 기술 문서) evaluator.dimensions = { "relevance": 0.15, # 관련성 덜 중요 "completeness": 0.20, # 완전성 중요 "accuracy": 0.40, # 정확성 매우 중요 "clarity": 0.20, # 명확성 중요 "usefulness": 0.05 # 유용성 덜 중요 } # 커스텀 가중치 (예: 마케팅 콘텐츠) evaluator.dimensions = { "relevance": 0.30, # 타겟 키워드 중요 "completeness": 0.15, "accuracy": 0.10, # 정확성 덜 중요 "clarity": 0.20, "usefulness": 0.25 # 유용성 매우 중요 } 

## 🔗 관련 지표

관련 지표 | 관계 | 문서 링크  
---|---|---  
**Accuracy** | Quality의 한 차원 | [Accuracy 가이드](<02_ACCURACY.html>)  
**Hallucination** | 낮은 Quality의 원인 | [Hallucination 가이드](<03_HALLUCINATION_DETECTION.html>)  
**TCR** | 완료율 + 품질 = 전체 성능 | [TCR 가이드](<01_TASK_COMPLETION_RATE.html>)  
  
## 📋 요약

**Quality Score (품질 점수)** 는 AI Agent 응답의 종합 품질을 다차원으로 평가하는 핵심 메트릭입니다. 

  * **5가지 차원** : Relevance (25%), Completeness (25%), Accuracy (20%), Clarity (15%), Usefulness (15%)
  * **0-5점 척도** : 가중 평균으로 종합 품질 점수 계산
  * **등급 시스템** : A (4.5-5.0) ~ F (0-2.9) 5단계 분류
  * **가중치 조정** : 도메인 특성에 맞게 차원별 가중치 커스터마이징 가능
  * **차원별 분석** : 약한 차원 파악으로 개선 방향 제시

  
Layer 1 네이티브 메트릭으로 외부 의존성 없이 다차원 품질 평가가 가능하며, 프로덕션 AI 시스템의 품질 보증과 사용자 만족도 향상에 필수적입니다. 

\1 

  * [Agent Evaluator 메인 문서](<../README.html>)
  * [종합 학습 가이드](<../LEARNING_GUIDE.html>)
  * [전체 지표 인덱스](<ALL_METRICS_INDEX.html>)

**최종 업데이트** : 2025-12-16 | **버전** : Agent Evaluator v0.5.1

**문서** : Quality Score 상세 가이드

© 2025 Agent Evaluator. All rights reserved.
