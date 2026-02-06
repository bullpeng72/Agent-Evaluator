# 🎯 Accuracy

Response Accuracy Measurement and Evaluation

Agent Evaluator v0.5.0 - Layer 1 Foundation Metric

## 📊 개요

**Accuracy (정확도)** 는 AI 에이전트의 응답이 정답(Ground Truth)과 얼마나 일치하는지를 측정하는 Layer 1 기본 메트릭입니다.   
  
작업 유형에 따라 QA Accuracy, Code Accuracy, General Accuracy 세 가지 계산 방법을 제공합니다. 

### ⚠️ 중요성

  * **품질 보증** : 응답의 정확성을 객관적으로 측정
  * **신뢰도 향상** : 정확한 응답으로 사용자 신뢰 확보
  * **모델 선택** : 정확도 기반 최적 모델 선택
  * **개선 방향** : 정확도가 낮은 작업 유형 식별
  * **벤치마킹** : 경쟁 시스템과 정량적 비교

## 📍 구현 위치

**파일:** `agent_evaluator/core/agent_evaluator.py`  
**클래스:** `AccuracyEvaluator`  
**라인:** 148-406 (총 259줄) 

### Accuracy란?

Accuracy(정확도)는 AI Agent의 응답이 실제 정답(Ground Truth)과 얼마나 일치하는지를 측정하는 지표입니다. 단순히 작업을 완료했는지를 측정하는 TCR과 달리, **완료된 작업의 품질과 정확성** 을 평가합니다. 

#### 💡 핵심 개념

**Accuracy = 예측값과 실제값의 유사도 (0.0 ~ 1.0 또는 0% ~ 100%)**

  * **작업 유형별 맞춤 평가** : QA, 코드 생성, 일반 작업마다 다른 알고리즘 적용
  * **다차원 유사도 측정** : 토큰, 문자, 구조 등 여러 차원에서 평가
  * **부분 정답 인정** : 0 또는 1이 아닌 연속적인 점수 (0.0 ~ 1.0)

### 1.2 왜 Accuracy가 중요한가?

  1. **품질 검증** : TCR이 높아도 Accuracy가 낮으면 쓸모없는 응답
  2. **신뢰성 평가** : 사용자가 Agent를 신뢰할 수 있는지 판단
  3. **개선 방향 제시** : 어떤 유형의 작업에서 약한지 파악
  4. **A/B 테스트** : 모델/프롬프트 변경 시 정확도 비교
  5. **비용 최적화** : 정확도와 비용의 균형점 찾기

### 1.3 작업 유형별 Accuracy 계산 방식

작업 유형 | 계산 방식 | 주요 알고리즘 | 적용 예시  
---|---|---|---  
**QA (질의응답)** | 다중 유사도 조합 |  • Jaccard 유사도 (30%)  
• Token Overlap (40%)  
• LCS Ratio (20%)  
• Char Similarity (10%)  | 자연어 답변, 요약, 설명  
**CODE_GENERATION** | 계층적 비교 |  1\. Exact Match  
2\. AST 비교  
3\. Normalized 비교  | 코드 생성, 리팩토링  
**일반 작업** | 문자열 일치 | Exact Match (0 or 1) | 분류, 단순 선택  
  
## 🏗️ 2. 구현 위치 및 클래스 구조

### 2.1 파일 위치

# 구현 파일 agent_evaluator/core/agent_evaluator.py # 클래스 정의 class AccuracyEvaluator: # Lines 148-406 """Evaluate accuracy across different dimensions"""

### 2.2 클래스 구조

메서드 | 라인 | 설명  
---|---|---  
`__init__()` | 151-152 | 평가 목록 초기화  
`add_evaluation()` | 154-164 | 평가 추가 (자동 계산)  
`_calculate_accuracy()` | 166-174 | 작업 유형 라우팅  
`_qa_accuracy()` | 176-256 | **QA 정확도 (다중 메트릭)**  
`_code_accuracy()` | 258-287 | **코드 정확도 (계층적)**  
`_ast_comparison()` | 289-336 | AST 구조 비교  
`_normalized_code_comparison()` | 338-375 | 정규화된 코드 비교  
`_general_accuracy()` | 377-379 | 일반 정확도 (Exact Match)  
`get_accuracy_scores()` | 381-397 | 통계 집계  
`get_accuracy_by_type()` | 399-405 | 작업 유형별 평균  
  
## ⚙️ 3. 핵심 메서드 상세 설명

### 3.1 QA Accuracy - 4가지 유사도 조합

**목적** : 자연어 답변의 정확도를 다각도로 평가

**위치** : Lines 176-256

**QA Accuracy 최종 공식**  
  
Accuracy = 0.4 × Token_Overlap + 0.3 × Jaccard + 0.2 × LCS + 0.1 × Char_Sim 

#### 알고리즘 1: Token Overlap Ratio (가중치 40%)

**목적** : 핵심 키워드 포함 여부

# 1. 텍스트 정규화 gt_norm = normalize(ground_truth) # 소문자, 공백 정리, 구두점 제거 pred_norm = normalize(prediction) # 2. 토큰화 gt_tokens = set(gt_norm.split()) pred_tokens = set(pred_norm.split()) # 3. 교집합 / Ground Truth 토큰 수 intersection = len(gt_tokens & pred_tokens) overlap_ratio = intersection / len(gt_tokens) # 예시: # Ground Truth: "서울의 인구는 약 천만명입니다" → {서울, 인구, 약, 천만명입니다} # Prediction: "서울 인구는 1000만 정도" → {서울, 인구, 1000만, 정도} # Overlap: {서울, 인구} = 2개 / 4개 = 0.5

#### 알고리즘 2: Jaccard Similarity (가중치 30%)

**목적** : 전체적인 단어 집합 유사도

# Jaccard = |교집합| / |합집합| intersection = len(gt_tokens & pred_tokens) union = len(gt_tokens | pred_tokens) jaccard = intersection / union if union > 0 else 0.0 # 예시 (위와 동일한 경우): # 교집합: {서울, 인구} = 2개 # 합집합: {서울, 인구, 약, 천만명입니다, 1000만, 정도} = 6개 # Jaccard: 2 / 6 = 0.333

#### 알고리즘 3: LCS (Longest Common Subsequence) Ratio (가중치 20%)

**목적** : 단어 순서 보존 평가

def lcs_ratio(s1, s2): m, n = len(s1), len(s2) if m == 0: return 0.0 # Dynamic Programming으로 LCS 길이 계산 dp = [[0] * (n + 1) for _ in range(m + 1)] for i in range(1, m + 1): for j in range(1, n + 1): if s1[i-1] == s2[j-1]: dp[i][j] = dp[i-1][j-1] + 1 else: dp[i][j] = max(dp[i-1][j], dp[i][j-1]) lcs_length = dp[m][n] return lcs_length / m # 예시: # s1: "서울의인구는천만명" (공백 제거) # s2: "서울인구는1000만" # LCS: "서울인구는" (길이 5) # Ratio: 5 / len(s1)

#### 알고리즘 4: Character Similarity (가중치 10%)

**목적** : 오타나 표현 변형 허용

def char_similarity(s1, s2): s1_chars = set(s1) s2_chars = set(s2) if not s1_chars: return 0.0 char_overlap = len(s1_chars & s2_chars) / len(s1_chars) return char_overlap # 예시: # s1 chars: {서, 울, 의, 인, 구, 는, ...} # s2 chars: {서, 울, 인, 구, 는, 1, 0, ...} # 교집합 비율 계산

#### 📊 QA Accuracy 계산 흐름 다이어그램

graph TD A[response & ground_truth] --> B[normalize_text  
소문자, 공백정리, 구두점제거] B --> C1[Token Overlap 40%  
교집합 / GT토큰수] B --> C2[Jaccard 30%  
교집합 / 합집합] B --> C3[LCS 20%  
최장 공통 부분수열] B --> C4[Char Sim 10%  
문자 집합 유사도] C1 --> D[가중 평균 계산  
0.4×T + 0.3×J + 0.2×L + 0.1×C] C2 --> D C3 --> D C4 --> D D --> E[round 3자리  
최종 QA Accuracy] style A fill:#667eea,color:#fff style B fill:#48bb78,color:#fff style C1 fill:#ed8936,color:#fff style C2 fill:#ed8936,color:#fff style C3 fill:#ed8936,color:#fff style C4 fill:#ed8936,color:#fff style D fill:#3182ce,color:#fff style E fill:#667eea,color:#fff 

### 3.2 Code Accuracy - 계층적 비교

**목적** : 코드의 기능적 동등성을 평가 (포맷팅 무시)

**위치** : Lines 258-287

#### 📐 3단계 계층적 비교 전략

  1. **Level 1: Exact Match** → 100% 일치
  2. **Level 2: AST Comparison** → 구조적 동등성 (포맷 무관)
  3. **Level 3: Normalized Comparison** → 공백/주석 제거 후 비교

각 레벨은 순차적으로 시도되며, 가장 높은 점수를 반환합니다.

#### Level 2: AST (Abstract Syntax Tree) 비교

**위치** : Lines 289-336

import ast def _ast_comparison(code1: str, code2: str) -> float: """AST 구조 비교로 코드 동등성 평가""" try: # 1. 코드를 AST로 파싱 tree1 = ast.parse(code1) tree2 = ast.parse(code2) # 2. AST 덤프 (문자열 표현) dump1 = ast.dump(tree1) dump2 = ast.dump(tree2) if dump1 == dump2: return 1.0 # 완전히 동일한 구조 # 3. 부분 일치: AST 노드들의 Jaccard 유사도 nodes1 = set(dump1.split(',')) nodes2 = set(dump2.split(',')) intersection = len(nodes1 & nodes2) union = len(nodes1 | nodes2) return intersection / union if union > 0 else 0.0 except SyntaxError: # 구문 오류 시 AST 비교 불가 return 0.0 

**AST 비교의 장점** :

  * 다른 들여쓰기/공백 → 동일 판정
  * 다른 주석 스타일 → 동일 판정
  * 변수명만 다른 경우도 구조가 같으면 높은 점수

#### Level 3: Normalized Code 비교

**위치** : Lines 338-375

def normalize_code(code: str) -> str: # 1. 주석 제거 code = re.sub(r'#.*?$', '', code, flags=re.MULTILINE) code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL) code = re.sub(r"'''.*?'''", '', code, flags=re.DOTALL) # 2. 공백 정규화 code = re.sub(r'\s+', ' ', code) # 3. Trim return code.strip() norm1 = normalize_code(code1) norm2 = normalize_code(code2) if norm1 == norm2: return 0.95 # 주석만 다를 경우 # 문자 단위 유사도 matches = sum(1 for c1, c2 in zip(norm1, norm2) if c1 == c2) max_len = max(len(norm1), len(norm2)) return matches / max_len if max_len > 0 else 0.0 

#### 📊 Code Accuracy 계층적 비교 흐름 다이어그램

graph TD A[code1 & code2] --> B{Level 1:  
Exact Match?} B -->|Yes| Z1[Accuracy = 1.0] B -->|No| C{Level 2:  
AST 파싱 가능?} C -->|Yes| D[AST Comparison  
ast.dump 비교] D --> D1{AST dump  
완전 일치?} D1 -->|Yes| Z2[Accuracy = 1.0] D1 -->|No| D2[AST 노드  
Jaccard 유사도] D2 --> Z3[Accuracy = 구조 유사도] C -->|No| E[Level 3:  
Normalized Comparison] E --> E1[주석 제거] E1 --> E2[공백 정규화] E2 --> E3{Normalized  
완전 일치?} E3 -->|Yes| Z4[Accuracy = 1.0] E3 -->|No| E4[Token Jaccard] E4 --> Z5[Accuracy = Token 유사도] style A fill:#667eea,color:#fff style B fill:#ed8936,color:#fff style C fill:#ed8936,color:#fff style D fill:#48bb78,color:#fff style E fill:#48bb78,color:#fff style Z1 fill:#38a169,color:#fff style Z2 fill:#38a169,color:#fff style Z3 fill:#38a169,color:#fff style Z4 fill:#38a169,color:#fff style Z5 fill:#38a169,color:#fff 

### 3.3 통계 집계 메서드

def get_accuracy_scores(self) -> Dict[str, float]: """전체 정확도 통계""" if not self.evaluations: return {"overall_accuracy": 0.0} df = pd.DataFrame(self.evaluations) # 표준편차는 단일 값일 때 NaN 반환 가능 std_val = df["accuracy"].std() return { "overall_accuracy": round(df["accuracy"].mean() * 100, 2), "median_accuracy": round(df["accuracy"].median() * 100, 2), "min_accuracy": round(df["accuracy"].min() * 100, 2), "max_accuracy": round(df["accuracy"].max() * 100, 2), "std_accuracy": round(std_val * 100, 2) if not pd.isna(std_val) else 0.0 } def get_accuracy_by_type(self) -> Dict[str, float]: """작업 유형별 평균 정확도""" if not self.evaluations: return {} df = pd.DataFrame(self.evaluations) return df.groupby("task_type")["accuracy"].mean().mul(100).round(2).to_dict() 

## 💻 4. 실제 사용 예제

### 4.1 QA 작업 정확도 평가

from agent_evaluator import PerformanceMonitor, TaskType # 모니터 초기화 monitor = PerformanceMonitor() # QA 작업 실행 question = "대한민국의 수도는?" ground_truth = "서울입니다" agent_answer = "대한민국의 수도는 서울이에요" # 작업 기록 (정확도 자동 계산됨) monitor.record_task( task_id="qa_001", task_type=TaskType.QA, success=True, latency=1.2, completion_score=1.0, expected_output=ground_truth, actual_output=agent_answer, ground_truth=ground_truth ) # 정확도 확인 accuracy_stats = monitor.accuracy_evaluator.get_accuracy_scores() print(f"Overall Accuracy: {accuracy_stats['overall_accuracy']}%") # 예상 결과: 85-90% (키워드는 일치하지만 표현 방식이 약간 다름)

### 4.2 코드 생성 정확도 평가

from agent_evaluator import PerformanceMonitor, TaskType monitor = PerformanceMonitor() # 코드 생성 작업 expected_code = """ def fibonacci(n): if n <= 1: return n return fibonacci(n-1) + fibonacci(n-2) """ agent_code = """ def fibonacci(n): # Base case if n <= 1: return n # Recursive case return fibonacci(n - 1) + fibonacci(n - 2) """ # 작업 기록 monitor.record_task( task_id="code_001", task_type=TaskType.CODE_GENERATION, success=True, latency=2.5, completion_score=1.0, expected_output=expected_code, actual_output=agent_code, ground_truth=expected_code ) # 정확도 확인 accuracy_stats = monitor.accuracy_evaluator.get_accuracy_scores() print(f"Code Accuracy: {accuracy_stats['overall_accuracy']}%") # 예상 결과: ~100% (AST가 동일하므로)

### 4.3 다중 작업 정확도 분석

from agent_evaluator import PerformanceMonitor, TaskType monitor = PerformanceMonitor() # 여러 QA 작업 평가 test_cases = [ { "question": "한국의 수도는?", "ground_truth": "서울", "answer": "서울입니다" }, { "question": "피타고라스 정리는?", "ground_truth": "직각삼각형에서 빗변의 제곱은 다른 두 변의 제곱의 합과 같다", "answer": "a² + b² = c²이며, c는 빗변입니다" }, { "question": "지구의 공전 주기는?", "ground_truth": "365일", "answer": "약 365.25일" } ] for i, case in enumerate(test_cases): monitor.record_task( task_id=f"qa_{i:03d}", task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, expected_output=case["ground_truth"], actual_output=case["answer"], ground_truth=case["ground_truth"] ) # 통계 확인 accuracy_stats = monitor.accuracy_evaluator.get_accuracy_scores() print("\n=== Accuracy Statistics ===") print(f"Overall: {accuracy_stats['overall_accuracy']}%") print(f"Median: {accuracy_stats['median_accuracy']}%") print(f"Min: {accuracy_stats['min_accuracy']}%") print(f"Max: {accuracy_stats['max_accuracy']}%") print(f"Std Dev: {accuracy_stats['std_accuracy']}%") # 작업 유형별 정확도 by_type = monitor.accuracy_evaluator.get_accuracy_by_type() print("\n=== Accuracy by Type ===") for task_type, acc in by_type.items(): print(f"{task_type}: {acc}%") 

## 📦 5. Dashboard Golden Dataset 연계 평가

**Golden Dataset** 은 평가를 위해 미리 준비된 질문-정답 쌍의 데이터셋입니다.  
Agent Evaluator Dashboard는 Golden Dataset을 관리하고, 이를 기반으로 자동 평가를 수행할 수 있는 기능을 제공합니다. 

### 5.1 Golden Dataset 구조 이해

**위치** : `Evaluator_Examples/Dashboard/data/golden_datasets/*.json`

#### 📋 Golden Dataset JSON 구조

각 Golden Dataset은 다음 정보를 포함합니다:

  * **dataset_id** : 데이터셋 고유 식별자
  * **metadata** : 데이터셋 메타정보 (이름, 버전, 설명)
  * **qa_pairs** : 질문-정답 쌍 배열

# Golden Dataset 구조 예시 { "dataset_id": "sample_qa_dataset_001", "source_document": "Sample QA Collection", "created_at": "2024-12-10", "total_qa_pairs": 10, "metadata": { "dataset_name": "Sample QA Dataset", "version": "0.5.0", "description": "자동 평가를 위한 샘플 Golden Dataset" }, "qa_pairs": [ { "qa_id": "qa_001", "question": "대한민국의 수도는 어디인가요?", "answer": "대한민국의 수도는 서울입니다.", "context": "서울은 대한민국의 수도이며...", "ground_truth": "서울", ← Accuracy 평가에 사용 "expected_tools": ["search", "knowledge_base"], "task_type": "qa" } ] } 

### 5.2 Golden Dataset 기반 자동 평가 (기본)

import json from pathlib import Path from agent_evaluator import PerformanceMonitor, TaskType # 1. Golden Dataset 로드 dataset_path = Path("Evaluator_Examples/Dashboard/data/golden_datasets/sample_auto_eval_dataset.json") with open(dataset_path, 'r', encoding='utf-8') as f: golden_dataset = json.load(f) # 2. PerformanceMonitor 초기화 monitor = PerformanceMonitor() # 3. 각 QA 쌍에 대해 Agent 실행 및 평가 for qa_pair in golden_dataset["qa_pairs"]: # Agent 실행 (실제 구현에서는 여기에 Agent 호출 로직) agent_response = your_agent.run(qa_pair["question"]) # 평가 기록 (Accuracy 자동 계산) monitor.record_task( task_id=qa_pair["qa_id"], task_type=TaskType.QA, success=True, latency=agent_response.execution_time, completion_score=1.0, expected_output=qa_pair["ground_truth"], ← Golden Dataset의 정답 actual_output=agent_response.answer, ground_truth=qa_pair["ground_truth"] ← Accuracy 계산에 사용 ) # 4. 전체 정확도 확인 accuracy_stats = monitor.accuracy_evaluator.get_accuracy_scores() print(f\"Overall Accuracy: {accuracy_stats['overall_accuracy']}%\") print(f\"Median Accuracy: {accuracy_stats['median_accuracy']}%\") print(f\"Min Accuracy: {accuracy_stats['min_accuracy']}%\") print(f\"Max Accuracy: {accuracy_stats['max_accuracy']}%\") 

### 5.3 evaluate_with_golden_dataset() 사용 (원스텝)

`PerformanceMonitor`는 Golden Dataset을 자동으로 로드하고 평가하는 편의 메서드를 제공합니다.

from agent_evaluator import PerformanceMonitor from pathlib import Path # 1. Monitor 초기화 monitor = PerformanceMonitor() # 2. Golden Dataset 경로 지정 dataset_path = "Evaluator_Examples/Dashboard/data/golden_datasets/sample_auto_eval_dataset.json" # 3. Agent 함수 정의 def my_agent(question: str) -> str: \"\"\"실제 Agent 로직\"\"\" # 여기에 실제 Agent 호출 코드 response = your_llm.generate(question) return response # 4. 자동 평가 실행 results = monitor.evaluate_with_golden_dataset( dataset_path=dataset_path, agent_function=my_agent, verbose=True # 진행 상황 출력 ) # 5. 결과 확인 print(f\"\\\n평가 완료: {results['total_evaluated']}개\") print(f\"Overall Accuracy: {results['accuracy']['overall_accuracy']}%\") # 6. Dashboard에 저장 save_path = monitor.save_to_file("golden_eval_results.json") print(f\"\\\n결과 저장: {save_path}\") 

### 5.4 Dashboard Integration (Dashboard 저장소 직접 사용)

#### 💡 Zero Configuration 저장

Dashboard 통합 유틸리티를 사용하면 자동으로 Dashboard의 저장소 경로를 찾아 결과를 저장합니다.

from agent_evaluator import PerformanceMonitor from agent_evaluator.utils.dashboard_integration import save_to_dashboard import json from pathlib import Path # 1. Dashboard의 Golden Dataset 로드 from agent_evaluator.utils.path_helpers import find_project_root, get_dashboard_dir project_root = find_project_root() dashboard_dir = get_dashboard_dir(project_root) golden_dataset_path = dashboard_dir / "data" / "golden_datasets" / "sample_auto_eval_dataset.json" with open(golden_dataset_path, 'r', encoding='utf-8') as f: golden_data = json.load(f) # 2. 평가 실행 monitor = PerformanceMonitor() for qa_pair in golden_data["qa_pairs"]: agent_answer = your_agent.run(qa_pair["question"]) monitor.record_task( task_id=qa_pair["qa_id"], task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, ground_truth=qa_pair["ground_truth"], ← 정확도 계산 actual_output=agent_answer ) # 3. Dashboard 저장소에 자동 저장 result_path = save_to_dashboard( monitor, filename="my_evaluation_results.json", prefer_dashboard=True, # Dashboard 우선 verbose=True ) # 출력 예시: # 📁 Dashboard 저장소에 저장됨 # 경로: /path/to/Dashboard/data/evaluation_results/my_evaluation_results.json # 💡 Dashboard에서 바로 확인 가능합니다!

### 5.5 완전한 예제: Golden Dataset → 평가 → Dashboard

#!/usr/bin/env python3 \"\"\" Golden Dataset 기반 완전 자동 평가 예제 ======================================== Dashboard의 Golden Dataset을 로드하여: 1\. Agent 실행 2\. Accuracy 자동 계산 3\. Dashboard 저장소에 결과 저장 \"\"\" import json from pathlib import Path from agent_evaluator import PerformanceMonitor, TaskType from agent_evaluator.utils.dashboard_integration import save_to_dashboard # ============================================================ # 1. Golden Dataset 로드 # ============================================================ golden_dataset_path = Path( "Evaluator_Examples/Dashboard/data/golden_datasets/sample_auto_eval_dataset.json" ) with open(golden_dataset_path, 'r', encoding='utf-8') as f: golden_data = json.load(f) print(f\"✅ Golden Dataset 로드 완료: {golden_data['metadata']['dataset_name']}\") print(f\" 총 {golden_data['total_qa_pairs']}개 QA 쌍\") # ============================================================ # 2. Agent 함수 정의 (실제 구현에서는 LLM 호출) # ============================================================ def dummy_agent(question: str) -> str: \"\"\"테스트용 더미 Agent (실제로는 LLM 호출)\"\"\" # 실제 구현: # return openai.ChatCompletion.create(...) # return langchain_chain.run(question) # 더미 응답 if "수도" in question: return "서울입니다" elif "한글" in question: return "세종대왕" else: return "답변을 찾을 수 없습니다" # ============================================================ # 3. 평가 실행 # ============================================================ monitor = PerformanceMonitor() print(\"\\\n🚀 평가 시작...\") for i, qa_pair in enumerate(golden_data["qa_pairs"], 1): print(f\"\\\n[{i}/{golden_data['total_qa_pairs']}] {qa_pair['qa_id']}\") print(f\" Question: {qa_pair['question']}\") # Agent 실행 agent_answer = dummy_agent(qa_pair["question"]) print(f\" Agent: {agent_answer}\") print(f\" Ground Truth: {qa_pair['ground_truth']}\") # 평가 기록 (Accuracy 자동 계산) monitor.record_task( task_id=qa_pair["qa_id"], task_type=getattr(TaskType, qa_pair["task_type"].upper(), TaskType.QA), success=True, latency=0.5, completion_score=1.0, expected_output=qa_pair["ground_truth"], actual_output=agent_answer, ground_truth=qa_pair["ground_truth"] ← 핵심: Accuracy 계산 ) # ============================================================ # 4. 결과 통계 # ============================================================ accuracy_stats = monitor.accuracy_evaluator.get_accuracy_scores() print(\"\\\n\" + \"=\"*60) print(\"📊 평가 결과\") print(\"=\"*60) print(f\"Overall Accuracy: {accuracy_stats['overall_accuracy']}%\") print(f\"Median Accuracy: {accuracy_stats['median_accuracy']}%\") print(f\"Min Accuracy: {accuracy_stats['min_accuracy']}%\") print(f\"Max Accuracy: {accuracy_stats['max_accuracy']}%\") print(f\"Std Dev: {accuracy_stats['std_accuracy']}%\") # ============================================================ # 5. Dashboard 저장소에 저장 # ============================================================ result_path = save_to_dashboard( monitor, filename=f\"golden_eval_{golden_data['dataset_id']}.json\", prefer_dashboard=True, verbose=True ) print(\"\\\n✅ 평가 완료! Dashboard에서 확인하세요.\") 

### 5.6 Golden Dataset 작성 가이드

**✅ Golden Dataset 작성 Best Practices**

  1. **명확한 ground_truth**
     * 간결하고 핵심적인 정답 제공
     * 예: "서울" (O), "음... 서울인 것 같아요" (X)
  2. **다양한 난이도**
     * 쉬운 질문부터 어려운 질문까지 포함
     * Agent의 전반적인 성능 파악
  3. **context 제공**
     * 정답의 근거가 되는 배경 정보
     * RAG 시스템 평가 시 특히 중요
  4. **task_type 명시**
     * "qa", "code_generation", "classification" 등
     * 적절한 Accuracy 알고리즘 선택
  5. **expected_tools (선택)**
     * Layer 2 Tool Selection 평가용
     * Agent가 사용해야 할 도구 명시

### 5.7 여러 Golden Dataset 배치 평가

from pathlib import Path import json # Dashboard의 모든 Golden Dataset 찾기 golden_datasets_dir = Path("Evaluator_Examples/Dashboard/data/golden_datasets") dataset_files = list(golden_datasets_dir.glob("*.json")) print(f\"발견된 Golden Dataset: {len(dataset_files)}개\\\n\") # 각 데이터셋별로 평가 all_results = {} for dataset_file in dataset_files: print(f\"\\\n{'='*60}\") print(f\"📊 평가 중: {dataset_file.name}\") print(f\"{'='*60}\") # 새 Monitor 인스턴스 (데이터셋별 독립 평가) monitor = PerformanceMonitor() # Golden Dataset 로드 with open(dataset_file, 'r', encoding='utf-8') as f: golden_data = json.load(f) # 평가 실행 for qa_pair in golden_data["qa_pairs"]: agent_answer = your_agent.run(qa_pair["question"]) monitor.record_task( task_id=qa_pair["qa_id"], task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, ground_truth=qa_pair["ground_truth"], actual_output=agent_answer ) # 결과 수집 accuracy_stats = monitor.accuracy_evaluator.get_accuracy_scores() all_results[dataset_file.stem] = accuracy_stats print(f\"\\\n✅ {dataset_file.name} 완료\") print(f\" Accuracy: {accuracy_stats['overall_accuracy']}%\") # Dashboard 저장 save_to_dashboard( monitor, filename=f\"eval_{dataset_file.stem}.json\" ) # 전체 결과 요약 print(\"\\\n\" + \"=\"*60) print(\"📈 전체 평가 요약\") print(\"=\"*60) for dataset_name, stats in all_results.items(): print(f\"{dataset_name}: {stats['overall_accuracy']}%\") 

#### ⚠️ Dashboard 연계 시 주의사항

  * **경로 일관성** : Golden Dataset과 평가 결과는 Dashboard의 data/ 디렉토리 사용 권장
  * **파일명 규칙** : 타임스탬프나 dataset_id를 포함하여 중복 방지
  * **버전 관리** : Golden Dataset 수정 시 version 필드 업데이트
  * **메타데이터** : 평가 결과에 어떤 Golden Dataset을 사용했는지 기록
  * **백업** : Golden Dataset은 중요한 자산이므로 별도 백업 필수

## 🤖 6. 평가 데이터 자동 처리 방안

**실제 프로젝트에서는 수백~수천 개의 작업을 평가해야 합니다.**  
이 섹션에서는 Accuracy 평가를 최대한 자동화하여 수작업을 최소화하는 방법을 다룹니다. 

### 6.1 자동화 수준별 전략

레벨 | 자동화 범위 | Ground Truth 수집 | 적용 시나리오  
---|---|---|---  
**Level 1** | Golden Dataset 기반 | 사전 준비 필요 | 벤치마크, 반복 평가  
**Level 2** | RAG 컨텍스트 활용 | 문서에서 자동 추출 | RAG 시스템 평가  
**Level 3** | LLM-as-Judge | 불필요 (의미적 평가) | Ground Truth 없는 경우  
**Level 4** | 규칙 기반 검증 | 패턴/정규식으로 검증 | 구조화된 응답 평가  
**Level 5** | 하이브리드 | 복합 전략 | 복잡한 프로덕션 환경  
  
### 6.2 Level 1: Golden Dataset 기반 완전 자동화

#### 💡 핵심 아이디어

사전에 준비된 Golden Dataset을 사용하여 ground_truth 기반 Accuracy를 자동 계산합니다.

**장점** : 완전 자동, 재현 가능, 벤치마킹 용이

**단점** : Golden Dataset 작성 필요

from agent_evaluator import PerformanceMonitor, TaskType from agent_evaluator.utils.dashboard_integration import save_to_dashboard import json from pathlib import Path from concurrent.futures import ThreadPoolExecutor # ============================================================ # Golden Dataset 로드 # ============================================================ dataset_path = Path("Evaluator_Examples/Dashboard/data/golden_datasets/sample_auto_eval_dataset.json") with open(dataset_path, 'r', encoding='utf-8') as f: golden_data = json.load(f) monitor = PerformanceMonitor() # ============================================================ # 병렬 평가 함수 # ============================================================ def evaluate_single_qa(qa_pair: dict) -> dict: """단일 QA 쌍 평가""" try: # Agent 실행 agent_answer = your_agent.run(qa_pair["question"]) return { "qa_id": qa_pair["qa_id"], "question": qa_pair["question"], "ground_truth": qa_pair["ground_truth"], "actual_output": agent_answer, "task_type": qa_pair.get("task_type", "qa"), "success": True } except Exception as e: return { "qa_id": qa_pair["qa_id"], "success": False, "error": str(e) } # ============================================================ # 병렬 실행 (10배 빠름) # ============================================================ print(f"🚀 {len(golden_data['qa_pairs'])}개 QA 쌍 평가 시작...") with ThreadPoolExecutor(max_workers=10) as executor: results = list(executor.map(evaluate_single_qa, golden_data["qa_pairs"])) # ============================================================ # 결과 기록 (Accuracy 자동 계산) # ============================================================ for result in results: if result["success"]: monitor.record_task( task_id=result["qa_id"], task_type=getattr(TaskType, result["task_type"].upper(), TaskType.QA), success=True, latency=0.5, completion_score=1.0, ground_truth=result["ground_truth"], ← 자동 Accuracy 계산 actual_output=result["actual_output"] ) else: print(f"❌ {result['qa_id']} 실패: {result['error']}") # ============================================================ # 결과 출력 및 저장 # ============================================================ accuracy_stats = monitor.accuracy_evaluator.get_accuracy_scores() print(f"\n✅ 평가 완료!") print(f"Overall Accuracy: {accuracy_stats['overall_accuracy']}%") # Dashboard 자동 저장 save_to_dashboard(monitor, filename="automated_accuracy_eval.json") 

### 6.3 Level 2: RAG 시스템 자동 평가

#### 💡 핵심 아이디어

RAG 시스템에서 검색된 문서를 ground_truth로 사용하여 자동 평가합니다.

**장점** : Ground Truth 수동 작성 불필요

**단점** : 검색 품질에 의존

from agent_evaluator import PerformanceMonitor, TaskType class RAGAutoEvaluator: """RAG 시스템 자동 평가""" def __init__(self, rag_system, monitor: PerformanceMonitor): self.rag_system = rag_system self.monitor = monitor def auto_evaluate_rag(self, questions: list[str]): """RAG 시스템 자동 평가 1\. 질문에 대해 관련 문서 검색 2\. 검색된 문서를 ground_truth로 사용 3\. Agent 응답과 비교 """ for i, question in enumerate(questions): # 1. 관련 문서 검색 retrieved_docs = self.rag_system.retrieve(question) ground_truth_context = " ".join([doc.page_content for doc in retrieved_docs]) # 2. Agent 응답 생성 agent_answer = self.rag_system.generate(question, retrieved_docs) # 3. 핵심 정보 추출 (옵션 1: 정규식) # 예: 숫자, 날짜, 고유명사 등 import re numbers_in_context = re.findall(r'\d+', ground_truth_context) numbers_in_answer = re.findall(r'\d+', agent_answer) # 4. Ground Truth 생성 (옵션 2: LLM 사용) ground_truth = self.extract_answer_from_context( question, ground_truth_context ) # 5. 평가 기록 self.monitor.record_task( task_id=f"rag_qa_{i:03d}", task_type=TaskType.QA, success=True, latency=1.0, completion_score=1.0, ground_truth=ground_truth, ← 자동 생성된 정답 actual_output=agent_answer, context=ground_truth_context ← Hallucination 평가용 ) def extract_answer_from_context(self, question: str, context: str) -> str: """컨텍스트에서 질문에 대한 정답 추출 (LLM 사용)""" prompt = f""" 다음 문서에서 질문에 대한 정확한 답변을 추출하세요. 답변은 간결하고 핵심만 포함해야 합니다. 문서: {context} 질문: {question} 정답:""" # LLM 호출로 정답 추출 ground_truth = your_llm.generate(prompt) return ground_truth.strip() # ============================================================ # 사용 예시 # ============================================================ monitor = PerformanceMonitor() evaluator = RAGAutoEvaluator(your_rag_system, monitor) # 평가할 질문 리스트 questions = [ "대한민국의 수도는?", "서울의 인구는?", "한국의 GDP는?" ] # 자동 평가 실행 evaluator.auto_evaluate_rag(questions) # 결과 확인 accuracy_stats = monitor.accuracy_evaluator.get_accuracy_scores() print(f"RAG Accuracy: {accuracy_stats['overall_accuracy']}%") 

### 6.4 Level 3: LLM-as-Judge (Ground Truth 없이 평가)

#### 💡 핵심 아이디어

Ground Truth가 없는 경우, 강력한 LLM(GPT-4 등)을 사용하여 응답 품질을 평가합니다.

**장점** : Ground Truth 불필요, 의미적 평가 가능

**단점** : LLM 비용, 주관적일 수 있음

from agent_evaluator import PerformanceMonitor, TaskType from openai import OpenAI class LLMJudgeAccuracyEvaluator: """LLM을 Judge로 사용한 Accuracy 평가""" def __init__(self, api_key: str, monitor: PerformanceMonitor): self.client = OpenAI(api_key=api_key) self.monitor = monitor def evaluate_with_llm( self, task_id: str, question: str, agent_answer: str, reference_context: str = None ) -> float: """LLM을 사용한 Accuracy 평가 Returns: float: 0.0 ~ 1.0 사이의 정확도 점수 """ # Evaluation Prompt 구성 context_part = f"\n\n참조 문서:\n{reference_context}" if reference_context else "" evaluation_prompt = f""" 다음 질문에 대한 AI Agent의 답변을 평가하세요.{context_part} 질문: {question} Agent 답변: {agent_answer} 평가 기준: 1\. 사실적 정확성 (40점): 정보가 정확하고 사실에 부합하는가? 2\. 완성도 (30점): 질문에 대한 완전한 답변인가? 3\. 명확성 (20점): 이해하기 쉽고 명확한가? 4\. 관련성 (10점): 질문과 직접적으로 관련이 있는가? 100점 만점으로 평가하고, 점수만 출력하세요. 점수:""" try: completion = self.client.chat.completions.create( model="gpt-4", messages=[ {"role": "system", "content": "당신은 공정하고 엄격한 평가자입니다."}, {"role": "user", "content": evaluation_prompt} ], temperature=0.0 ) # 점수 추출 (0-100 → 0.0-1.0) score_text = completion.choices[0].message.content.strip() score = float(score_text) / 100.0 score = max(0.0, min(1.0, score)) # Clamp to [0, 1] # 평가 기록 self.monitor.record_task( task_id=task_id, task_type=TaskType.QA, success=True, latency=1.0, completion_score=score, actual_output=agent_answer ) # Accuracy Evaluator에 직접 추가 self.monitor.accuracy_evaluator.add_evaluation( task_id=task_id, task_type="qa", ground_truth="[LLM-Judged]", # 마커 prediction=agent_answer, accuracy=score ) return score except Exception as e: print(f"❌ LLM 평가 실패: {e}") return 0.0 def batch_evaluate(self, qa_pairs: list[dict]): """배치 평가""" for qa in qa_pairs: agent_answer = your_agent.run(qa["question"]) score = self.evaluate_with_llm( task_id=qa["qa_id"], question=qa["question"], agent_answer=agent_answer, reference_context=qa.get("context") ) print(f"✅ {qa['qa_id']}: {score*100:.1f}%") # ============================================================ # 사용 예시 # ============================================================ monitor = PerformanceMonitor() llm_judge = LLMJudgeAccuracyEvaluator(api_key="your-api-key", monitor=monitor) qa_pairs = [ { "qa_id": "qa_001", "question": "양자 컴퓨터의 원리를 설명하세요", "context": "양자 컴퓨터는 중첩과 얽힘을 이용..." # 선택 } ] llm_judge.batch_evaluate(qa_pairs) # 결과 확인 accuracy_stats = monitor.accuracy_evaluator.get_accuracy_scores() print(f"\nLLM-Judged Accuracy: {accuracy_stats['overall_accuracy']}%") 

### 6.5 Level 4: 규칙 기반 자동 검증

#### 💡 핵심 아이디어

구조화된 응답(JSON, 표, 코드 등)은 규칙 기반으로 자동 검증 가능합니다.

**장점** : 빠르고 결정론적

**단점** : 유연성 낮음, 규칙 작성 필요

from agent_evaluator import PerformanceMonitor, TaskType import json import re class RuleBasedAccuracyChecker: """규칙 기반 Accuracy 자동 검증""" def __init__(self, monitor: PerformanceMonitor): self.monitor = monitor def check_json_accuracy( self, task_id: str, expected_schema: dict, actual_output: str ) -> float: """JSON 응답의 스키마 일치도 검사""" try: actual_json = json.loads(actual_output) except json.JSONDecodeError: return 0.0 # 필드 일치도 계산 expected_keys = set(expected_schema.keys()) actual_keys = set(actual_json.keys()) # 1. 키 존재 여부 (50%) key_overlap = len(expected_keys & actual_keys) / len(expected_keys) # 2. 값 타입 일치 (30%) type_score = 0.0 matching_keys = expected_keys & actual_keys if matching_keys: type_matches = sum( 1 for key in matching_keys if type(actual_json[key]).__name__ == expected_schema[key] ) type_score = type_matches / len(matching_keys) # 3. 추가 키 패널티 (20%) extra_keys = actual_keys - expected_keys extra_penalty = len(extra_keys) / max(len(actual_keys), 1) extra_score = max(0.0, 1.0 - extra_penalty) # 최종 점수 accuracy = 0.5 * key_overlap + 0.3 * type_score + 0.2 * extra_score return accuracy def check_code_syntax( self, task_id: str, code: str, language: str = "python" ) -> float: """코드 구문 오류 검사""" if language == "python": import ast try: ast.parse(code) return 1.0 # 구문 정상 except SyntaxError: return 0.3 # 구문 오류 (부분 점수) return 0.5 # 검증 불가 def check_pattern_match( self, task_id: str, expected_patterns: list[str], actual_output: str ) -> float: """정규식 패턴 매칭 (이메일, URL, 날짜 등)""" matches = 0 for pattern in expected_patterns: if re.search(pattern, actual_output): matches += 1 accuracy = matches / len(expected_patterns) if expected_patterns else 0.0 return accuracy # ============================================================ # 사용 예시 1: JSON 응답 검증 # ============================================================ monitor = PerformanceMonitor() checker = RuleBasedAccuracyChecker(monitor) # 예상 JSON 스키마 expected_schema = { "name": "str", "age": "int", "email": "str" } # Agent 응답 agent_output = '''{"name": "홍길동", "age": 30, "email": "hong@example.com"}''' # 자동 검증 accuracy = checker.check_json_accuracy( task_id="json_001", expected_schema=expected_schema, actual_output=agent_output ) print(f"JSON Accuracy: {accuracy*100:.1f}%") # ============================================================ # 사용 예시 2: 패턴 검증 (이메일 추출) # ============================================================ agent_response = "연락처: support@company.com, 전화: 02-1234-5678" email_accuracy = checker.check_pattern_match( task_id="extract_001", expected_patterns=[ r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\b', # 이메일 r'\d{2,3}-\d{3,4}-\d{4}' # 전화번호 ], actual_output=agent_response ) print(f"Pattern Match Accuracy: {email_accuracy*100:.1f}%") 

### 6.6 Level 5: 하이브리드 전략

#### 💡 핵심 아이디어

여러 자동화 전략을 조합하여 최적의 평가를 수행합니다.

from agent_evaluator import PerformanceMonitor, TaskType class HybridAccuracyEvaluator: """하이브리드 Accuracy 평가기""" def __init__(self, monitor: PerformanceMonitor): self.monitor = monitor self.rule_checker = RuleBasedAccuracyChecker(monitor) self.llm_judge = None # 필요 시 초기화 def evaluate_with_strategy( self, task_id: str, question: str, agent_answer: str, ground_truth: str = None, task_type: str = "qa" ): """작업 유형에 따라 최적 전략 선택""" # 전략 1: Ground Truth 있으면 기본 Accuracy if ground_truth: self.monitor.record_task( task_id=task_id, task_type=getattr(TaskType, task_type.upper(), TaskType.QA), success=True, latency=1.0, completion_score=1.0, ground_truth=ground_truth, ← 기본 Accuracy 계산 actual_output=agent_answer ) return "standard" # 전략 2: JSON/코드면 규칙 기반 if task_type == "code_generation": accuracy = self.rule_checker.check_code_syntax( task_id=task_id, code=agent_answer ) return f"rule_based (syntax: {accuracy*100:.0f}%)" if agent_answer.strip().startswith("{"): # JSON 응답으로 추정 return "rule_based (json)" # 전략 3: Ground Truth 없고 자유 텍스트면 LLM Judge if self.llm_judge: score = self.llm_judge.evaluate_with_llm( task_id=task_id, question=question, agent_answer=agent_answer ) return f"llm_judge (score: {score*100:.0f}%)" return "no_evaluation" # ============================================================ # 사용 예시 # ============================================================ monitor = PerformanceMonitor() hybrid = HybridAccuracyEvaluator(monitor) # 다양한 작업 타입 처리 tasks = [ {"id": "qa_001", "type": "qa", "gt": "서울"}, # → Standard {"id": "code_001", "type": "code_generation", "gt": None}, # → Rule-based {"id": "gen_001", "type": "qa", "gt": None} # → LLM Judge ] for task in tasks: agent_answer = your_agent.run(task["question"]) strategy = hybrid.evaluate_with_strategy( task_id=task["id"], question=task["question"], agent_answer=agent_answer, ground_truth=task["gt"], task_type=task["type"] ) print(f"✅ {task['id']}: {strategy}") 

### 6.7 성능 최적화 팁

**⚡ 대량 평가 최적화**

#### 1\. 병렬 처리

  * **ThreadPoolExecutor** : I/O 바운드 작업 (API 호출)
  * **ProcessPoolExecutor** : CPU 바운드 작업 (AST 비교)
  * 적정 워커 수: 10-20개 (API rate limit 고려)

#### 2\. 캐싱

  * **Ground Truth 캐싱** : 동일 질문 재사용
  * **LLM 응답 캐싱** : 동일 평가 프롬프트 재사용
  * **AST 파싱 캐싱** : 동일 코드 재평가 방지

#### 3\. 배치 처리

  * 100-200개씩 배치로 처리
  * 중간 결과 저장 (장애 복구)
  * 진행 상황 로깅

# 캐싱 예시 from functools import lru_cache import hashlib class CachedEvaluator: def __init__(self): self.cache = {} @lru_cache(maxsize=1000) def _calculate_accuracy(self, gt_hash: str, pred_hash: str) -> float: """해시 기반 캐싱""" # 실제 계산 (비용이 큰 작업) return self._qa_accuracy(gt, prediction) def evaluate(self, ground_truth: str, prediction: str) -> float: # 해시 생성 gt_hash = hashlib.md5(ground_truth.encode()).hexdigest() pred_hash = hashlib.md5(prediction.encode()).hexdigest() return self._calculate_accuracy(gt_hash, pred_hash) 

#### ⚠️ 자동화 주의사항

  * **검증 필수** : 자동 평가 결과는 샘플링하여 인간 검증
  * **편향 체크** : LLM Judge는 특정 스타일 선호 가능
  * **비용 모니터링** : LLM API 비용 추적 (GPT-4 비쌈)
  * **버전 관리** : 평가 방법 변경 시 버전 기록
  * **Ground Truth 품질** : 자동 생성된 Ground Truth는 주기적 검토

## 🔌 7. Framework Integration

### 7.1 LangChain 통합

from langchain.agents import AgentExecutor from agent_evaluator.integrations import LangChainEvaluator evaluator = LangChainEvaluator() result = evaluator.run_and_evaluate( agent=agent, task_input="What is the capital of France?", task_id="qa_001", task_type=TaskType.QA, ground_truth="Paris" # 정확도 평가에 사용 ) # 정확도 자동 계산됨 accuracy = evaluator.monitor.accuracy_evaluator.get_accuracy_scores() print(f"Accuracy: {accuracy['overall_accuracy']}%") 

## 📊 8. Best Practices

#### ✅ Accuracy 측정 Best Practices

  1. **Ground Truth 품질**
     * 정확하고 명확한 정답 제공
     * 여러 정답이 가능한 경우 모두 고려
  2. **작업 유형 분류**
     * QA와 Code를 명확히 구분
     * 적절한 평가 알고리즘 선택
  3. **임계값 설정**
     * QA: 70% 이상을 정확한 답변으로 간주
     * Code: 90% 이상 (기능적 동등성 중요)
  4. **정기적 캘리브레이션**
     * 인간 평가와 자동 평가 비교
     * 알고리즘 가중치 조정

#### ⚠️ 주의사항

  * **문화적 차이** : "서울"과 "Seoul"은 다르게 평가될 수 있음
  * **단위 변환** : "1km"와 "1000m"는 의미적으로 같지만 다르게 평가
  * **코드 주석** : 주석이 많으면 AST는 같지만 normalized 점수 차이
  * **과적합 방지** : 특정 데이터셋에만 높은 정확도 주의

## 🔍 9. 관련 지표

관련 지표 | 관계 | 문서 링크  
---|---|---  
**TCR** | 완료율 + 정확도 = 전체 품질 | [TCR 가이드](<01_TASK_COMPLETION_RATE.html>)  
**Quality Score** | Accuracy는 Quality의 한 차원 | [Quality 가이드](<04_QUALITY_SCORE.html>)  
**Hallucination** | 낮은 Accuracy의 원인 | [Hallucination 가이드](<03_HALLUCINATION.html>)  
  
## 📚 10. 참고 자료

  * [Agent Evaluator 메인 문서](<../README.html>)
  * [종합 학습 가이드](<../LEARNING_GUIDE.html>)
  * [전체 지표 인덱스](<ALL_METRICS_INDEX.html>)

**최종 업데이트** : 2025-12-16 | **버전** : Agent Evaluator v0.5.0

**문서** : Accuracy 상세 가이드

© 2025 Agent Evaluator. All rights reserved.
