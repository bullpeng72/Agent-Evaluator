# 📊 Task Completion Rate (TCR)

AI Agent Task Completion Tracking and Analysis

Agent Evaluator v0.5.0 - Layer 1 Foundation Metric

## 🎯 개요

**Task Completion Rate (TCR)** 는 AI 에이전트가 할당받은 작업을 성공적으로 완료한 비율을 나타내는 가장 기본적이고 중요한 평가 지표입니다.   
  
TCR은 가중 평균 방식으로 계산되며, Full Success (1.0), Partial Success (0.7), Failure (0.0)로 구분하여 현실적인 성능 평가를 제공합니다. 

### ⚠️ 중요성

  * **직관적 성능 지표** : 복잡한 메트릭 없이 Agent의 성능을 한눈에 파악
  * **비즈니스 임팩트 측정** : 실제 업무 효율성 직접 반영
  * **벤치마크 비교** : 산업 표준 및 경쟁사 비교 가능
  * **개선 방향 제시** : 부분 성공/실패 패턴 분석으로 개선점 도출
  * **SLA 모니터링** : 서비스 수준 합의 준수 여부 추적

## 📍 구현 위치

**파일:** `agent_evaluator/core/agent_evaluator.py`  
**클래스:** `TaskCompletionTracker`  
**라인:** 79-142 (총 64줄) 

### 핵심 메서드

TCR 범위 | 등급 | 설명 | 권장 조치  
---|---|---|---  
95% 이상 | **Industry Leading** | 업계 최고 수준 | 현재 수준 유지, 고급 최적화 고려  
85-94% | **Good Performance** | 우수한 성능 | 세부 최적화 기회 탐색  
70-84% | **Acceptable** | 허용 가능 | 주요 실패 원인 분석 및 개선 필요  
70% 미만 | **Needs Improvement** | 개선 필요 | 즉각적인 개선 조치 및 재설계 고려  
  
## 📊 TCR 벤치마크 기준

속성/메서드 | 라인 | 설명  
---|---|---  
`__init__()` | 82-88 | 트래커 초기화, 완료 기준 설정  
`add_task()` | 90-92 | 작업 결과 추가  
`calculate_tcr()` | 94-122 | TCR 계산 (전체 또는 타입별)  
`get_tcr_by_type()` | 124-130 | 작업 유형별 TCR 분석  
`get_benchmark_status()` | 132-141 | 벤치마크 등급 판정  
  
## 📋 TCR 계산 공식

**TCR** 은 가중 평균 방식으로 계산됩니다:   
  
**TCR = (가중 완료 점수 합 / 전체 작업 수) × 100**   
  
각 작업의 `completion_score` (0.0-1.0)를 합산하여 평균을 구하고 백분율로 표시합니다. 

### 완료 기준

등급 | Completion Score | 설명  
---|---|---  
**Full Success** | 1.0 | 작업을 100% 완료  
**Partial Success** | 0.7 ~ 0.99 | 작업을 부분적으로 완료 (70% 이상)  
**Failure** | 0.0 ~ 0.69 | 작업 실패 (70% 미만)  
  
### 데이터 구조

# TaskResult 구조 (TaskResult 클래스 사용) class TaskResult: task_id: str task_type: str # QA, CODE_GENERATION, SUMMARIZATION 등 completion_score: float # 0.0 ~ 1.0 success: bool start_time: datetime end_time: datetime latency: float # 초 단위 # 완료 기준 (TaskCompletionTracker) completion_criteria = { "full_success": 1.0, # 100% 완료 "partial_success": 0.7, # 70% 이상 "failure": 0.0 # 70% 미만 } 

## ⚙️ 핵심 메서드 상세 설명

### calculate_tcr() - TCR 계산

**목적** : 전체 또는 특정 작업 유형에 대한 TCR 계산

**위치** : Lines 94-122

def calculate_tcr(self, task_type: Optional[str] = None) -> Dict[str, float]: """Calculate Task Completion Rate Args: task_type: Optional task type filter (e.g., 'QA', 'CODE_GENERATION') Returns: Dict with TCR metrics: \- tcr: Overall completion rate (0-100) \- total_tasks: Number of tasks evaluated \- full_success: Count of fully completed tasks \- partial_success: Count of partially completed tasks \- failures: Count of failed tasks \- success_rate: Full success percentage """ # 1. 작업 필터링 (task_type 지정 시) tasks = self.tasks if task_type: tasks = [t for t in tasks if t.task_type == task_type] if not tasks: return {"tcr": 0.0, "total_tasks": 0} # 2. 가중 완료 점수 계산 weighted_completions = sum( t.completion_score for t in tasks ) # 3. TCR = (가중 합 / 전체 작업 수) × 100 tcr = (weighted_completions / len(tasks)) * 100 # 4. 완료 상태별 카운트 full_success_count = sum(1 for t in tasks if t.completion_score >= 1.0) partial_count = sum(1 for t in tasks if 0.7 <= t.completion_score < 1.0) failure_count = sum(1 for t in tasks if t.completion_score < 0.7) # 5. 결과 반환 return { "tcr": round(tcr, 2), "total_tasks": len(tasks), "full_success": full_success_count, "partial_success": partial_count, "failures": failure_count, "success_rate": round((full_success_count / len(tasks)) * 100, 2) } 

#### ✅ 계산 로직 핵심 포인트

  1. **가중 평균 방식** : 각 작업의 completion_score(0.0-1.0)를 합산하여 평균
  2. **부분 성공 인정** : 0.7 이상을 부분 성공으로 간주하여 현실적인 평가
  3. **다차원 분석** : TCR뿐 아니라 full/partial/failure 분포도 제공
  4. **타입별 분석** : 선택적으로 특정 작업 유형만 필터링 가능

### get_tcr_by_type() - 작업 유형별 TCR

**목적** : 모든 작업 유형에 대한 TCR 분석

**위치** : Lines 124-130

def get_tcr_by_type(self) -> Dict[str, Dict[str, float]]: """Get TCR breakdown by task type Returns: Dictionary mapping task_type -> TCR metrics Example: { 'QA': {'tcr': 92.5, 'total_tasks': 20, ...}, 'CODE_GENERATION': {'tcr': 85.0, 'total_tasks': 15, ...}, 'SUMMARIZATION': {'tcr': 88.3, 'total_tasks': 18, ...} } """ # 모든 작업 유형 추출 task_types = set(t.task_type for t in self.tasks) # 각 유형별로 TCR 계산 return { task_type: self.calculate_tcr(task_type) for task_type in task_types } 

#### 📊 작업 유형 (TaskType)

Agent Evaluator는 다음 작업 유형을 지원합니다:

  * `QA`: 질의응답 작업
  * `CODE_GENERATION`: 코드 생성 작업
  * `SUMMARIZATION`: 요약 작업
  * `TRANSLATION`: 번역 작업
  * `CLASSIFICATION`: 분류 작업
  * `DATA_ANALYSIS`: 데이터 분석 작업
  * `MULTI_AGENT`: 멀티 에이전트 협업
  * `TOOL_USE`: 도구 사용 작업

### get_benchmark_status() - 벤치마크 등급 판정

**목적** : TCR을 산업 벤치마크와 비교하여 등급 부여

**위치** : Lines 132-141

def get_benchmark_status(self, tcr: float) -> str: """Determine benchmark status based on TCR Args: tcr: Task Completion Rate (0-100) Returns: Benchmark classification string """ if tcr >= 95: return "Industry Leading" # 95% 이상 elif tcr >= 85: return "Good Performance" # 85-94% elif tcr >= 70: return "Acceptable" # 70-84% else: return "Needs Improvement" # 70% 미만

## 🔧 Helper 함수 및 알고리즘

### TaskResult 생성 Helper

**위치** : `agent_evaluator/helpers/taskresult_helpers.py`

from agent_evaluator import ( calculate_completion_score, create_taskresult ) # 방법 1: Completion Score 직접 계산 completion_score = calculate_completion_score( response=agent_response, expected_min_length=10, has_error=False, ground_truth=expected_answer ) # 방법 2: TaskResult 자동 생성 (권장) task_result = create_taskresult( task_id="task_001", task_type="QA", response=agent_response, ground_truth=expected_answer, start_time=start_time, end_time=end_time, input_text=user_query, context=context ) # completion_score, accuracy, success 등이 자동 계산됨

### Completion Score 계산 알고리즘

**Completion Score 결정 요인** :

  1. **작업 성공 여부** (success flag) 
     * True → 기본적으로 1.0
     * False → 0.0 또는 부분 점수
  2. **예상 vs 실제 산출물**
     * 모든 요구사항 충족 → 1.0
     * 일부 요구사항 충족 → 0.7-0.9
     * 거의 미충족 → 0.0-0.3
  3. **사용자 정의 평가**
     * 도메인별 평가 기준 적용
     * 비즈니스 로직 반영

### 🤖 create_taskresult() 자동 평가 알고리즘

**버전** : Agent Evaluator v0.5.0

**위치** : `agent_evaluator/helpers/taskresult_helpers.py` (Lines 410-513)

**목적** : Agent 실행 결과를 자동으로 분석하여 TaskResult를 생성하고 completion_score를 자동 계산

#### 📖 알고리즘 개요

`create_taskresult()`은 Agent의 실행 결과(응답, 실행 시간, 에러 여부 등)를 입력받아 **5단계 자동 평가 프로세스** 를 거쳐 완성된 TaskResult를 생성합니다. 이를 통해 사용자가 수동으로 점수를 매기지 않아도 객관적이고 일관된 평가가 가능합니다. 

**함수 시그니처** (agent_evaluator/helpers/taskresult_helpers.py:410-421):

def create_taskresult( task_id: str, question: str, response: str, ground_truth: str, execution_time: float, openai_response = None, langchain_result = None, has_error: bool = False, error_message: str = None, task_type: str = "qa" ) -> TaskResult: """Agent 실행 결과로부터 TaskResult 생성 (모든 필드 동적 계산)"""

#### 📐 5단계 자동 평가 프로세스

#### 1️⃣ Completion Score 자동 계산

**함수** : `calculate_completion_score()` (Lines 29-83)

**평가 기준** (순차적 검증):

  1. **에러 검증** : `has_error=True` → 즉시 0.0 반환
  2. **응답 존재 검증** : 응답이 없거나 공백만 있음 → 0.0 반환
  3. **길이 기반 평가** : 
     * 응답 길이 < 최소 기대 길이 → 부분 점수 (0.3 ~ 0.7)
     * 계산식: `max(0.3, min(0.7, response_length / expected_min_length))`
  4. **유사도 기반 평가** (ground_truth가 제공된 경우): 
     * 유사도 ≥ 0.8 → 1.0 (완벽한 답변)
     * 유사도 ≥ 0.5 → 0.7 (부분 정답)
     * 유사도 < 0.5 → 0.5 (낮은 정확도)
     * 유사도 계산: Jaccard Similarity 사용
  5. **기본 완료** : 위 조건 모두 통과 → 1.0 반환

**예시** :

# Case 1: 정상 응답, 충분한 길이 completion = calculate_completion_score( response="대한민국의 수도는 서울입니다", expected_min_length=5, has_error=False, ground_truth="서울" ) # → 1.0 (유사도 0.8 이상) # Case 2: 짧은 응답 completion = calculate_completion_score( response="서울", expected_min_length=100, has_error=False ) # → 0.3 (길이 부족) # Case 3: 에러 발생 completion = calculate_completion_score( response="", expected_min_length=10, has_error=True ) # → 0.0

#### 2️⃣ Accuracy Score 자동 계산

**함수** : `calculate_accuracy_score()` (Lines 90-152)

**위치** : taskresult_helpers.py Lines 473-478 (호출부), Lines 90-152 (구현부)

**실제 구현 코드** :

# 2. accuracy_score 동적 계산 (4가지 유사도 메트릭 조합) accuracy = calculate_accuracy_score( response=response, ground_truth=ground_truth, method="combined" ) 

**4가지 유사도 메트릭 가중 조합** :

메트릭 | 가중치 | 설명 | 함수 위치  
---|---|---|---  
**Token Overlap Ratio** | 40% | 두 텍스트 간 토큰 집합 교집합 비율 | Lines 164-176  
**Jaccard Similarity** | 30% | 집합 유사도 (교집합 / 합집합) | Lines 178-190  
**LCS Similarity** | 20% | 최장 공통 부분 수열 비율 (DP 알고리즘) | Lines 192-213  
**Character Similarity** | 10% | Levenshtein distance 기반 문자 유사도 | Lines 215-246  
  
**계산식 (Lines 134-141)** :

# 가중 평균 combined_score = ( token_score * 0.4 + # Token Overlap: 40% jaccard_score * 0.3 + # Jaccard: 30% lcs_score * 0.2 + # LCS: 20% char_score * 0.1 # Char: 10% ) return round(combined_score, 3) 

**텍스트 정규화** (normalize_text 함수, Lines 155-160):

def normalize_text(text: str) -> str: text = text.lower().strip() text = re.sub(r'[^\w\s가-힣]', '', text) # 특수문자 제거 (한글 유지) text = re.sub(r'\s+', ' ', text) # 다중 공백 → 단일 공백 return text 

  * 소문자 변환 및 공백 제거
  * 특수문자 제거 (한글, 영문, 숫자만 유지)
  * 다중 공백을 단일 공백으로 통일

##### 📊 Accuracy Score 계산 흐름

graph LR A[response & ground_truth] --> B[normalize_text] B --> C1[Token Overlap  
_token_overlap_ratio] B --> C2[Jaccard  
_jaccard_similarity] B --> C3[LCS  
_lcs_similarity] B --> C4[Char  
_char_similarity] C1 --> D[가중 평균  
40% + 30% + 20% + 10%] C2 --> D C3 --> D C4 --> D D --> E[round 3자리  
최종 Accuracy Score] style A fill:#667eea,color:#fff style B fill:#48bb78,color:#fff style C1 fill:#ed8936,color:#fff style C2 fill:#ed8936,color:#fff style C3 fill:#ed8936,color:#fff style C4 fill:#ed8936,color:#fff style D fill:#3182ce,color:#fff style E fill:#667eea,color:#fff 

#### 3️⃣ Tokens Used 자동 추출/추정

**위치** : taskresult_helpers.py Lines 480-491 (호출부)

**실제 구현 코드** :

# 3. tokens_used 동적 추출 (Lines 480-491) if openai_response: tokens = extract_tokens_from_openai(openai_response) elif langchain_result: tokens = extract_tokens_from_langchain(langchain_result) else: # 추정 tokens = { "input": estimate_tokens(question), "output": estimate_tokens(response), "total": estimate_tokens(question) + estimate_tokens(response) } 

**우선순위 기반 토큰 추출** :

  1. **OpenAI API 응답** (최우선) - Lines 257-281: 

def extract_tokens_from_openai(openai_response): try: return { "input": openai_response.usage.prompt_tokens, "output": openai_response.usage.completion_tokens, "total": openai_response.usage.total_tokens } except AttributeError: return {"input": 0, "output": 0, "total": 0} 

  2. **LangChain 결과** (2순위) - Lines 283-311: 

def extract_tokens_from_langchain(langchain_result): try: if isinstance(langchain_result, dict): llm_output = langchain_result.get("llm_output", {}) token_usage = llm_output.get("token_usage", {}) return { "input": token_usage.get("prompt_tokens", 0), "output": token_usage.get("completion_tokens", 0), "total": token_usage.get("total_tokens", 0) } except Exception: pass return {"input": 0, "output": 0, "total": 0} 

  3. **휴리스틱 추정** (폴백) - Lines 313-342: 

def estimate_tokens(text: str, model: str = "gpt-3.5-turbo") -> int: if not text: return 0 # 간단한 휴리스틱: 영문 4자 ≈ 1토큰, 한글 1.5자 ≈ 1토큰 char_count = len(text) # 한글 비율 추정 korean_chars = len(re.findall(r'[가-힣]', text)) english_chars = len(re.findall(r'[a-zA-Z]', text)) # 가중 평균 estimated_tokens = ( (korean_chars / 1.5) + (english_chars / 4) + (char_count - korean_chars - english_chars) / 3 ) return int(estimated_tokens) 

**추정 공식** :

     * 영문: 4자 ≈ 1토큰
     * 한글: 1.5자 ≈ 1토큰
     * 기타: 3자 ≈ 1토큰

**예시** :

text = "한국어와 영어가 섞인 텍스트입니다. This is mixed text." estimated = estimate_tokens(text) # 계산: 한글(18자/1.5) + 영문(20자/4) + 기타 = 약 18 토큰

##### 📊 Tokens 추출 흐름

graph TD A[Tokens Used 추출 시작] --> B{openai_response?} B -->|Yes| C[extract_tokens_from_openai] C --> C1[response.usage.prompt_tokens] C --> C2[response.usage.completion_tokens] C --> C3[response.usage.total_tokens] C1 --> D[tokens dict 생성] C2 --> D C3 --> D B -->|No| E{langchain_result?} E -->|Yes| F[extract_tokens_from_langchain] F --> F1[llm_output 추출] F1 --> F2[token_usage 추출] F2 --> F3{token_usage 있음?} F3 -->|Yes| F4[prompt_tokens, completion_tokens] F3 -->|No| F5[0, 0, 0 반환] F4 --> D F5 --> D E -->|No| G[estimate_tokens 호출] G --> G1[한글 문자 수 계산] G --> G2[영문 문자 수 계산] G --> G3[기타 문자 수 계산] G1 --> G4[가중 평균 계산] G2 --> G4 G3 --> G4 G4 --> G5[input: question 추정  
output: response 추정  
total: input + output] G5 --> D D[tokens dict 완성] style A fill:#667eea,color:#fff style B fill:#ecc94b,color:#000 style E fill:#ecc94b,color:#000 style C fill:#48bb78,color:#fff style F fill:#48bb78,color:#fff style G fill:#ed8936,color:#fff style D fill:#667eea,color:#fff 

#### 4️⃣ Tool Calls 자동 추출

**위치** : taskresult_helpers.py Lines 493-498 (호출부)

**실제 구현 코드** :

# 4. tool_calls 동적 추출 (Lines 493-498) tool_calls = [] if openai_response: tool_calls = extract_tool_calls_from_openai_functions(openai_response) elif langchain_result: tool_calls = extract_tool_calls_from_langchain(langchain_result) 

**프레임워크별 추출 방법** :

  1. **OpenAI Function Calling** \- Lines 379-404: 

def extract_tool_calls_from_openai_functions(openai_response): tool_calls = [] try: message = openai_response.choices[0].message if hasattr(message, 'tool_calls') and message.tool_calls: for tool_call in message.tool_calls: tool_calls.append({ "tool": tool_call.function.name, "arguments": tool_call.function.arguments }) except Exception: pass return tool_calls 

     * `message.tool_calls`에서 함수명, 인자 추출
     * 형식: `[{"tool": "function_name", "arguments": {...}}]`
  2. **LangChain Agent** \- Lines 348-377: 

def extract_tool_calls_from_langchain(langchain_result): tool_calls = [] try: if isinstance(langchain_result, dict): intermediate_steps = langchain_result.get("intermediate_steps", []) for step in intermediate_steps: if isinstance(step, tuple) and len(step) >= 2: action, output = step[0], step[1] tool_calls.append({ "tool": getattr(action, 'tool', 'unknown'), "input": getattr(action, 'tool_input', {}), "output": str(output) }) except Exception: pass return tool_calls 

     * `intermediate_steps`에서 action, output 추출
     * 형식: `[{"tool": "tool_name", "input": {...}, "output": "..."}]`

#### 5️⃣ TaskResult 생성 및 반환

**위치** : taskresult_helpers.py Lines 500-513

**최종 TaskResult 구성** (실제 구현 코드):

# 5. TaskResult 생성 (Lines 500-513) return TaskResult( task_id=task_id, task_type=getattr(TaskType, task_type.upper(), TaskType.QA).value, success=not has_error, # 에러 없으면 True completion_score=completion, # ✅ 1단계에서 자동 계산 accuracy_score=accuracy, # ✅ 2단계에서 자동 계산 (4가지 메트릭 조합) execution_time=execution_time, tokens_used=tokens, # ✅ 3단계에서 자동 추출 tool_calls=tool_calls, # ✅ 4단계에서 자동 추출 attempts=1, errors=[error_message] if error_message else [], timestamp=datetime.now() ) 

**핵심 포인트** :

  * `task_type`: 문자열을 TaskType enum으로 변환 (예: "qa" → TaskType.QA.value)
  * `success`: has_error의 반대값으로 자동 설정
  * `attempts`: 기본값 1로 고정 (재시도 추적은 상위 레이어에서 관리)
  * `timestamp`: 평가 시점을 자동 기록

#### 🎯 전체 흐름 다이어그램

graph TD A[create_taskresult 호출] --> A1[입력: task_id, question, response  
ground_truth, execution_time  
openai_response, langchain_result  
has_error, error_message, task_type] A1 --> B[1️⃣ Completion Score 계산] B --> B1[calculate_completion_score] B1 --> B2{has_error?} B2 -->|True| B3[return 0.0] B2 -->|False| B4{응답 존재?} B4 -->|No| B5[return 0.0] B4 -->|Yes| B6{길이 충분?} B6 -->|No| B7[부분 점수 0.3~0.7] B6 -->|Yes| B8{ground_truth 있음?} B8 -->|Yes| B9[유사도 계산  
≥0.8 → 1.0  
≥0.5 → 0.7  
<0.5 → 0.5] B8 -->|No| B10[return 1.0] B3 --> C B5 --> C B7 --> C B9 --> C B10 --> C C[2️⃣ Accuracy Score 계산] C --> C1[calculate_accuracy_score] C1 --> C2[텍스트 정규화] C2 --> C3[Token Overlap 40%] C2 --> C4[Jaccard 30%] C2 --> C5[LCS 20%] C2 --> C6[Char Similarity 10%] C3 --> C7[가중 평균] C4 --> C7 C5 --> C7 C6 --> C7 C7 --> D D[3️⃣ Tokens Used 추출] D --> D1{openai_response?} D1 -->|Yes| D2[extract_tokens_from_openai  
usage.prompt_tokens  
usage.completion_tokens] D1 -->|No| D3{langchain_result?} D3 -->|Yes| D4[extract_tokens_from_langchain  
llm_output.token_usage] D3 -->|No| D5[estimate_tokens  
영문 4자≈1토큰  
한글 1.5자≈1토큰] D2 --> E D4 --> E D5 --> E E[4️⃣ Tool Calls 추출] E --> E1{openai_response?} E1 -->|Yes| E2[extract_tool_calls_from_openai_functions  
message.tool_calls] E1 -->|No| E3{langchain_result?} E3 -->|Yes| E4[extract_tool_calls_from_langchain  
intermediate_steps] E3 -->|No| E5[tool_calls = 빈 리스트] E2 --> F E4 --> F E5 --> F F[5️⃣ TaskResult 생성] F --> F1[TaskResult 객체 생성] F1 --> F2[task_id, task_type 설정] F1 --> F3[success = not has_error] F1 --> F4[completion_score 할당] F1 --> F5[accuracy_score 할당] F1 --> F6[execution_time 할당] F1 --> F7[tokens_used 할당] F1 --> F8[tool_calls 할당] F1 --> F9[attempts = 1] F1 --> F10[errors 리스트 설정] F1 --> F11[timestamp = datetime.now] F2 --> G F3 --> G F4 --> G F5 --> G F6 --> G F7 --> G F8 --> G F9 --> G F10 --> G F11 --> G G[완성된 TaskResult 반환] style A fill:#667eea,color:#fff style B fill:#38a169,color:#fff style C fill:#38a169,color:#fff style D fill:#38a169,color:#fff style E fill:#38a169,color:#fff style F fill:#38a169,color:#fff style G fill:#667eea,color:#fff 

#### 💡 사용 예시

from agent_evaluator import create_taskresult import time # Agent 실행 start = time.time() response = agent.run("대한민국의 수도는?") execution_time = time.time() - start # TaskResult 자동 생성 (모든 점수 자동 계산) task_result = create_taskresult( task_id="task_001", question="대한민국의 수도는?", response=response, # Agent의 응답 ground_truth="서울", # 정답 execution_time=execution_time, openai_response=openai_response, # 선택: OpenAI API 응답 langchain_result=langchain_result, # 선택: LangChain 결과 has_error=False, task_type="qa" ) # 결과 확인 print(f"Completion Score: {task_result.completion_score}") # 자동 계산됨 print(f"Accuracy Score: {task_result.accuracy_score}") # 자동 계산됨 print(f"Tokens Used: {task_result.tokens_used}") # 자동 추출됨

#### ⚠️ 자동 평가의 장단점

##### ✅ 장점

  * **일관성** : 동일한 알고리즘으로 모든 작업 평가
  * **확장성** : 대량의 작업을 빠르게 평가 가능
  * **객관성** : 인간의 주관적 판단 배제
  * **재현성** : 동일 입력에 대해 동일 결과 보장

##### ⚠️ 한계

  * **의미 이해 부족** : 텍스트 유사도만으로 정확도 평가
  * **컨텍스트 무시** : 도메인 특화 지식 반영 어려움
  * **창의적 답변** : 정답과 다른 표현이지만 올바른 답변 저평가 가능

##### 💡 권장 사항

  * **하이브리드 접근** : 자동 평가 + 샘플링 수동 검증
  * **Ground Truth 고도화** : 여러 정답 패턴 제공
  * **커스텀 평가 함수** : 도메인 특화 평가 로직 구현
  * **LLM-as-Judge** : GPT-4를 활용한 고급 평가 (Level 2/3)

#### ⚠️ Completion Score 설정 시 주의사항

  * **일관성 유지** : 동일한 기준을 모든 작업에 일관되게 적용
  * **부분 성공 인정** : 0.7을 기준으로 부분 성공/실패 구분
  * **자동화 고려** : 가능한 자동 평가 로직 구현 권장
  * **Human-in-the-loop** : 중요 작업은 인간 검수 병행

## 🔌 Framework Integration 방법

### LangChain 통합

from langchain.agents import AgentExecutor from agent_evaluator.integrations import LangChainEvaluator from agent_evaluator import TaskType # 1. LangChain Agent 생성 agent = AgentExecutor.from_agent_and_tools( agent=agent, tools=tools, verbose=True ) # 2. Evaluator 래핑 evaluator = LangChainEvaluator( enable_transparency=True, enable_security_metrics=True ) # 3. 작업 실행 및 평가 result = evaluator.run_and_evaluate( agent=agent, task_input="Summarize the latest AI research", task_id="task_001", task_type=TaskType.SUMMARIZATION, expected_output="Summary with key findings", ground_truth="Expected summary content..." ) # 4. TCR 확인 tcr_metrics = evaluator.monitor.tcr_tracker.calculate_tcr() print(f"TCR: {tcr_metrics['tcr']}%") print(f"Full Success: {tcr_metrics['full_success']}") print(f"Partial Success: {tcr_metrics['partial_success']}") 

### CrewAI 통합

from crewai import Agent, Task, Crew from agent_evaluator.integrations import CrewAIEvaluator # 1. CrewAI 설정 researcher = Agent( role='Researcher', goal='Research AI trends', tools=[search_tool] ) task = Task( description='Research latest AI developments', agent=researcher ) crew = Crew( agents=[researcher], tasks=[task] ) # 2. Evaluator 통합 evaluator = CrewAIEvaluator( enable_transparency=True ) # 3. 실행 및 평가 result = evaluator.run_and_evaluate( crew=crew, task_id="crew_task_001", task_type=TaskType.DATA_ANALYSIS ) # 4. 타입별 TCR 확인 tcr_by_type = evaluator.monitor.tcr_tracker.get_tcr_by_type() for task_type, metrics in tcr_by_type.items(): print(f"{task_type}: TCR = {metrics['tcr']}%") 

### LangGraph 통합

from langgraph.graph import StateGraph from agent_evaluator.integrations import LangGraphEvaluator # 1. LangGraph 정의 workflow = StateGraph(AgentState) workflow.add_node("research", research_node) workflow.add_node("analyze", analyze_node) workflow.add_edge("research", "analyze") graph = workflow.compile() # 2. Evaluator 통합 evaluator = LangGraphEvaluator( enable_transparency=True ) # 3. 실행 및 평가 result = evaluator.run_and_evaluate( graph=graph, initial_state={"query": "AI trends"}, task_id="graph_task_001", task_type=TaskType.MULTI_AGENT ) # 4. 벤치마크 상태 확인 tcr = evaluator.monitor.tcr_tracker.calculate_tcr()['tcr'] status = evaluator.monitor.tcr_tracker.get_benchmark_status(tcr) print(f"Benchmark Status: {status}") 

### AutoGen 통합

from autogen import AssistantAgent, UserProxyAgent from agent_evaluator.integrations import AutoGenEvaluator # 1. AutoGen 설정 assistant = AssistantAgent( name="assistant", llm_config={"model": "gpt-4"} ) user_proxy = UserProxyAgent( name="user", human_input_mode="NEVER" ) # 2. Evaluator 통합 evaluator = AutoGenEvaluator( enable_transparency=True ) # 3. 대화 실행 및 평가 result = evaluator.run_and_evaluate( assistant=assistant, user_proxy=user_proxy, message="Analyze the stock market", task_id="autogen_task_001", task_type=TaskType.DATA_ANALYSIS ) # 4. 전체 TCR 보고서 report = evaluator.monitor.generate_report() print(report['tcr']) 

## 💻 실제 구현 코드 예제

### 기본 사용 예제

from agent_evaluator import PerformanceMonitor, TaskType from datetime import datetime # 1. 모니터 초기화 monitor = PerformanceMonitor( enable_transparency=True ) # 2. 작업 실행 (예: AI Agent 작업) start_time = datetime.now() # ... AI Agent 실행 ... agent_response = "AI generated response" ground_truth = "Expected correct answer" end_time = datetime.now() # 3. 작업 기록 monitor.record_task( task_id="task_001", task_type=TaskType.QA, success=True, latency=(end_time - start_time).total_seconds(), completion_score=1.0, # Full success expected_output="Answer to user question", actual_output=agent_response, ground_truth=ground_truth ) # 4. TCR 계산 tcr_metrics = monitor.tcr_tracker.calculate_tcr() print("=== TCR Metrics ===") print(f"Overall TCR: {tcr_metrics['tcr']}%") print(f"Total Tasks: {tcr_metrics['total_tasks']}") print(f"Full Success: {tcr_metrics['full_success']}") print(f"Partial Success: {tcr_metrics['partial_success']}") print(f"Failures: {tcr_metrics['failures']}") print(f"Success Rate: {tcr_metrics['success_rate']}%") 

### 다중 작업 평가 예제

from agent_evaluator import PerformanceMonitor, TaskType monitor = PerformanceMonitor() # 시나리오: 10개 QA 작업 평가 test_cases = [ {"id": "qa_001", "score": 1.0, "type": TaskType.QA}, {"id": "qa_002", "score": 0.8, "type": TaskType.QA}, {"id": "qa_003", "score": 1.0, "type": TaskType.QA}, {"id": "qa_004", "score": 0.5, "type": TaskType.QA}, {"id": "qa_005", "score": 0.9, "type": TaskType.QA}, {"id": "code_001", "score": 1.0, "type": TaskType.CODE_GENERATION}, {"id": "code_002", "score": 0.7, "type": TaskType.CODE_GENERATION}, {"id": "code_003", "score": 0.3, "type": TaskType.CODE_GENERATION}, {"id": "sum_001", "score": 0.95, "type": TaskType.SUMMARIZATION}, {"id": "sum_002", "score": 0.85, "type": TaskType.SUMMARIZATION} ] # 작업 기록 for case in test_cases: monitor.record_task( task_id=case["id"], task_type=case["type"], success=case["score"] >= 0.7, latency=1.5, completion_score=case["score"], expected_output="Expected", actual_output="Actual" ) # 전체 TCR overall_tcr = monitor.tcr_tracker.calculate_tcr() print(f"\n전체 TCR: {overall_tcr['tcr']}%") # 타입별 TCR print("\n=== 작업 유형별 TCR ===") tcr_by_type = monitor.tcr_tracker.get_tcr_by_type() for task_type, metrics in tcr_by_type.items(): print(f"\n{task_type}:") print(f" TCR: {metrics['tcr']}%") print(f" Total: {metrics['total_tasks']}") print(f" Full Success: {metrics['full_success']}") print(f" Partial: {metrics['partial_success']}") print(f" Failures: {metrics['failures']}") # 벤치마크 상태 status = monitor.tcr_tracker.get_benchmark_status(overall_tcr['tcr']) print(f"\nBenchmark Status: {status}") 

### 실시간 모니터링 예제

import time from agent_evaluator import PerformanceMonitor, TaskType def monitor_agent_performance(monitor, num_tasks=100): """실시간 Agent 성능 모니터링""" print("Starting real-time monitoring...") for i in range(num_tasks): # 시뮬레이션: Agent 작업 실행 task_id = f"task_{i:03d}" # Random completion score (실제로는 Agent 결과 평가) import random completion_score = random.choice([1.0, 0.9, 0.8, 0.7, 0.5, 0.3]) monitor.record_task( task_id=task_id, task_type=TaskType.QA, success=completion_score >= 0.7, latency=random.uniform(0.5, 3.0), completion_score=completion_score, expected_output="Expected", actual_output="Actual" ) # 10개마다 중간 리포트 if (i + 1) % 10 == 0: tcr = monitor.tcr_tracker.calculate_tcr() print(f"\n[{i+1}/{num_tasks}] Current TCR: {tcr['tcr']}%") print(f" Full Success: {tcr['full_success']}") print(f" Partial: {tcr['partial_success']}") print(f" Failures: {tcr['failures']}") time.sleep(0.1) # 실제로는 Agent 실행 시간 # 최종 리포트 print("\n" + "="*50) print("FINAL REPORT") print("="*50) final_tcr = monitor.tcr_tracker.calculate_tcr() status = monitor.tcr_tracker.get_benchmark_status(final_tcr['tcr']) print(f"Final TCR: {final_tcr['tcr']}%") print(f"Benchmark Status: {status}") print(f"Success Rate: {final_tcr['success_rate']}%") # 실행 monitor = PerformanceMonitor() monitor_agent_performance(monitor, num_tasks=50) 

## ✨ Best Practices

### Production 환경 설정

from agent_evaluator import PerformanceMonitor import os # Production 모니터 설정 monitor = PerformanceMonitor( enable_transparency=True, # 투명성 로깅 활성화 enable_hallucination_detection=True, # 환각 감지 enable_security_metrics=True, # 보안 메트릭 output_dir="/var/log/agent_evaluator" # 로그 디렉토리 ) # TCR 목표 설정 TARGET_TCR = 90.0 ACCEPTABLE_TCR = 80.0 def check_tcr_health(monitor): """TCR 건강도 체크""" tcr = monitor.tcr_tracker.calculate_tcr()['tcr'] if tcr < ACCEPTABLE_TCR: # Alert: TCR이 허용 수준 이하 send_alert(f"TCR below acceptable level: {tcr}%") elif tcr < TARGET_TCR: # Warning: TCR이 목표치 미달 log_warning(f"TCR below target: {tcr}%") else: # OK: TCR 정상 log_info(f"TCR healthy: {tcr}%") 

### A/B 테스트

from agent_evaluator import PerformanceMonitor # A/B 테스트: 두 Agent 버전 비교 monitor_a = PerformanceMonitor() # Version A monitor_b = PerformanceMonitor() # Version B # 동일한 작업을 두 버전에 실행 for task in test_tasks: # Version A result_a = agent_v_a.run(task) monitor_a.record_task( task_id=task["id"] + "_a", task_type=task["type"], success=evaluate(result_a), completion_score=score(result_a), latency=result_a.latency ) # Version B result_b = agent_v_b.run(task) monitor_b.record_task( task_id=task["id"] + "_b", task_type=task["type"], success=evaluate(result_b), completion_score=score(result_b), latency=result_b.latency ) # TCR 비교 tcr_a = monitor_a.tcr_tracker.calculate_tcr()['tcr'] tcr_b = monitor_b.tcr_tracker.calculate_tcr()['tcr'] print(f"Version A TCR: {tcr_a}%") print(f"Version B TCR: {tcr_b}%") print(f"Improvement: {tcr_b - tcr_a:+.2f}%") # 통계적 유의성 검정 (선택 사항) from scipy.stats import ttest_ind success_a = [t.completion_score for t in monitor_a.tcr_tracker.tasks] success_b = [t.completion_score for t in monitor_b.tcr_tracker.tasks] t_stat, p_value = ttest_ind(success_a, success_b) print(f"Statistical significance (p-value): {p_value}") 

### TCR 측정 권장사항

#### ✅ TCR 측정 Best Practices

  1. **일관된 평가 기준**
     * 모든 작업에 동일한 completion_score 기준 적용
     * 평가 가이드라인 문서화
  2. **충분한 샘플 크기**
     * 최소 30개 이상의 작업으로 TCR 계산
     * 통계적 신뢰도 확보
  3. **작업 유형별 분석**
     * QA, 코드 생성 등 유형별로 TCR 추적
     * 유형별 특성 고려한 개선
  4. **시계열 추적**
     * 시간에 따른 TCR 변화 모니터링
     * 트렌드 분석 및 예측
  5. **실시간 알림**
     * TCR 급락 시 즉시 알림
     * 자동화된 대응 프로세스 구축
  6. **근본 원인 분석**
     * TCR 저하 시 실패 작업 분석
     * 패턴 파악 및 시스템 개선

#### ⚠️ 주의사항

  * **TCR만으로는 부족** : Latency, Cost, Quality 등 다른 메트릭과 함께 평가
  * **게임 방지** : 쉬운 작업만 선택하여 TCR 부풀리기 방지
  * **Context 고려** : 작업 난이도, 도메인 특성 반영
  * **사용자 만족도** : TCR과 실제 사용자 만족도 상관관계 확인

## 🤖 평가 데이터 자동 처리 방안

**실제 과제 적용 시** 수백~수천 개의 작업을 평가해야 하는 경우, 평가 데이터를 최대한 자동으로 처리하는 것이 필수적입니다.  
이 섹션에서는 TCR 평가를 위한 **5가지 자동화 전략** 을 제공합니다. 

### 자동화 레벨 개요

레벨 | 자동화 범위 | 수작업 필요 | 적용 시나리오  
---|---|---|---  
**Level 1** | 예외 기반 자동 판정 | 초기 설정만 | 에러 추적 시스템  
**Level 2** | 반환값 구조 검증 | 스키마 정의 | API/함수 호출  
**Level 3** | 규칙 기반 자동 채점 | 규칙 작성 | 명확한 기준 있는 작업  
**Level 4** | LLM-as-Judge | 프롬프트 작성 | 복잡한 평가 기준  
**Level 5** | Golden Dataset 기반 | Dataset 구축 | 벤치마크 평가  
  
### 🔧 Level 1: 예외 기반 자동 판정 (완전 자동)

#### ✅ 가장 간단한 자동화

**원리** : Agent 실행 중 예외 발생 여부로 성공/실패 자동 판정

**장점** : 설정 불필요, 완전 자동

**한계** : 예외 없이 잘못된 결과 반환 시 탐지 불가

from agent_evaluator import PerformanceMonitor, TaskType import traceback monitor = PerformanceMonitor() # 작업 리스트 tasks = [ {"task_id": "task_001", "query": "한국의 수도는?"}, {"task_id": "task_002", "query": "파이썬으로 피보나치 구현"}, {"task_id": "task_003", "query": "데이터 분석 리포트 작성"} ] # 자동 평가 루프 for task in tasks: try: # Agent 실행 result = your_agent.run(task["query"]) # 예외 없음 = 성공 monitor.record_task( task_id=task["task_id"], task_type=TaskType.QA, success=True, ← 자동 판정 latency=result.execution_time, completion_score=1.0 ← 자동 설정 ) print(f"✅ {task['task_id']}: Success") except Exception as e: # 예외 발생 = 실패 monitor.record_task( task_id=task["task_id"], task_type=TaskType.QA, success=False, ← 자동 판정 latency=0.0, completion_score=0.0, ← 자동 설정 error_message=str(e) ) print(f"❌ {task['task_id']}: Failed - {e}") # TCR 자동 계산 tcr_stats = monitor.tcr_tracker.get_metrics() print(f"\n자동 평가 완료!") print(f"TCR: {tcr_stats['weighted_tcr']:.2f}%") print(f"성공: {tcr_stats['successful_tasks']}개") print(f"실패: {tcr_stats['failed_tasks']}개") 

### 🔍 Level 2: 반환값 구조 검증 (구조 자동 검증)

#### ✅ 반환값 형식 검증

**원리** : Agent 응답의 구조/타입/필수 필드 자동 검증

**장점** : JSON/Dict 구조화된 응답에 효과적

**한계** : 구조는 맞지만 내용이 틀린 경우 탐지 불가

from agent_evaluator import PerformanceMonitor, TaskType from typing import Dict, Any def validate_response_structure(response: Any, schema: Dict) -> float: """ 응답 구조 검증 및 자동 채점 Returns: 0.0 (실패), 0.7 (부분 성공), 1.0 (완전 성공) """ if not isinstance(response, dict): return 0.0 required_fields = schema.get("required", []) optional_fields = schema.get("optional", []) # 필수 필드 체크 missing_required = [f for f in required_fields if f not in response] if missing_required: return 0.0 # 필수 필드 누락 = 실패 # 선택 필드 체크 present_optional = [f for f in optional_fields if f in response] if len(present_optional) == len(optional_fields): return 1.0 # 모든 필드 존재 = 완전 성공 else: return 0.7 # 필수만 있음 = 부분 성공 # 사용 예시 monitor = PerformanceMonitor() # 응답 스키마 정의 (한 번만) response_schema = { "required": ["answer", "confidence"], "optional": ["sources", "explanation"] } tasks = [ "질문 1", "질문 2", "질문 3" ] for i, task in enumerate(tasks): response = your_agent.run(task) # Dict 반환 가정 # 자동 채점 completion_score = validate_response_structure(response, response_schema) monitor.record_task( task_id=f"task_{i:03d}", task_type=TaskType.QA, success=completion_score > 0.0, latency=1.0, completion_score=completion_score ← 자동 계산 ) # 자동 평가 완료 tcr_stats = monitor.tcr_tracker.get_metrics() print(f"TCR: {tcr_stats['weighted_tcr']:.2f}%") 

### 📐 Level 3: 규칙 기반 자동 채점 (규칙 엔진)

#### ✅ 명확한 기준으로 자동 채점

**원리** : 정의된 규칙에 따라 응답 자동 평가

**장점** : 객관적, 일관적, 빠른 속도

**한계** : 규칙 작성 필요, 복잡한 평가 어려움

from agent_evaluator import PerformanceMonitor, TaskType import re class RuleBasedScorer: """규칙 기반 자동 채점 엔진""" def __init__(self): self.rules = [] def add_rule(self, rule_name: str, check_func, weight: float): """채점 규칙 추가""" self.rules.append({ "name": rule_name, "check": check_func, "weight": weight }) def score(self, response: str) -> float: """자동 채점 실행""" total_score = 0.0 total_weight = sum(r["weight"] for r in self.rules) for rule in self.rules: if rule["check"](response): total_score += rule["weight"] return total_score / total_weight if total_weight > 0 else 0.0 # 사용 예시: QA 작업 자동 채점 scorer = RuleBasedScorer() # 규칙 정의 (한 번만) scorer.add_rule( "응답 길이", lambda r: len(r.split()) >= 10, # 10단어 이상 weight=0.2 ) scorer.add_rule( "숫자 포함", lambda r: bool(re.search(r'\d+', r)), # 숫자 포함 weight=0.3 ) scorer.add_rule( "키워드 포함", lambda r: any(kw in r.lower() for kw in ["서울", "인구"]), weight=0.5 ) # 자동 평가 monitor = PerformanceMonitor() tasks = ["서울의 인구는?", "파이썬은 언제 만들어졌나?"] for i, task in enumerate(tasks): response = your_agent.run(task) # 규칙 기반 자동 채점 completion_score = scorer.score(response) monitor.record_task( task_id=f"task_{i:03d}", task_type=TaskType.QA, success=completion_score > 0.5, latency=1.0, completion_score=completion_score ← 자동 계산 ) tcr_stats = monitor.tcr_tracker.get_metrics() print(f"자동 채점 완료! TCR: {tcr_stats['weighted_tcr']:.2f}%") 

### 🤖 Level 4: LLM-as-Judge (AI 기반 자동 평가)

#### ✅ 가장 강력한 자동화

**원리** : LLM이 응답 품질을 자동 평가

**장점** : 복잡한 평가 가능, 사람 수준 판단

**한계** : API 비용, 속도 저하

from agent_evaluator import PerformanceMonitor, TaskType from openai import OpenAI class LLMJudge: """LLM 기반 자동 평가자""" def __init__(self, api_key: str): self.client = OpenAI(api_key=api_key) def evaluate(self, query: str, response: str) -> float: """ LLM이 응답 품질을 0.0~1.0으로 평가 Returns: 0.0 (전혀 답변 못함) ~ 1.0 (완벽한 답변) """ evaluation_prompt = f""" 다음 질문과 응답을 평가하고 점수를 매기세요. 질문: {query} 응답: {response} 평가 기준: 1\. 질문에 대한 직접적 답변 여부 2\. 답변의 정확성 3\. 답변의 완성도 4\. 답변의 명확성 0.0 (완전 실패) ~ 1.0 (완벽) 사이의 점수만 출력하세요. 예시: 0.85 점수:""" completion = self.client.chat.completions.create( model="gpt-4", messages=[ {"role": "system", "content": "당신은 공정한 평가자입니다."}, {"role": "user", "content": evaluation_prompt} ], temperature=0.0 ) try: score_text = completion.choices[0].message.content.strip() score = float(score_text) return max(0.0, min(1.0, score)) # 0~1 범위로 제한 except: return 0.5 # 파싱 실패 시 중간 점수 # 사용 예시 judge = LLMJudge(api_key="your-openai-key") monitor = PerformanceMonitor() tasks = [ {"query": "서울의 인구는?"}, {"query": "Python은 언제 만들어졌나?"} ] for i, task in enumerate(tasks): # Agent 실행 response = your_agent.run(task["query"]) # LLM-as-Judge 자동 평가 completion_score = judge.evaluate(task["query"], response) print(f"Task {i}: Score = {completion_score:.2f}") monitor.record_task( task_id=f"task_{i:03d}", task_type=TaskType.QA, success=completion_score > 0.5, latency=1.0, completion_score=completion_score ← LLM이 자동 채점 ) tcr_stats = monitor.tcr_tracker.get_metrics() print(f"\nLLM 자동 평가 완료! TCR: {tcr_stats['weighted_tcr']:.2f}%") 

### 📊 Level 5: Golden Dataset 기반 자동 평가 (벤치마크)

#### ✅ 가장 체계적인 자동화

**원리** : 미리 준비된 Golden Dataset으로 자동 비교

**장점** : 재현 가능, 벤치마크 가능, 일관성

**한계** : 초기 Dataset 구축 시간

import json from pathlib import Path from agent_evaluator import PerformanceMonitor, TaskType from agent_evaluator import create_taskresult # 1. Golden Dataset 로드 dataset_path = Path("Evaluator_Examples/Dashboard/data/golden_datasets/sample_auto_eval_dataset.json") with open(dataset_path, 'r', encoding='utf-8') as f: golden_data = json.load(f) monitor = PerformanceMonitor() print(f"✅ Golden Dataset 로드: {golden_data['total_qa_pairs']}개 작업") # 2. 자동 평가 실행 for qa_pair in golden_data["qa_pairs"]: print(f"평가 중: {qa_pair['qa_id']}") # Agent 실행 agent_response = your_agent.run(qa_pair["question"]) # TaskResult 자동 생성 (TCR 자동 계산) task_result = create_taskresult( task_id=qa_pair["qa_id"], question=qa_pair["question"], response=agent_response, ground_truth=qa_pair["ground_truth"], execution_time=1.0, task_type=qa_pair["task_type"] ) # 자동 기록 (completion_score 자동 계산됨) monitor.tcr_tracker.add_task(task_result) # 3. 결과 확인 tcr_stats = monitor.tcr_tracker.get_metrics() print(f"\n{'='*60}") print(f"자동 평가 완료!") print(f"{'='*60}") print(f"TCR: {tcr_stats['weighted_tcr']:.2f}%") print(f"성공: {tcr_stats['successful_tasks']}개") print(f"부분 성공: {tcr_stats['partial_success_tasks']}개") print(f"실패: {tcr_stats['failed_tasks']}개") # 4. Dashboard 저장 from agent_evaluator.utils.dashboard_integration import save_to_dashboard result_path = save_to_dashboard(monitor, f"tcr_eval_{golden_data['dataset_id']}.json") print(f"\n결과 저장: {result_path}") 

### 📈 자동화 레벨 선택 가이드

**🎯 상황별 추천 레벨**  
  
**개발/테스트 단계** | → Level 1-2 (빠른 피드백)  
---|---  
**명확한 평가 기준** | → Level 3 (규칙 기반)  
**복잡한 평가 필요** | → Level 4 (LLM-as-Judge)  
**벤치마크/재현성** | → Level 5 (Golden Dataset)  
**프로덕션 배포** | → 하이브리드 (Level 1+2+3)  
**대량 평가 (1000+ 작업)** | → Level 5 필수  
  
### ⚡ 성능 최적화 팁

**✅ 자동화 성능 향상 방법**

  1. **병렬 처리**
     * 여러 작업을 동시에 평가 (ThreadPoolExecutor)
     * 10배 이상 속도 향상 가능
  2. **캐싱**
     * 동일한 query는 캐시된 결과 재사용
     * LLM 호출 횟수 감소
  3. **배치 처리**
     * 100개씩 묶어서 평가
     * 중간 결과 저장으로 재시작 가능
  4. **점진적 평가**
     * Level 1 → 2 → 3 순서로 단계적 평가
     * 실패 시 즉시 중단으로 시간 절약

from concurrent.futures import ThreadPoolExecutor from agent_evaluator import PerformanceMonitor def evaluate_single_task(task): """단일 작업 평가 함수""" try: response = your_agent.run(task["query"]) return { "task_id": task["task_id"], "success": True, "completion_score": 1.0 } except: return { "task_id": task["task_id"], "success": False, "completion_score": 0.0 } # 병렬 평가 (10배 빠름) monitor = PerformanceMonitor() tasks = [...] # 1000개 작업 with ThreadPoolExecutor(max_workers=10) as executor: results = list(executor.map(evaluate_single_task, tasks)) # 결과 기록 for result in results: monitor.record_task( task_id=result["task_id"], success=result["success"], completion_score=result["completion_score"] ) print(f"병렬 평가 완료: {len(tasks)}개 작업") 

#### ⚠️ 자동화 사용 시 주의사항

  * **검증 필수** : 자동 평가 결과를 샘플링하여 수동 검증
  * **에지 케이스** : 극단적 케이스는 수동 확인
  * **LLM 비용** : Level 4 사용 시 API 비용 모니터링
  * **규칙 유지보수** : Level 3 규칙은 주기적 업데이트
  * **과적합 방지** : 특정 데이터셋에만 맞춘 규칙 주의

## 🔗 관련 메트릭

관련 지표 | 관계 | 문서 링크  
---|---|---  
**Accuracy** | TCR의 품질 측면 보완 | [Accuracy 가이드](<02_ACCURACY.html>)  
**Quality Score** | 완료된 작업의 품질 평가 | [Quality Score 가이드](<04_QUALITY_SCORE.html>)  
**Latency** | TCR과 속도 간 trade-off 분석 | [Latency 가이드](<05_LATENCY.html>)  
**Cost** | TCR과 비용 간 효율성 분석 | [Cost 가이드](<06_COST.html>)  
**Retry Count** | TCR 달성을 위한 재시도 횟수 | [Retry Count 가이드](<07_RETRY_COUNT.html>)  
  
## 📋 요약

**Task Completion Rate (TCR)** 는 AI 에이전트의 성능을 평가하는 가장 기본적이고 중요한 지표입니다. 

  * **가중 평균 계산** : 각 작업의 completion_score를 합산하여 평균 산출
  * **3단계 평가** : Full Success (1.0), Partial Success (0.7), Failure (0.0)
  * **작업 유형별 분석** : QA, Code Generation 등 유형별 TCR 추적
  * **벤치마크 등급** : Industry Leading (95%+), Good (85-94%), Acceptable (70-84%), Needs Improvement (<70%)
  * **프레임워크 통합** : LangChain, CrewAI, LangGraph, AutoGen 지원

  
Layer 1 네이티브 메트릭으로 외부 의존성 없이 실시간 성능 추적이 가능하며, 프로덕션 AI 시스템의 신뢰성과 품질 보장에 필수적입니다.
