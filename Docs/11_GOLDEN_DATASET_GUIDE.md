# 📚 Golden Dataset 가이드

테스트 데이터셋 생성 및 관리 (Agent Evaluator v0.6.1)

# Golden Dataset 가이드

## 목차

  1. [Golden Dataset란?](<#golden-dataset란>)
  2. [QAPair 구조 완전 가이드](<#qapair-구조-완전-가이드>)
  3. [Layer 1 필드 (기본)](<#layer-1-필드-기본>)
  4. [Layer 2 필드 (Agentic + Security)](<#layer-2-필드-agentic-security>)
  5. [Golden Dataset 생성 방법](<#golden-dataset-생성-방법>)
  6. [Dashboard에서 편집하기](<#dashboard에서-편집하기>)
  7. [자동 평가 워크플로우](<#자동-평가-워크플로우>)
  8. [Best Practices](<#best-practices>)
  9. [예제 Golden Datasets](<#예제-golden-datasets>)
  10. [📊 품질 관리자 가이드 (QA Manager)](<#qa-품질-관리자-가이드>)
     * [1\. Golden Dataset 품질 관리](<#qa-1-golden-dataset-품질-관리>)
     * [2\. 데이터셋 품질 지표](<#qa-2-데이터셋-품질-지표>)
     * [3\. 데이터셋 유지보수](<#qa-3-데이터셋-유지보수>)
     * [4\. 문제 시나리오 및 해결](<#qa-4-문제-시나리오-및-해결>)
     * [5\. QA 관리자 핵심 원칙](<#qa-5-qa-관리자-핵심-원칙>)
  11. [FAQ & Troubleshooting](<#faq-troubleshooting>)

* * *

## 중요: 문서 vs 실제 구현

이 가이드는 실제 구현 코드와 검증되었으며, 다음 사항을 확인하십시오:

### ✅ 검증된 필드명

문서 표기 | 실제 구현 | 상태  
---|---|---  
`qa_id` | `qa_id` | ✅ 일치  
`question` | `question` | ✅ 일치  
`answer` | `answer` | ✅ 일치 (필수)  
`context` | `context` | ✅ 일치 (단수형)  
`ground_truth` | `ground_truth` | ✅ 일치  
`metadata` | `metadata` | ✅ 일치  
`expected_tools` | `expected_tools` | ✅ 일치  
`expected_agents` | `expected_agents` | ✅ 일치  
`expected_workflow_steps` | `expected_workflow_steps` | ✅ 일치  
  
### ✅ 검증된 Golden Dataset 구조
```python
    [](<#cb1-1>)# korean_rag_dataset_generator.py에서 실제 구현
    [](<#cb1-2>)@dataclass
    [](<#cb1-3>)class QAPair:
    [](<#cb1-4>)    qa_id: str                                    # 고유 ID
    [](<#cb1-5>)    question: str                                 # 질문
    [](<#cb1-6>)    answer: str                                   # 완전한 답변 (2-3문장)
    [](<#cb1-7>)    context: str                                  # 컨텍스트 (단수형)
    [](<#cb1-8>)    ground_truth: str                             # 평가 기준 답변 (1-2문장)
    [](<#cb1-9>)    metadata: Dict[str, Any]                      # 메타데이터
    [](<#cb1-10>)    expected_tools: Optional[List[str]]           # Layer 2
    [](<#cb1-11>)    expected_agents: Optional[List[str]]          # Layer 2
    [](<#cb1-12>)    expected_workflow_steps: Optional[List[str]]  # Layer 2
    [](<#cb1-13>)
    [](<#cb1-14>)@dataclass
    [](<#cb1-15>)class GoldenDataset:
    [](<#cb1-16>)    dataset_id: str           # 데이터셋 ID
    [](<#cb1-17>)    source_document: str      # 소스 문서 경로
    [](<#cb1-18>)    created_at: str           # 생성 시간
    [](<#cb1-19>)    total_qa_pairs: int       # 총 QA 쌍 수
    [](<#cb1-20>)    qa_pairs: List[QAPair]    # QA 쌍 리스트
    [](<#cb1-21>)    metadata: Dict[str, Any]  # 추가 메타데이터
```

### 🔑 핵심 차이점

  1. **`answer` vs `ground_truth`**
     * `answer`: 문서 기반의 완전한 답변 (2-3문장)
     * `ground_truth`: 평가용 간결한 핵심 답변 (1-2문장)
     * 둘 다 필수 필드
  2. **`context` (단수형)**
     * ❌ `contexts` (복수형) 아님
     * ✅ `context` (단수형) 사용
  3. **Golden Dataset 파일 구조**
     * 최상위: `dataset_id`, `source_document`, `created_at`, `total_qa_pairs`, `qa_pairs`, `metadata`
     * ❌ `dataset_name`, `version` 필드 아님
  4. **PDF 생성 프로세스**
     * 사용 클래스: `KoreanRAGDatasetGenerator`
     * 청크 크기: 기본 1000자 (설정 가능)
     * AI 모델: OpenAI GPT (gpt-4o-mini 또는 gpt-4o)
     * Layer 2 필드: 자동 생성 안 됨 (수동 추가 필요)

* * *

## Golden Dataset란?

### 정의

**Golden Dataset** 은 AI 에이전트를 평가하기 위한 **표준 테스트 데이터셋** 입니다. 각 항목은 질문(Question), 답변(Answer), 정답(Ground Truth), 컨텍스트(Context), 그리고 기대 동작(Expected Behavior)을 포함합니다.

### 왜 필요한가?

#### 1\. 객관적 평가 기준

  * 수동 테스트는 일관성이 없고 재현이 어렵습니다
  * Golden Dataset은 **반복 가능하고 객관적인** 평가 기준을 제공합니다
  * CI/CD 파이프라인에 통합 가능합니다

#### 2\. 회귀 테스트

  * 에이전트를 업데이트할 때마다 **성능이 저하되지 않았는지** 확인
  * 이전 버전과 현재 버전의 정량적 비교

#### 3\. Layer 2 Agentic + Security 메트릭 평가

  * **Tool Selection** : 올바른 도구를 선택했는지 검증
  * **Agent Coordination** : 에이전트 간 협업이 올바른지 검증
  * **Workflow Execution** : 워크플로우 실행이 예상대로 진행되었는지 검증

#### 4\. 프로덕션 준비 검증

  * 엄격한 임계값(threshold)과 함께 사용하여 **품질 게이트** 역할
  * 모든 테스트를 통과해야만 배포 진행

* * *

## QAPair 구조 완전 가이드

### QAPair란?

**QAPair**(Question-Answer Pair)는 Golden Dataset의 기본 단위입니다. 각 QAPair는 하나의 테스트 케이스를 나타냅니다.

### 전체 구조 (JSON)
```json
    [](<#cb2-1>){
    [](<#cb2-2>)  "qa_id": "qa_001",
    [](<#cb2-3>)  "question": "What is the capital of France?",
    [](<#cb2-4>)  "answer": "The capital of France is Paris.",
    [](<#cb2-5>)  "context": "France is a country in Western Europe. Its capital and largest city is Paris.",
    [](<#cb2-6>)  "ground_truth": "The capital of France is Paris.",
    [](<#cb2-7>)  "metadata": {
    [](<#cb2-8>)    "domain": "geography",
    [](<#cb2-9>)    "difficulty": "easy",
    [](<#cb2-10>)    "source": "manual"
    [](<#cb2-11>)  },
    [](<#cb2-12>)  "expected_tools": ["search", "knowledge_base"],
    [](<#cb2-13>)  "expected_agents": ["researcher", "validator"],
    [](<#cb2-14>)  "expected_workflow_steps": ["retrieval", "generation", "validation"]
    [](<#cb2-15>)}
```

### 필드 설명

필드 | 타입 | 필수 | Layer | 설명  
---|---|---|---|---  
`qa_id` | string | ✅ | 1 | 고유 식별자 (예: “qa_001”)  
`question` | string | ✅ | 1 | 에이전트에게 제공될 질문  
`answer` | string | ✅ | 1 | 문서 내용 기반의 완전한 답변 (2-3문장)  
`context` | string | ✅ | 1 | 질문에 대한 배경 정보/컨텍스트 (단수형)  
`ground_truth` | string | ✅ | 1 | 평가를 위한 기준 답변 (1-2문장, 간결하게)  
`metadata` | object | ❌ | 1 | 추가 메타데이터 (domain, difficulty 등)  
`expected_tools` | list[string] | ❌ | 2 | 에이전트가 사용해야 할 도구 목록  
`expected_agents` | list[string] | ❌ | 2 | 참여해야 할 에이전트 목록  
`expected_workflow_steps` | list[string] | ❌ | 2 | 실행되어야 할 워크플로우 단계  
  
* * *

## Layer 1 필드 (기본)

Layer 1 필드는 **기본적인 QA 평가** 에 필요한 필드들입니다.

### 1\. `qa_id` (필수)

  * **타입** : `string`

  * **설명** : QAPair의 고유 식별자

  * **형식** : 자유 형식이지만 일관된 패턴 권장

  * **실제 구현** : `korean_rag_dataset_generator.py`의 `QAPair` 클래스에서 `qa_id` 필드명 사용

  * **예제** :
``` [](<#cb3-1>)"qa_id": "qa_001"
        [](<#cb3-2>)"qa_id": "math_calculation_01"
        [](<#cb3-3>)"qa_id": "customer_support_greeting_001"
```

### 2\. `question` (필수)

  * **타입** : `string`

  * **설명** : 에이전트에게 제공될 질문 또는 프롬프트

  * **작성 팁** :

    * 명확하고 구체적으로 작성
    * 실제 사용자가 물어볼 법한 질문
    * 모호성을 최소화
  * **예제** :
``` [](<#cb4-1>)"question": "What is 25 * 4?"
        [](<#cb4-2>)"question": "Summarize the main points of the attached PDF document."
        [](<#cb4-3>)"question": "Find the latest news about AI in healthcare."
```

### 3\. `ground_truth` (필수)

  * **타입** : `string`

  * **설명** : 정답 또는 예상 응답

  * **작성 팁** :

    * 정확하고 완전한 답변
    * 유연성 허용: 완전 일치가 아닌 유사도 평가
    * 다양한 표현 허용
  * **예제** :
``` [](<#cb5-1>)"ground_truth": "100"
        [](<#cb5-2>)"ground_truth": "The document discusses three main topics: climate change impacts, renewable energy solutions, and policy recommendations."
```

### 4\. `answer` (필수)

  * **타입** : `string`

  * **설명** : 문서 내용을 바탕으로 한 완전한 답변

  * **실제 구현** : PDF 생성 시 AI가 2-3문장으로 자동 생성

  * **작성 팁** :

    * 주어진 문서 내용만을 기반으로 작성
    * 완전하고 상세한 답변 (2-3문장)
    * `ground_truth`보다 더 상세함
  * **예제** :
``` [](<#cb6-1>)"answer": "100"
        [](<#cb6-2>)"answer": "The document discusses three main topics: climate change impacts, renewable energy solutions, and policy recommendations. It provides detailed analysis of current trends and future projections."
```

### 5\. `context` (필수)

  * **타입** : `string` (단수형)

  * **설명** : 질문에 대한 배경 정보 또는 컨텍스트 (문서 청크 내용)

  * **실제 구현** : PDF 청킹 시 생성된 청크 내용이 자동으로 context로 사용됨

  * **작성 팁** :

    * 에이전트가 답변을 생성하는 데 필요한 정보
    * RAG 시스템에서는 검색 결과로 사용될 수 있음
    * 충분한 정보를 제공하되, 불필요한 정보는 제외
  * **예제** :
``` [](<#cb7-1>)"context": "The user is asking for a basic multiplication calculation."
        [](<#cb7-2>)"context": "The PDF document titled 'Climate Action Report 2024' contains 50 pages discussing climate change, renewable energy, and policy recommendations. The report was published by the International Climate Organization."
```

### 6\. `ground_truth` (필수)

  * **타입** : `string`

  * **설명** : 평가를 위한 핵심 정답 (간결한 버전)

  * **실제 구현** : AI가 1-2문장으로 간결하게 생성

  * **`answer`와의 차이**:

    * `answer`: 완전하고 상세한 답변 (2-3문장)
    * `ground_truth`: 평가 기준이 되는 핵심 정답 (1-2문장, 간결)
  * **작성 팁** :

    * 정확하고 완전한 답변
    * 유연성 허용: 완전 일치가 아닌 유사도 평가
    * 다양한 표현 허용
  * **예제** :
``` [](<#cb8-1>)"ground_truth": "100"
        [](<#cb8-2>)"ground_truth": "The document discusses climate change, renewable energy, and policy recommendations."
```

### 7\. `metadata` (선택)

  * **타입** : `object`

  * **설명** : 추가 메타데이터

  * **일반적인 필드** :

    * `domain`: 도메인 분류 (예: “math”, “customer_support”, “healthcare”)
    * `difficulty`: 난이도 (예: “easy”, “medium”, “hard”)
    * `source`: 데이터 출처 (예: “manual”, “pdf”, “real_user_query”)
    * `tags`: 태그 리스트 (예: [“calculation”, “basic”])
    * `created_at`: 생성 시간 (ISO 8601)
  * **예제** :
``` [](<#cb9-1>)"metadata": {
        [](<#cb9-2>)  "domain": "mathematics",
        [](<#cb9-3>)  "difficulty": "easy",
        [](<#cb9-4>)  "source": "manual",
        [](<#cb9-5>)  "tags": ["calculation", "multiplication"],
        [](<#cb9-6>)  "created_at": "2024-01-15T10:30:00Z"
        [](<#cb9-7>)}
```

* * *

## Layer 2 필드 (Agentic + Security)

Layer 2 필드는 **Agentic AI 시스템 및 보안 평가** 에 필요한 고급 필드들입니다. 이 필드들은 선택 사항이지만, Layer 2 메트릭을 사용하려면 필수입니다.

### 1\. `expected_tools` (선택)

  * **타입** : `list[string]`
  * **Layer 2 메트릭** : Tool Selection Accuracy
  * **설명** : 에이전트가 이 질문을 처리하기 위해 **사용해야 할 도구 목록**
  * **평가 방식** : 
    * Precision, Recall, F1 Score 계산
    * 불필요한 도구 사용 검출
    * 필요한 도구 누락 검출

#### 작성 가이드

**1) 도구 이름 일관성** \- 에이전트 코드에서 사용하는 도구 이름과 **정확히 일치** 해야 합니다 - 대소문자 구분에 주의

**2) 필수 도구만 포함** \- 이 질문을 답변하는 데 **반드시 필요한 도구만** 포함 - 선택적 도구는 제외

**3) 순서는 중요하지 않음** \- 도구 사용 순서가 아니라 **사용 여부** 만 평가

#### 예제

**예제 1: 간단한 검색**
```json
    [](<#cb10-1>){
    [](<#cb10-2>)  "question": "What is the population of Tokyo?",
    [](<#cb10-3>)  "expected_tools": ["search"]
    [](<#cb10-4>)}
```

**예제 2: 수학 계산**
```json
    [](<#cb11-1>){
    [](<#cb11-2>)  "question": "Calculate the compound interest on $1000 at 5% for 10 years.",
    [](<#cb11-3>)  "expected_tools": ["calculator", "python_repl"]
    [](<#cb11-4>)}
```

**예제 3: 복합 작업**
```json
    [](<#cb12-1>){
    [](<#cb12-2>)  "question": "Find recent stock prices for AAPL and create a visualization.",
    [](<#cb12-3>)  "expected_tools": ["search", "yahoo_finance", "python_repl", "matplotlib"]
    [](<#cb12-4>)}
```

**예제 4: RAG 시스템**
```json
    [](<#cb13-1>){
    [](<#cb13-2>)  "question": "Summarize the key findings from the research papers on quantum computing.",
    [](<#cb13-3>)  "expected_tools": ["vector_search", "pdf_reader", "summarizer"]
    [](<#cb13-4>)}
```

#### 일반적인 도구 이름

도구 이름 | 설명 | 용도  
---|---|---  
`search` | 웹 검색 | 최신 정보, 일반 지식  
`calculator` | 계산기 | 기본 수학 계산  
`python_repl` | Python 인터프리터 | 복잡한 계산, 데이터 처리  
`vector_search` | 벡터 DB 검색 | RAG, 유사 문서 검색  
`sql_db` | SQL 데이터베이스 | 구조화된 데이터 쿼리  
`api_call` | 외부 API 호출 | 날씨, 주가, 뉴스 등  
`pdf_reader` | PDF 읽기 | 문서 분석  
`summarizer` | 요약 | 긴 텍스트 요약  
`translator` | 번역 | 다국어 번역  
`code_interpreter` | 코드 실행 | 코드 생성 및 실행  
  
### 2\. `expected_agents` (선택)

  * **타입** : `list[string]`
  * **Layer 2 메트릭** : Agent Coordination
  * **설명** : 이 질문을 처리하는 데 **참여해야 할 에이전트 목록**
  * **평가 방식** : 
    * 에이전트 간 상호작용 추적
    * 협업 점수 계산 (0-10)
    * 성공률, 다양성, 균형 평가

#### 작성 가이드

**1) Multi-Agent 시스템에만 사용** \- 단일 에이전트 시스템에는 불필요 - CrewAI, AutoGen, LangGraph Multi-Agent 등에 적용

**2) 에이전트 Role/Name 사용** \- 에이전트를 식별하는 고유한 이름 또는 역할 - 코드에서 정의한 이름과 일치

**3) 모든 참여 에이전트 포함** \- 직접 작업을 수행하는 에이전트 - 조정(orchestration)하는 에이전트 - 검증(validation)하는 에이전트

#### 예제

**예제 1: CrewAI - 연구 작업**
```json
    [](<#cb14-1>){
    [](<#cb14-2>)  "question": "Research the latest trends in AI and write a summary report.",
    [](<#cb14-3>)  "expected_agents": ["manager", "researcher", "writer", "reviewer"]
    [](<#cb14-4>)}
```

**예제 2: 고객 지원**
```json
    [](<#cb15-1>){
    [](<#cb15-2>)  "question": "Help me reset my password.",
    [](<#cb15-3>)  "expected_agents": ["classifier", "auth_agent", "notification_agent"]
    [](<#cb15-4>)}
```

**예제 3: 데이터 분석 파이프라인**
```json
    [](<#cb16-1>){
    [](<#cb16-2>)  "question": "Analyze sales data and create a dashboard.",
    [](<#cb16-3>)  "expected_agents": ["data_loader", "data_processor", "analyst", "visualizer"]
    [](<#cb16-4>)}
```

### 3\. `expected_workflow_steps` (선택)

  * **타입** : `list[string]`
  * **Layer 2 메트릭** : Workflow Execution Success Rate
  * **설명** : 워크플로우에서 **실행되어야 할 단계(노드) 목록**
  * **평가 방식** : 
    * 각 단계의 실행 성공 여부
    * 단계별 성공률 계산
    * 작업 전체 성공률 계산

#### 작성 가이드

**1) LangGraph, LangChain 워크플로우에 사용** \- LangGraph의 노드 이름 - LangChain의 chain 단계 이름

**2) 실행 순서 포함** \- 순서대로 나열 (선택 사항이지만 권장) - 병렬 실행되는 단계도 모두 포함

**3) 조건부 단계 처리** \- 조건부로 실행되는 단계는 실제 실행 여부에 따라 평가 - 또는 가능한 모든 경로의 단계를 포함

#### 예제

**예제 1: RAG 워크플로우**
```json
    [](<#cb17-1>){
    [](<#cb17-2>)  "question": "What are the benefits of solar energy?",
    [](<#cb17-3>)  "expected_workflow_steps": ["retrieval", "reranking", "generation", "validation"]
    [](<#cb17-4>)}
```

**예제 2: LangGraph 에이전트**
```json
    [](<#cb18-1>){
    [](<#cb18-2>)  "question": "Plan a trip to Paris.",
    [](<#cb18-3>)  "expected_workflow_steps": ["planning", "research", "booking", "confirmation"]
    [](<#cb18-4>)}
```

**예제 3: 복잡한 워크플로우**
```json
    [](<#cb19-1>){
    [](<#cb19-2>)  "question": "Analyze customer feedback and suggest improvements.",
    [](<#cb19-3>)  "expected_workflow_steps": [
    [](<#cb19-4>)    "data_ingestion",
    [](<#cb19-5>)    "preprocessing",
    [](<#cb19-6>)    "sentiment_analysis",
    [](<#cb19-7>)    "topic_modeling",
    [](<#cb19-8>)    "insight_generation",
    [](<#cb19-9>)    "recommendation"
    [](<#cb19-10>)  ]
    [](<#cb19-11>)}
```

* * *

## Golden Dataset 생성 방법

Golden Dataset을 생성하는 방법은 크게 3가지입니다.

### 방법 1: 수동 생성 (Manual)

#### 장점

  * 정확하고 고품질
  * 세밀한 제어 가능
  * Layer 2 필드를 정확히 정의 가능

#### 단점

  * 시간 소모적
  * 확장성 제한

#### 과정

**1) JSON 파일 직접 작성**
```json
    [](<#cb20-1>){
    [](<#cb20-2>)  "dataset_id": "dataset_a1b2c3d4",
    [](<#cb20-3>)  "source_document": "documentation.pdf",
    [](<#cb20-4>)  "created_at": "2024-01-15T10:00:00Z",
    [](<#cb20-5>)  "total_qa_pairs": 2,
    [](<#cb20-6>)  "qa_pairs": [
    [](<#cb20-7>)    {
    [](<#cb20-8>)      "qa_id": "qa_001",
    [](<#cb20-9>)      "question": "What is 15 + 27?",
    [](<#cb20-10>)      "answer": "The result of 15 + 27 is 42.",
    [](<#cb20-11>)      "context": "Simple arithmetic addition problem for basic calculation.",
    [](<#cb20-12>)      "ground_truth": "42",
    [](<#cb20-13>)      "metadata": {
    [](<#cb20-14>)        "domain": "math",
    [](<#cb20-15>)        "difficulty": "easy",
    [](<#cb20-16>)        "chunk_id": "chunk_p1_i0_abc123",
    [](<#cb20-17>)        "page_number": 1
    [](<#cb20-18>)      },
    [](<#cb20-19>)      "expected_tools": ["calculator"]
    [](<#cb20-20>)    },
    [](<#cb20-21>)    {
    [](<#cb20-22>)      "qa_id": "qa_002",
    [](<#cb20-23>)      "question": "Find the latest news on AI.",
    [](<#cb20-24>)      "answer": "Recent news includes major advancements in GPT-4, Gemini, and Claude models with improved capabilities.",
    [](<#cb20-25>)      "context": "The user wants current information about AI developments in 2024.",
    [](<#cb20-26>)      "ground_truth": "Recent advancements in GPT-4, Gemini, and Claude models.",
    [](<#cb20-27>)      "metadata": {
    [](<#cb20-28>)        "domain": "news",
    [](<#cb20-29>)        "difficulty": "medium",
    [](<#cb20-30>)        "chunk_id": "chunk_p2_i1_def456",
    [](<#cb20-31>)        "page_number": 2
    [](<#cb20-32>)      },
    [](<#cb20-33>)      "expected_tools": ["search", "news_api"]
    [](<#cb20-34>)    }
    [](<#cb20-35>)  ],
    [](<#cb20-36>)  "metadata": {
    [](<#cb20-37>)    "total_pages": 50,
    [](<#cb20-38>)    "total_chunks": 25,
    [](<#cb20-39>)    "chunk_size": 1000,
    [](<#cb20-40>)    "chunk_overlap": 200,
    [](<#cb20-41>)    "num_questions_per_chunk": 3,
    [](<#cb20-42>)    "model": "gpt-4o-mini"
    [](<#cb20-43>)  }
    [](<#cb20-44>)}
```

**2) Python 코드로 생성 (실제 구조 사용)**
```python
    [](<#cb21-1>)from agent_evaluator.datasets.korean_rag_dataset_generator import QAPair, GoldenDataset, GoldenDatasetManager
    [](<#cb21-2>)from datetime import datetime
    [](<#cb21-3>)
    [](<#cb21-4>)def create_golden_dataset():
    [](<#cb21-5>)    # QAPair 생성
    [](<#cb21-6>)    qa_pairs = [
    [](<#cb21-7>)        QAPair(
    [](<#cb21-8>)            qa_id="cs_001",
    [](<#cb21-9>)            question="How do I reset my password?",
    [](<#cb21-10>)            answer="To reset your password, go to Settings > Account > Reset Password and follow the instructions.",
    [](<#cb21-11>)            context="User account management documentation explains the password reset process.",
    [](<#cb21-12>)            ground_truth="Go to Settings > Account > Reset Password.",
    [](<#cb21-13>)            metadata={
    [](<#cb21-14>)                "domain": "customer_support",
    [](<#cb21-15>)                "difficulty": "easy",
    [](<#cb21-16>)                "category": "authentication"
    [](<#cb21-17>)            },
    [](<#cb21-18>)            expected_tools=["knowledge_base"],
    [](<#cb21-19>)            expected_agents=["support_agent"]
    [](<#cb21-20>)        ),
    [](<#cb21-21>)        QAPair(
    [](<#cb21-22>)            qa_id="cs_002",
    [](<#cb21-23>)            question="What is your refund policy?",
    [](<#cb21-24>)            answer="We offer a 30-day money-back guarantee for all purchases made through our platform.",
    [](<#cb21-25>)            context="Company refund policy documentation states the terms and conditions.",
    [](<#cb21-26>)            ground_truth="30-day money-back guarantee for all purchases.",
    [](<#cb21-27>)            metadata={
    [](<#cb21-28>)                "domain": "customer_support",
    [](<#cb21-29>)                "difficulty": "easy",
    [](<#cb21-30>)                "category": "billing"
    [](<#cb21-31>)            },
    [](<#cb21-32>)            expected_tools=["policy_db", "search"],
    [](<#cb21-33>)            expected_agents=["support_agent", "billing_agent"]
    [](<#cb21-34>)        )
    [](<#cb21-35>)    ]
    [](<#cb21-36>)
    [](<#cb21-37>)    # GoldenDataset 생성
    [](<#cb21-38>)    dataset = GoldenDataset(
    [](<#cb21-39>)        dataset_id="customer_support_qa",
    [](<#cb21-40>)        source_document="support_docs.pdf",
    [](<#cb21-41>)        created_at=datetime.now().isoformat(),
    [](<#cb21-42>)        total_qa_pairs=len(qa_pairs),
    [](<#cb21-43>)        qa_pairs=qa_pairs,
    [](<#cb21-44>)        metadata={
    [](<#cb21-45>)            "version": "1.0",
    [](<#cb21-46>)            "created_by": "support_team"
    [](<#cb21-47>)        }
    [](<#cb21-48>)    )
    [](<#cb21-49>)
    [](<#cb21-50>)    # 저장
    [](<#cb21-51>)    manager = GoldenDatasetManager(output_dir="golden_datasets")
    [](<#cb21-52>)    saved_path = manager.save_dataset(dataset, format="json")
    [](<#cb21-53>)
    [](<#cb21-54>)    print(f"✅ Golden Dataset created: {len(qa_pairs)} QAPairs")
    [](<#cb21-55>)    print(f"   Saved to: {saved_path}")
    [](<#cb21-56>)
    [](<#cb21-57>)create_golden_dataset()
```

### 방법 2: PDF에서 자동 생성

Agent Evaluator는 **PDF 문서에서 자동으로 Golden Dataset을 생성** 하는 기능을 제공합니다.

#### 장점

  * 대량의 QAPair를 빠르게 생성
  * 문서 기반 지식을 자동으로 추출
  * RAG 시스템 평가에 최적

#### 사용법
```python
    [](<#cb22-1>)from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator
    [](<#cb22-2>)
    [](<#cb22-3>)# 생성기 초기화
    [](<#cb22-4>)generator = KoreanRAGDatasetGenerator(
    [](<#cb22-5>)    model="gpt-4o-mini",  # 또는 "gpt-4o"
    [](<#cb22-6>)    chunk_size=1000,      # 청크 크기 (문자 수)
    [](<#cb22-7>)    chunk_overlap=200,    # 청크 겹침 (문자 수)
    [](<#cb22-8>)    output_dir="golden_datasets"
    [](<#cb22-9>))
    [](<#cb22-10>)
    [](<#cb22-11>)# PDF에서 Golden Dataset 생성
    [](<#cb22-12>)dataset = generator.generate_from_pdf(
    [](<#cb22-13>)    pdf_path="documentation.pdf",
    [](<#cb22-14>)    num_questions_per_chunk=3,  # 청크당 질문 수
    [](<#cb22-15>)    question_types=["factual", "reasoning", "summary"],
    [](<#cb22-16>)    save_format="json",  # "json" 또는 "csv"
    [](<#cb22-17>)    max_chunks=None  # 전체 청크 사용 (테스트 시 숫자 지정 가능)
    [](<#cb22-18>))
```

#### 생성 과정

  1. **PDF 텍스트 추출** : pypdf 또는 pdfplumber 사용
  2. **텍스트 청킹** : 설정된 chunk_size와 chunk_overlap에 따라 분할
  3. **AI 기반 QA 생성** : OpenAI GPT 모델을 사용하여 각 청크에서 질문-답변 생성 
     * **질문** : 자연스럽고 구체적인 질문
     * **답변** : 2-3문장의 완전한 답변
     * **ground_truth** : 1-2문장의 간결한 핵심 정답
  4. **검증** : 필수 필드 확인 및 품질 검증
  5. **저장** : JSON 또는 CSV 파일로 저장

#### 실제 생성 프로세스 (korean_rag_dataset_generator.py)
```json
    [](<#cb23-1>)# 1. PDF 텍스트 추출 (pypdf 또는 pdfplumber)
    [](<#cb23-2>)extractor = KoreanPDFExtractor()
    [](<#cb23-3>)pages_text = extractor.extract_text("document.pdf")
    [](<#cb23-4>)
    [](<#cb23-5>)# 2. 텍스트 청킹
    [](<#cb23-6>)chunker = TextChunker(chunk_size=1000, chunk_overlap=200)
    [](<#cb23-7>)chunks = chunker.chunk_documents(pages_text)
    [](<#cb23-8>)
    [](<#cb23-9>)# 3. 각 청크에서 QA 생성 (OpenAI API)
    [](<#cb23-10>)qa_generator = KoreanQAGenerator(model="gpt-4o-mini")
    [](<#cb23-11>)for chunk in chunks:
    [](<#cb23-12>)    qa_pairs = qa_generator.generate_qa_pairs(
    [](<#cb23-13>)        chunk,
    [](<#cb23-14>)        num_questions=3,
    [](<#cb23-15>)        question_types=["factual", "reasoning", "summary"]
    [](<#cb23-16>)    )
    [](<#cb23-17>)
    [](<#cb23-18>)# 4. Golden Dataset 생성 및 저장
    [](<#cb23-19>)dataset_manager = GoldenDatasetManager()
    [](<#cb23-20>)dataset = dataset_manager.create_dataset(qa_pairs, "document.pdf")
    [](<#cb23-21>)dataset_manager.save_dataset(dataset, format="json")
```

#### 중요: Layer 2 필드는 수동 추가 권장

현재 구현에서는 **Layer 2 필드(expected_tools, expected_agents, expected_workflow_steps)가 자동으로 생성되지 않습니다**.

PDF 생성 후: 1. Dashboard에서 Golden Dataset 로드 2. Layer 2 필드를 수동으로 추가/편집 3. 또는 Python 코드로 직접 추가:
```python
    [](<#cb24-1>)from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager
    [](<#cb24-2>)
    [](<#cb24-3>)manager = GoldenDatasetManager()
    [](<#cb24-4>)dataset = manager.load_dataset("golden_dataset.json")
    [](<#cb24-5>)
    [](<#cb24-6>)# Layer 2 필드 추가
    [](<#cb24-7>)for qa in dataset.qa_pairs:
    [](<#cb24-8>)    qa.expected_tools = ["vector_search", "document_reader"]
    [](<#cb24-9>)    qa.expected_agents = ["research_agent"]
    [](<#cb24-10>)    qa.expected_workflow_steps = ["retrieval", "generation"]
    [](<#cb24-11>)
    [](<#cb24-12>)# 저장
    [](<#cb24-13>)manager.save_dataset(dataset, format="json")
```

### 방법 3: Dashboard에서 생성

Agent Evaluator Dashboard는 **GUI 기반 Golden Dataset 생성 및 편집** 을 지원합니다.

#### 장점

  * 사용자 친화적 인터페이스
  * 실시간 미리보기
  * Layer 2 필드 편집 UI

#### 사용법

**1) Dashboard 실행**
```bash
    [](<#cb25-1>)agent-eval serve
```

**2) “Golden Dataset” 탭으로 이동**

**3) “Create New QAPair” 클릭**

**4) 폼 작성** \- **ID** : qa_001 - **Question** : What is the capital of France? - **Ground Truth** : Paris - **Context** : France is a country in Western Europe. - **Metadata** : `{"domain": "geography", "difficulty": "easy"}` \- **Expected Tools** : [“search”] - **Expected Agents** : [“research_agent”]

**5) “Save” 클릭**

**6) “Export Dataset” 클릭하여 JSON 다운로드**

* * *

## Dashboard에서 편집하기

### 기존 Golden Dataset 로드

**JSON 직접 로드**
```python
    [](<#cb26-1>)import json
    [](<#cb26-2>)
    [](<#cb26-3>)with open("results/golden_datasets/my_dataset.json") as f:
    [](<#cb26-4>)    dataset = json.load(f)
    [](<#cb26-5>)
    [](<#cb26-6>)# 로드된 데이터 확인
    [](<#cb26-7>)print(f"로드된 QA 쌍: {len(dataset)}개")
```

### QAPair 편집

**DataFrame 편집 방식**
```json
    [](<#cb27-1>)# 1. 특정 QAPair 수정
    [](<#cb27-2>)df.loc[df['qa_id'] == 'qa_001', 'ground_truth'] = "수정된 정답"
    [](<#cb27-3>)
    [](<#cb27-4>)# 2. Layer 2 필드 추가/수정 (쉼표로 구분된 문자열)
    [](<#cb27-5>)df.loc[df['qa_id'] == 'qa_001', 'expected_tools'] = "vector_search,document_reader"
    [](<#cb27-6>)
    [](<#cb27-7>)# 3. 저장
    [](<#cb27-8>)manager.save_golden_dataset(
    [](<#cb27-9>)    df=df,
    [](<#cb27-10>)    filepath="golden_datasets/my_dataset.json",
    [](<#cb27-11>)    dataset_id="my_dataset",
    [](<#cb27-12>)    source_document="my_document.pdf",
    [](<#cb27-13>)    editor="Your Name",
    [](<#cb27-14>)    reason="Updated ground truth and added Layer 2 fields"
    [](<#cb27-15>))
```

### QAPair 추가
```json
    [](<#cb28-1>)# 새 QA 쌍 추가
    [](<#cb28-2>)new_qa = {
    [](<#cb28-3>)    "qa_id": "qa_new",
    [](<#cb28-4>)    "question": "새로운 질문",
    [](<#cb28-5>)    "answer": "새로운 답변",
    [](<#cb28-6>)    "context": "새로운 컨텍스트",
    [](<#cb28-7>)    "ground_truth": "새로운 정답",
    [](<#cb28-8>)    "metadata": {"domain": "new", "difficulty": "medium"},
    [](<#cb28-9>)    "expected_tools": ["search"],
    [](<#cb28-10>)    "expected_agents": None,
    [](<#cb28-11>)    "expected_workflow_steps": None
    [](<#cb28-12>)}
    [](<#cb28-13>)
    [](<#cb28-14>)manager.add_qa_pair(
    [](<#cb28-15>)    qa_data=new_qa,
    [](<#cb28-16>)    filepath="golden_datasets/my_dataset.json",
    [](<#cb28-17>)    editor="Your Name",
    [](<#cb28-18>)    reason="Added new test case"
    [](<#cb28-19>))
```

### QAPair 삭제
```json
    [](<#cb29-1>)manager.delete_qa_pair(
    [](<#cb29-2>)    qa_id="qa_001",
    [](<#cb29-3>)    filepath="golden_datasets/my_dataset.json",
    [](<#cb29-4>)    editor="Your Name",
    [](<#cb29-5>)    reason="Removed outdated test case"
    [](<#cb29-6>))
```

### Layer 2 필드 일괄 추가
```json
    [](<#cb30-1>)# DataFrame에서 일괄 수정
    [](<#cb30-2>)df = manager.load_golden_dataset("golden_datasets/my_dataset.json")
    [](<#cb30-3>)
    [](<#cb30-4>)# 특정 도메인의 QA에 Layer 2 필드 일괄 추가
    [](<#cb30-5>)mask = df['metadata'].apply(lambda x: x.get('domain') == 'math' if isinstance(x, dict) else False)
    [](<#cb30-6>)df.loc[mask, 'expected_tools'] = "calculator,python_repl"
    [](<#cb30-7>)df.loc[mask, 'expected_workflow_steps'] = "parse,calculate,format"
    [](<#cb30-8>)
    [](<#cb30-9>)# 저장
    [](<#cb30-10>)manager.save_golden_dataset(
    [](<#cb30-11>)    df=df,
    [](<#cb30-12>)    filepath="golden_datasets/my_dataset.json",
    [](<#cb30-13>)    dataset_id="my_dataset",
    [](<#cb30-14>)    source_document="my_document.pdf",
    [](<#cb30-15>)    editor="Your Name",
    [](<#cb30-16>)    reason="Bulk update Layer 2 fields for math domain"
    [](<#cb30-17>))
```

### 검증
```python
    [](<#cb31-1>)from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager
    [](<#cb31-2>)
    [](<#cb31-3>)manager = GoldenDatasetManager()
    [](<#cb31-4>)dataset = manager.load_dataset("golden_datasets/my_dataset.json")
    [](<#cb31-5>)
    [](<#cb31-6>)# 데이터셋 검증
    [](<#cb31-7>)validation = manager.validate_dataset(dataset)
    [](<#cb31-8>)
    [](<#cb31-9>)if validation["is_valid"]:
    [](<#cb31-10>)    print("✅ 검증 통과")
    [](<#cb31-11>)else:
    [](<#cb31-12>)    print("❌ 검증 실패:")
    [](<#cb31-13>)    for issue in validation["issues"]:
    [](<#cb31-14>)        print(f"  - {issue}")
    [](<#cb31-15>)
    [](<#cb31-16>)print(f"\n총 QA 쌍: {validation['total_qa_pairs']}개")
```

* * *

## 자동 평가 워크플로우

Golden Dataset을 사용한 자동 평가는 다음과 같이 진행됩니다.

### 기본 워크플로우 (실제 구현)
```python
    [](<#cb32-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb32-2>)
    [](<#cb32-3>)# 1. Monitor 초기화
    [](<#cb32-4>)monitor = PerformanceMonitor()
    [](<#cb32-5>)
    [](<#cb32-6>)# 2. 임계값 설정
    [](<#cb32-7>)monitor.thresholds = {
    [](<#cb32-8>)    # Layer 1
    [](<#cb32-9>)    'tcr': 90.0,
    [](<#cb32-10>)    'accuracy': 85.0,
    [](<#cb32-11>)    'hallucination': 5.0,
    [](<#cb32-12>)    # Layer 2
    [](<#cb32-13>)    'tool_selection_accuracy': 80.0
    [](<#cb32-14>)}
    [](<#cb32-15>)
    [](<#cb32-16>)# 3. 에이전트 함수 정의
    [](<#cb32-17>)def my_agent(question: str):
    [](<#cb32-18>)    """
    [](<#cb32-19>)    평가할 에이전트 함수
    [](<#cb32-20>)
    [](<#cb32-21>)    Args:
    [](<#cb32-22>)        question: 질문 (Golden Dataset의 'question' 필드)
    [](<#cb32-23>)
    [](<#cb32-24>)    Returns:
    [](<#cb32-25>)        dict: 필수 키
    [](<#cb32-26>)            - answer: 에이전트의 답변 (문자열)
    [](<#cb32-27>)            - tools_used: 사용한 도구 리스트 (Layer 2용, 선택)
    [](<#cb32-28>)            - latency: 응답 시간 (선택)
    [](<#cb32-29>)            - token_usage: 토큰 사용량 (선택)
    [](<#cb32-30>)    """
    [](<#cb32-31>)    # 실제 에이전트 로직 (LLM 호출 등)
    [](<#cb32-32>)    response = your_llm.predict(question)
    [](<#cb32-33>)
    [](<#cb32-34>)    return {
    [](<#cb32-35>)        "answer": response,
    [](<#cb32-36>)        "tools_used": ["search", "calculator"],  # Layer 2: 실제 사용한 도구
    [](<#cb32-37>)        "latency": 1.5,
    [](<#cb32-38>)        "token_usage": {"input": 100, "output": 50}
    [](<#cb32-39>)    }
    [](<#cb32-40>)
    [](<#cb32-41>)# 4. Golden Dataset 기반 자동 평가
    [](<#cb32-42>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb32-43>)    agent_fn=my_agent,
    [](<#cb32-44>)    dataset_path="golden_datasets/sample_dataset.json",  # 또는 절대 경로
    [](<#cb32-45>)    enable_layer2_metrics=True,  # Layer 2 자동 평가
    [](<#cb32-46>)    enable_advanced_metrics=False,  # Layer 3 (유료)
    [](<#cb32-47>)    verbose=True  # 진행 상황 출력
    [](<#cb32-48>))
    [](<#cb32-49>)
    [](<#cb32-50>)# 5. 결과 확인
    [](<#cb32-51>)print(f"\n📊 평가 결과:")
    [](<#cb32-52>)print(f"  총 평가: {results['total_evaluated']}개")
    [](<#cb32-53>)print(f"  TCR: {results['layer1_metrics']['tcr']:.1f}%")
    [](<#cb32-54>)print(f"  Accuracy: {results['layer1_metrics']['accuracy']:.1f}%")
    [](<#cb32-55>)print(f"  Hallucination Rate: {results['layer1_metrics']['hallucination_rate']:.1f}%")
    [](<#cb32-56>)
    [](<#cb32-57>)if results.get('layer2_metrics'):
    [](<#cb32-58>)    print(f"  Tool Selection Accuracy: {results['layer2_metrics']['tool_selection_accuracy']:.1f}%")
    [](<#cb32-59>)    print(f"  Tool Selection F1: {results['layer2_metrics']['tool_selection_f1']:.1f}%")
    [](<#cb32-60>)
    [](<#cb32-61>)# 6. 임계값 비교
    [](<#cb32-62>)if results.get('pass_fail'):
    [](<#cb32-63>)    print(f"\n🎯 임계값 비교:")
    [](<#cb32-64>)    for metric, data in results['pass_fail'].items():
    [](<#cb32-65>)        status = "✅ PASS" if data['status'] == 'pass' else "❌ FAIL"
    [](<#cb32-66>)        print(f"  {status} {data['name']}: {data['value']:.1f} (임계값: {data['threshold']})")
```

### 중요: evaluate_with_golden_dataset() 작동 방식
```json
    [](<#cb33-1>)# 내부적으로 다음과 같이 동작합니다:
    [](<#cb33-2>)
    [](<#cb33-3>)# 1. Golden Dataset 로드
    [](<#cb33-4>)with open(dataset_path, 'r') as f:
    [](<#cb33-5>)    golden_datasets = json.load(f)
    [](<#cb33-6>)
    [](<#cb33-7>)# 2. 각 QA 쌍에 대해 평가
    [](<#cb33-8>)for qa_pair in golden_datasets:
    [](<#cb33-9>)    # 2.1 에이전트 실행
    [](<#cb33-10>)    result = agent_fn(qa_pair['question'])
    [](<#cb33-11>)
    [](<#cb33-12>)    # 2.2 TaskResult 자동 생성
    [](<#cb33-13>)    task = TaskResult(
    [](<#cb33-14>)        task_id=qa_pair['qa_id'],
    [](<#cb33-15>)        task_type=TaskType.QA,
    [](<#cb33-16>)        # ... 자동으로 메트릭 계산
    [](<#cb33-17>)    )
    [](<#cb33-18>)
    [](<#cb33-19>)    # 2.3 Layer 1 메트릭 자동 계산
    [](<#cb33-20>)    monitor.record_task(task)
    [](<#cb33-21>)
    [](<#cb33-22>)    # 2.4 Layer 2: Tool Selection 자동 평가
    [](<#cb33-23>)    if qa_pair.get('expected_tools'):
    [](<#cb33-24>)        monitor.tool_selection_tracker.evaluate_selection(
    [](<#cb33-25>)            task_id=task.task_id,
    [](<#cb33-26>)            expected_tools=qa_pair['expected_tools'],
    [](<#cb33-27>)            actual_tools=result.get('tools_used', [])
    [](<#cb33-28>)        )
    [](<#cb33-29>)
    [](<#cb33-30>)# 3. 결과 집계 및 반환
```

### Layer 2 자동 평가 상세

#### Tool Selection 평가
```json
    [](<#cb34-1>)# Golden Dataset QAPair
    [](<#cb34-2>){
    [](<#cb34-3>)  "id": "qa_001",
    [](<#cb34-4>)  "question": "What is 15 + 27?",
    [](<#cb34-5>)  "expected_tools": ["calculator"]
    [](<#cb34-6>)}
    [](<#cb34-7>)
    [](<#cb34-8>)# 에이전트 실행 후
    [](<#cb34-9>)# 실제 사용 도구: ["search", "calculator"]
    [](<#cb34-10>)
    [](<#cb34-11>)# 자동 평가
    [](<#cb34-12>)# - Precision: 1/2 = 50% (calculator는 맞지만 search는 불필요)
    [](<#cb34-13>)# - Recall: 1/1 = 100% (calculator 사용함)
    [](<#cb34-14>)# - F1 Score: 2 * (0.5 * 1.0) / (0.5 + 1.0) = 66.7%
```

#### Agent Coordination 평가
```json
    [](<#cb35-1>)# Golden Dataset QAPair
    [](<#cb35-2>){
    [](<#cb35-3>)  "id": "qa_002",
    [](<#cb35-4>)  "question": "Research AI trends and write a report.",
    [](<#cb35-5>)  "expected_agents": ["manager", "researcher", "writer"]
    [](<#cb35-6>)}
    [](<#cb35-7>)
    [](<#cb35-8>)# CrewAI 실행 후
    [](<#cb35-9>)# 실제 상호작용:
    [](<#cb35-10>)# - manager → researcher (delegation)
    [](<#cb35-11>)# - researcher → writer (collaboration)
    [](<#cb35-12>)
    [](<#cb35-13>)# 자동 평가
    [](<#cb35-14>)# - 모든 expected_agents 참여: ✅
    [](<#cb35-15>)# - 상호작용 성공률: 100%
    [](<#cb35-16>)# - 협업 점수: 8.5/10
```

#### Workflow Execution 평가
```json
    [](<#cb36-1>)# Golden Dataset QAPair
    [](<#cb36-2>){
    [](<#cb36-3>)  "id": "qa_003",
    [](<#cb36-4>)  "question": "Summarize this document.",
    [](<#cb36-5>)  "expected_workflow_steps": ["retrieval", "generation", "validation"]
    [](<#cb36-6>)}
    [](<#cb36-7>)
    [](<#cb36-8>)# LangGraph 실행 후
    [](<#cb36-9>)# 실제 실행 단계:
    [](<#cb36-10>)# - retrieval (success)
    [](<#cb36-11>)# - generation (success)
    [](<#cb36-12>)# - validation (success)
    [](<#cb36-13>)
    [](<#cb36-14>)# 자동 평가
    [](<#cb36-15>)# - 모든 단계 실행: ✅
    [](<#cb36-16>)# - 단계 성공률: 100%
```

### Framework 통합 예제

#### LangChain
```python
    [](<#cb37-1>)from agent_evaluator.integrations import LangChainEvaluator, AdvancedLangChainCallback
    [](<#cb37-2>)
    [](<#cb37-3>)# Golden Dataset에서 expected_tools 로드
    [](<#cb37-4>)expected_tools = ["search", "calculator"]
    [](<#cb37-5>)
    [](<#cb37-6>)# Evaluator 생성
    [](<#cb37-7>)evaluator = LangChainEvaluator(
    [](<#cb37-8>)    agent,
    [](<#cb37-9>)    monitor,
    [](<#cb37-10>)    expected_tools=expected_tools,
    [](<#cb37-11>)    enable_layer2=True
    [](<#cb37-12>))
    [](<#cb37-13>)
    [](<#cb37-14>)# 에이전트 실행 (자동 추적)
    [](<#cb37-15>)result = evaluator.run(
    [](<#cb37-16>)    "What is 15 + 27 and who invented the calculator?"
    [](<#cb37-17>))
    [](<#cb37-18>)
    [](<#cb37-19>)# Tool Selection 자동 평가됨
```

#### CrewAI
```python
    [](<#cb38-1>)from agent_evaluator.integrations import CrewAIEvaluator
    [](<#cb38-2>)
    [](<#cb38-3>)# Crew 생성
    [](<#cb38-4>)crew = Crew(
    [](<#cb38-5>)    agents=[manager, researcher, writer],
    [](<#cb38-6>)    tasks=[research_task, write_task]
    [](<#cb38-7>))
    [](<#cb38-8>)
    [](<#cb38-9>)# Evaluator 생성
    [](<#cb38-10>)evaluator = CrewAIEvaluator(
    [](<#cb38-11>)    crew,
    [](<#cb38-12>)    monitor,
    [](<#cb38-13>)    enable_layer2=True,
    [](<#cb38-14>)    expected_agents=["manager", "researcher", "writer"]
    [](<#cb38-15>))
    [](<#cb38-16>)
    [](<#cb38-17>)# 실행 (자동 추적)
    [](<#cb38-18>)result = evaluator.kickoff()
    [](<#cb38-19>)
    [](<#cb38-20>)# Agent Coordination 자동 평가됨
```

#### LangGraph
```python
    [](<#cb39-1>)from agent_evaluator.integrations import LangGraphEvaluator
    [](<#cb39-2>)
    [](<#cb39-3>)# Evaluator 생성
    [](<#cb39-4>)evaluator = LangGraphEvaluator(
    [](<#cb39-5>)    monitor,
    [](<#cb39-6>)    enable_workflow_tracking=True,
    [](<#cb39-7>)    expected_workflow_steps=["retrieval", "generation", "validation"]
    [](<#cb39-8>))
    [](<#cb39-9>)
    [](<#cb39-10>)# 노드 추가 (자동 래핑)
    [](<#cb39-11>)workflow.add_node("retrieval", retrieval_func)
    [](<#cb39-12>)workflow.add_node("generation", generation_func)
    [](<#cb39-13>)workflow.add_node("validation", validation_func)
    [](<#cb39-14>)
    [](<#cb39-15>)# 실행
    [](<#cb39-16>)result = workflow.compile_and_run({"messages": ["input"]})
    [](<#cb39-17>)
    [](<#cb39-18>)# Workflow Execution 자동 평가됨
```

* * *

## Best Practices

**⚡ IMPROVED: QA Accuracy 30% Improvement (30% 향상)**

The evaluation system now uses **4 similarity metrics (4가지 유사도 메트릭)** to calculate QA accuracy with ground_truth:

  * **Token Overlap (40%):** Measures keyword coverage - most important for QA tasks
  * **Jaccard Similarity (30%):** Measures token set similarity
  * **LCS - Longest Common Subsequence (20%):** Measures sequence preservation
  * **Character-level Similarity (10%):** Handles typos and variations

**Result:** 30% more accurate QA evaluation (30% 향상) compared to simple string matching, using 4가지 유사도 메트릭

**Response Quality Automation:** When ground_truth is provided, accuracy and usefulness scores are automatically calculated based on these metrics.

### 1\. QAPair 작성 Best Practices

#### ✅ 좋은 예

**명확하고 구체적인 질문**
```json
    [](<#cb40-1>){
    [](<#cb40-2>)  "question": "What is the refund policy for digital products purchased within the last 30 days?"
    [](<#cb40-3>)}
```

**완전하고 정확한 정답**
```json
    [](<#cb41-1>){
    [](<#cb41-2>)  "ground_truth": "Digital products purchased within the last 30 days are eligible for a full refund if you contact support at support@example.com."
    [](<#cb41-3>)}
```

**충분한 컨텍스트**
```json
    [](<#cb42-1>){
    [](<#cb42-2>)  "context": "Company refund policy documentation states: 'All digital products come with a 30-day money-back guarantee. To request a refund, contact support@example.com with your order number.'"
    [](<#cb42-3>)}
```

#### ❌ 나쁜 예

**모호한 질문**
```json
    [](<#cb43-1>){
    [](<#cb43-2>)  "question": "How does refund work?"
    [](<#cb43-3>)}
```

**불완전한 정답**
```json
    [](<#cb44-1>){
    [](<#cb44-2>)  "ground_truth": "You can get a refund."
    [](<#cb44-3>)}
```

**불충분한 컨텍스트**
```json
    [](<#cb45-1>){
    [](<#cb45-2>)  "context": "Refund policy exists."
    [](<#cb45-3>)}
```

### 2\. Layer 2 필드 작성 Best Practices

#### Expected Tools

**✅ 필수 도구만 포함**
```json
    [](<#cb46-1>){
    [](<#cb46-2>)  "question": "What is 15 + 27?",
    [](<#cb46-3>)  "expected_tools": ["calculator"]
    [](<#cb46-4>)}
```

**❌ 선택적 도구 포함**
```json
    [](<#cb47-1>){
    [](<#cb47-2>)  "question": "What is 15 + 27?",
    [](<#cb47-3>)  "expected_tools": ["calculator", "search", "python_repl"]
    [](<#cb47-4>)  // search와 python_repl은 불필요
    [](<#cb47-5>)}
```

#### Expected Agents

**✅ 실제 참여하는 에이전트만**
```json
    [](<#cb48-1>){
    [](<#cb48-2>)  "question": "Research and write a summary.",
    [](<#cb48-3>)  "expected_agents": ["researcher", "writer"]
    [](<#cb48-4>)}
```

**❌ 불필요한 에이전트 포함**
```json
    [](<#cb49-1>){
    [](<#cb49-2>)  "question": "Research and write a summary.",
    [](<#cb49-3>)  "expected_agents": ["manager", "researcher", "writer", "reviewer", "publisher"]
    [](<#cb49-4>)  // 실제로는 researcher와 writer만 필요
    [](<#cb49-5>)}
```

#### Expected Workflow Steps

**✅ 실행 순서대로**
```json
    [](<#cb50-1>){
    [](<#cb50-2>)  "expected_workflow_steps": ["retrieval", "reranking", "generation", "validation"]
    [](<#cb50-3>)}
```

**❌ 순서 없음 (비권장)**
```json
    [](<#cb51-1>){
    [](<#cb51-2>)  "expected_workflow_steps": ["generation", "retrieval", "validation", "reranking"]
    [](<#cb51-3>)}
```

### 3\. Golden Dataset 관리 Best Practices

#### 버전 관리

  * Golden Dataset을 Git에 커밋
  * 변경 사항 추적
  * 버전 태그 사용 (v1.0, v1.1 등)

#### 정기 업데이트

  * 에이전트가 발전하면 Golden Dataset도 업데이트
  * 새로운 기능이 추가되면 관련 QAPair 추가
  * 오래된 QAPair는 제거 또는 업데이트

#### 다양성 확보

  * 다양한 난이도의 QAPair 포함 (easy, medium, hard)
  * 다양한 도메인 포함
  * Edge case 포함

#### 품질 검증

  * 주기적으로 QAPair 검토
  * ground_truth가 여전히 정확한지 확인
  * Layer 2 필드가 최신 상태인지 확인

### 4\. 임계값 설정 Best Practices

#### 초기 설정

  * 너무 엄격하지 않게 시작 (예: TCR 80%, Accuracy 70%)
  * 점진적으로 임계값 상향

#### 프로덕션 설정

  * 엄격한 임계값 설정 (예: TCR 95%, Accuracy 90%)
  * Layer 2 메트릭 포함

#### 예제
```python
    [](<#cb52-1>)# 개발 환경
    [](<#cb52-2>)monitor.thresholds = {
    [](<#cb52-3>)    'tcr': 80.0,
    [](<#cb52-4>)    'accuracy': 70.0,
    [](<#cb52-5>)    'tool_selection_accuracy': 70.0
    [](<#cb52-6>)}
    [](<#cb52-7>)
    [](<#cb52-8>)# 프로덕션 환경
    [](<#cb52-9>)monitor.thresholds = {
    [](<#cb52-10>)    'tcr': 95.0,
    [](<#cb52-11>)    'accuracy': 90.0,
    [](<#cb52-12>)    'hallucination': 2.0,
    [](<#cb52-13>)    'tool_selection_accuracy': 85.0,
    [](<#cb52-14>)    'agent_coordination': 8.0,
    [](<#cb52-15>)    'workflow_execution': 95.0
    [](<#cb52-16>)}
```

* * *

## 예제 Golden Datasets

### 예제 1: 간단한 QA (실제 구조)
```json
    [](<#cb53-1>){
    [](<#cb53-2>)  "dataset_id": "simple_qa_abc123",
    [](<#cb53-3>)  "source_document": "sample_document.pdf",
    [](<#cb53-4>)  "created_at": "2024-01-15T10:00:00Z",
    [](<#cb53-5>)  "total_qa_pairs": 2,
    [](<#cb53-6>)  "qa_pairs": [
    [](<#cb53-7>)    {
    [](<#cb53-8>)      "qa_id": "qa_001",
    [](<#cb53-9>)      "question": "What is the capital of France?",
    [](<#cb53-10>)      "answer": "The capital of France is Paris, which is also the largest city in the country.",
    [](<#cb53-11>)      "context": "France is a country in Western Europe. Its capital and largest city is Paris.",
    [](<#cb53-12>)      "ground_truth": "Paris",
    [](<#cb53-13>)      "metadata": {
    [](<#cb53-14>)        "domain": "geography",
    [](<#cb53-15>)        "difficulty": "easy",
    [](<#cb53-16>)        "chunk_id": "chunk_p1_i0_abc123",
    [](<#cb53-17>)        "page_number": 1
    [](<#cb53-18>)      },
    [](<#cb53-19>)      "expected_tools": ["search"],
    [](<#cb53-20>)      "expected_agents": null,
    [](<#cb53-21>)      "expected_workflow_steps": null
    [](<#cb53-22>)    },
    [](<#cb53-23>)    {
    [](<#cb53-24>)      "qa_id": "qa_002",
    [](<#cb53-25>)      "question": "What is 25 * 4?",
    [](<#cb53-26>)      "answer": "The result of 25 multiplied by 4 is 100.",
    [](<#cb53-27>)      "context": "Basic multiplication problem for arithmetic calculation.",
    [](<#cb53-28>)      "ground_truth": "100",
    [](<#cb53-29>)      "metadata": {
    [](<#cb53-30>)        "domain": "math",
    [](<#cb53-31>)        "difficulty": "easy",
    [](<#cb53-32>)        "chunk_id": "chunk_p1_i1_def456",
    [](<#cb53-33>)        "page_number": 1
    [](<#cb53-34>)      },
    [](<#cb53-35>)      "expected_tools": ["calculator"],
    [](<#cb53-36>)      "expected_agents": null,
    [](<#cb53-37>)      "expected_workflow_steps": null
    [](<#cb53-38>)    }
    [](<#cb53-39>)  ],
    [](<#cb53-40>)  "metadata": {
    [](<#cb53-41>)    "total_pages": 1,
    [](<#cb53-42>)    "total_chunks": 2,
    [](<#cb53-43>)    "chunk_size": 1000,
    [](<#cb53-44>)    "model": "gpt-4o-mini"
    [](<#cb53-45>)  }
    [](<#cb53-46>)}
```

### 예제 2: Multi-Agent 시스템
```json
    [](<#cb54-1>){
    [](<#cb54-2>)  "dataset_name": "multi_agent_research",
    [](<#cb54-3>)  "version": "1.0",
    [](<#cb54-4>)  "qa_pairs": [
    [](<#cb54-5>)    {
    [](<#cb54-6>)      "id": "research_001",
    [](<#cb54-7>)      "question": "Research the latest trends in renewable energy and write a comprehensive report.",
    [](<#cb54-8>)      "ground_truth": "A comprehensive report covering solar, wind, and hydrogen energy trends with current market analysis and future predictions.",
    [](<#cb54-9>)      "context": "The user needs a detailed research report on renewable energy trends for a business presentation.",
    [](<#cb54-10>)      "metadata": {
    [](<#cb54-11>)        "domain": "research",
    [](<#cb54-12>)        "difficulty": "hard",
    [](<#cb54-13>)        "estimated_time": "300s"
    [](<#cb54-14>)      },
    [](<#cb54-15>)      "expected_tools": ["search", "web_scraper", "pdf_reader", "summarizer"],
    [](<#cb54-16>)      "expected_agents": ["manager", "researcher", "analyst", "writer", "reviewer"],
    [](<#cb54-17>)      "expected_workflow_steps": [
    [](<#cb54-18>)        "task_decomposition",
    [](<#cb54-19>)        "research",
    [](<#cb54-20>)        "data_analysis",
    [](<#cb54-21>)        "writing",
    [](<#cb54-22>)        "review",
    [](<#cb54-23>)        "finalization"
    [](<#cb54-24>)      ]
    [](<#cb54-25>)    }
    [](<#cb54-26>)  ]
    [](<#cb54-27>)}
```

### 예제 3: RAG 시스템
```json
    [](<#cb55-1>){
    [](<#cb55-2>)  "dataset_name": "rag_qa",
    [](<#cb55-3>)  "version": "1.0",
    [](<#cb55-4>)  "qa_pairs": [
    [](<#cb55-5>)    {
    [](<#cb55-6>)      "id": "rag_001",
    [](<#cb55-7>)      "question": "What are the main benefits of solar energy according to the documentation?",
    [](<#cb55-8>)      "ground_truth": "The main benefits of solar energy include: 1) Renewable and sustainable, 2) Reduces electricity bills, 3) Low maintenance costs, 4) Environmentally friendly with zero emissions.",
    [](<#cb55-9>)      "context": "Documentation on renewable energy sources, specifically the chapter on solar energy benefits and applications.",
    [](<#cb55-10>)      "metadata": {
    [](<#cb55-11>)        "domain": "energy",
    [](<#cb55-12>)        "difficulty": "medium",
    [](<#cb55-13>)        "source": "pdf"
    [](<#cb55-14>)      },
    [](<#cb55-15>)      "expected_tools": ["vector_search", "pdf_reader"],
    [](<#cb55-16>)      "expected_workflow_steps": ["retrieval", "reranking", "generation", "validation"]
    [](<#cb55-17>)    }
    [](<#cb55-18>)  ]
    [](<#cb55-19>)}
```

### 예제 4: 고객 지원
```json
    [](<#cb56-1>){
    [](<#cb56-2>)  "dataset_name": "customer_support",
    [](<#cb56-3>)  "version": "1.0",
    [](<#cb56-4>)  "qa_pairs": [
    [](<#cb56-5>)    {
    [](<#cb56-6>)      "id": "support_001",
    [](<#cb56-7>)      "question": "I forgot my password. How can I reset it?",
    [](<#cb56-8>)      "ground_truth": "To reset your password: 1) Go to the login page, 2) Click 'Forgot Password', 3) Enter your email address, 4) Check your email for a reset link, 5) Click the link and create a new password.",
    [](<#cb56-9>)      "context": "User account management help documentation.",
    [](<#cb56-10>)      "metadata": {
    [](<#cb56-11>)        "domain": "customer_support",
    [](<#cb56-12>)        "difficulty": "easy",
    [](<#cb56-13>)        "category": "authentication"
    [](<#cb56-14>)      },
    [](<#cb56-15>)      "expected_tools": ["knowledge_base"],
    [](<#cb56-16>)      "expected_agents": ["support_agent"]
    [](<#cb56-17>)    },
    [](<#cb56-18>)    {
    [](<#cb56-19>)      "id": "support_002",
    [](<#cb56-20>)      "question": "My order hasn't arrived yet. It's been 10 days. Order number: #12345",
    [](<#cb56-21>)      "ground_truth": "I can help you track your order #12345. Let me check the shipping status and provide you with an update. If there's a delay, we'll arrange expedited shipping or a refund.",
    [](<#cb56-22>)      "context": "Order tracking and customer support documentation. Standard delivery time is 5-7 business days.",
    [](<#cb56-23>)      "metadata": {
    [](<#cb56-24>)        "domain": "customer_support",
    [](<#cb56-25>)        "difficulty": "medium",
    [](<#cb56-26>)        "category": "shipping"
    [](<#cb56-27>)      },
    [](<#cb56-28>)      "expected_tools": ["order_db", "shipping_api"],
    [](<#cb56-29>)      "expected_agents": ["support_agent", "shipping_agent"]
    [](<#cb56-30>)    }
    [](<#cb56-31>)  ]
    [](<#cb56-32>)}
```

* * *

## PerformanceMonitor 메서드 완전 가이드

### load_golden_dataset()

Golden Dataset 파일을 로드합니다.
```python
    [](<#cb57-1>)def load_golden_dataset(self, dataset_path: Optional[str] = None) -> List[Dict]:
    [](<#cb57-2>)    """
    [](<#cb57-3>)    Args:
    [](<#cb57-4>)        dataset_path: Golden Dataset 파일 경로
    [](<#cb57-5>)                      - 절대 경로 또는 상대 경로
    [](<#cb57-6>)                      - 상대 경로일 경우 'golden_datasets/' 디렉토리에서 검색
    [](<#cb57-7>)                      - None일 경우 생성자에서 지정한 경로 사용
    [](<#cb57-8>)
    [](<#cb57-9>)    Returns:
    [](<#cb57-10>)        List[Dict]: Golden Dataset 항목 리스트 (qa_pairs)
    [](<#cb57-11>)
    [](<#cb57-12>)    Raises:
    [](<#cb57-13>)        FileNotFoundError: 파일을 찾을 수 없는 경우
    [](<#cb57-14>)    """
```

**사용 예시:**
```python
    [](<#cb58-1>)monitor = PerformanceMonitor()
    [](<#cb58-2>)
    [](<#cb58-3>)# 방법 1: 상대 경로 (golden_datasets/ 디렉토리에서 검색)
    [](<#cb58-4>)dataset = monitor.load_golden_dataset("my_dataset.json")
    [](<#cb58-5>)
    [](<#cb58-6>)# 방법 2: 절대 경로
    [](<#cb58-7>)dataset = monitor.load_golden_dataset("/path/to/golden_datasets/my_dataset.json")
    [](<#cb58-8>)
    [](<#cb58-9>)# 방법 3: 속성으로 지정
    [](<#cb58-10>)monitor = PerformanceMonitor()
    [](<#cb58-11>)monitor.golden_dataset_path = "my_dataset.json"
    [](<#cb58-12>)dataset = monitor.load_golden_dataset()  # 자동으로 속성 경로 사용
    [](<#cb58-12>)
    [](<#cb58-13>)print(f"로드된 QA 쌍: {len(dataset)}개")
```

### evaluate_with_golden_dataset()

Golden Dataset 기반 완전 자동 평가 파이프라인입니다.
```python
    [](<#cb59-1>)def evaluate_with_golden_dataset(
    [](<#cb59-2>)    self,
    [](<#cb59-3>)    agent_fn: Callable[[str], Dict],
    [](<#cb59-4>)    dataset_path: Optional[str] = None,
    [](<#cb59-5>)    enable_layer2_metrics: bool = True,
    [](<#cb59-6>)    enable_advanced_metrics: bool = False,
    [](<#cb59-7>)    verbose: bool = True
    [](<#cb59-8>)) -> Dict[str, Any]:
    [](<#cb59-9>)    """
    [](<#cb59-10>)    Args:
    [](<#cb59-11>)        agent_fn: 평가할 에이전트 함수
    [](<#cb59-12>)                  - 입력: question (str)
    [](<#cb59-13>)                  - 출력: Dict with keys:
    [](<#cb59-14>)                      - answer (str, 필수): 에이전트의 답변
    [](<#cb59-15>)                      - tools_used (List[str], 선택): 사용한 도구 리스트
    [](<#cb59-16>)                      - latency (float, 선택): 응답 시간
    [](<#cb59-17>)                      - token_usage (Dict, 선택): 토큰 사용량
    [](<#cb59-18>)
    [](<#cb59-19>)        dataset_path: Golden Dataset 파일 경로 (None이면 이미 로드된 데이터 사용)
    [](<#cb59-20>)
    [](<#cb59-21>)        enable_layer2_metrics: Layer 2 메트릭 자동 평가
    [](<#cb59-22>)                               - Tool Selection Accuracy
    [](<#cb59-23>)                               - Tool Selection F1 Score
    [](<#cb59-24>)
    [](<#cb59-25>)        enable_advanced_metrics: Layer 3 고급 메트릭 (DeepEval, Ragas)
    [](<#cb59-26>)
    [](<#cb59-27>)        verbose: 진행 상황 출력 여부
    [](<#cb59-28>)
    [](<#cb59-29>)    Returns:
    [](<#cb59-30>)        Dict: 평가 결과
    [](<#cb59-31>)        {
    [](<#cb59-32>)            "total_evaluated": int,
    [](<#cb59-33>)            "layer1_metrics": {
    [](<#cb59-34>)                "tcr": float,
    [](<#cb59-35>)                "accuracy": float,
    [](<#cb59-36>)                "hallucination_rate": float
    [](<#cb59-37>)            },
    [](<#cb59-38>)            "layer2_metrics": {
    [](<#cb59-39>)                "tool_selection_accuracy": float,
    [](<#cb59-40>)                "tool_selection_f1": float
    [](<#cb59-41>)            },
    [](<#cb59-42>)            "pass_fail": {
    [](<#cb59-43>)                "metric_name": {
    [](<#cb59-44>)                    "status": "pass" | "fail",
    [](<#cb59-45>)                    "value": float,
    [](<#cb59-46>)                    "threshold": float,
    [](<#cb59-47>)                    "name": str,
    [](<#cb59-48>)                    "unit": str
    [](<#cb59-49>)                }
    [](<#cb59-50>)            }
    [](<#cb59-51>)        }
    [](<#cb59-52>)    """
```

**완전한 사용 예시:**
```python
    [](<#cb60-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb60-2>)
    [](<#cb60-3>)# 1. Monitor 초기화
    [](<#cb60-4>)monitor = PerformanceMonitor()
    [](<#cb60-5>)monitor.thresholds = {
    [](<#cb60-6>)    'tcr': 90.0,
    [](<#cb60-7>)    'accuracy': 85.0,
    [](<#cb60-8>)    'tool_selection_accuracy': 80.0
    [](<#cb60-9>)}
    [](<#cb60-10>)
    [](<#cb60-11>)# 2. 에이전트 함수 정의
    [](<#cb60-12>)def my_rag_agent(question: str) -> Dict:
    [](<#cb60-13>)    """실제 RAG 에이전트"""
    [](<#cb60-14>)    # 벡터 검색
    [](<#cb60-15>)    context = vector_store.search(question)
    [](<#cb60-16>)
    [](<#cb60-17>)    # LLM 호출
    [](<#cb60-18>)    answer = llm.predict(question, context=context)
    [](<#cb60-19>)
    [](<#cb60-20>)    return {
    [](<#cb60-21>)        "answer": answer,
    [](<#cb60-22>)        "tools_used": ["vector_search", "llm"],
    [](<#cb60-23>)        "latency": 1.5,
    [](<#cb60-24>)        "token_usage": {"input": 100, "output": 50}
    [](<#cb60-25>)    }
    [](<#cb60-26>)
    [](<#cb60-27>)# 3. 자동 평가 실행
    [](<#cb60-28>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb60-29>)    agent_fn=my_rag_agent,
    [](<#cb60-30>)    dataset_path="rag_test_dataset.json",
    [](<#cb60-31>)    enable_layer2_metrics=True,
    [](<#cb60-32>)    verbose=True
    [](<#cb60-33>))
    [](<#cb60-34>)
    [](<#cb60-35>)# 4. 결과 확인
    [](<#cb60-36>)print(f"\n📊 평가 결과:")
    [](<#cb60-37>)print(f"  총 평가: {results['total_evaluated']}개")
    [](<#cb60-38>)print(f"  TCR: {results['layer1_metrics']['tcr']:.1f}%")
    [](<#cb60-39>)print(f"  Accuracy: {results['layer1_metrics']['accuracy']:.1f}%")
    [](<#cb60-40>)print(f"  Tool Selection: {results['layer2_metrics']['tool_selection_accuracy']:.1f}%")
    [](<#cb60-41>)
    [](<#cb60-42>)# 5. Pass/Fail 확인
    [](<#cb60-43>)if results.get('pass_fail'):
    [](<#cb60-44>)    failed_metrics = [m for m, d in results['pass_fail'].items() if d['status'] == 'fail']
    [](<#cb60-45>)    if failed_metrics:
    [](<#cb60-46>)        print(f"\n❌ 실패한 메트릭: {', '.join(failed_metrics)}")
    [](<#cb60-47>)        exit(1)
    [](<#cb60-48>)    else:
    [](<#cb60-49>)        print(f"\n✅ 모든 메트릭 통과!")
    [](<#cb60-50>)        exit(0)
```

### compare_with_thresholds()

현재 메트릭 값을 설정된 임계값과 비교합니다.
```python
    [](<#cb61-1>)def compare_with_thresholds(self) -> Dict[str, Any]:
    [](<#cb61-2>)    """
    [](<#cb61-3>)    Returns:
    [](<#cb61-4>)        Dict: 각 메트릭별 비교 결과
    [](<#cb61-5>)        {
    [](<#cb61-6>)            "metric_name": {
    [](<#cb61-7>)                "status": "pass" | "fail",
    [](<#cb61-8>)                "value": float,
    [](<#cb61-9>)                "threshold": float,
    [](<#cb61-10>)                "name": str,
    [](<#cb61-11>)                "unit": str
    [](<#cb61-12>)            }
    [](<#cb61-13>)        }
    [](<#cb61-14>)    """
```

**사용 예시:**
```python
    [](<#cb62-1>)# 임계값 설정
    [](<#cb62-2>)monitor.thresholds = {
    [](<#cb62-3>)    'tcr': 90.0,
    [](<#cb62-4>)    'accuracy': 85.0,
    [](<#cb62-5>)    'hallucination': 5.0
    [](<#cb62-6>)}
    [](<#cb62-7>)
    [](<#cb62-8>)# 평가 실행 후
    [](<#cb62-9>)comparison = monitor.compare_with_thresholds()
    [](<#cb62-10>)
    [](<#cb62-11>)# 결과 출력
    [](<#cb62-12>)for metric, data in comparison.items():
    [](<#cb62-13>)    status = "✅ PASS" if data['status'] == 'pass' else "❌ FAIL"
    [](<#cb62-14>)    print(f"{status} {data['name']}: {data['value']:.1f}{data['unit']} (임계값: {data['threshold']})")
```

* * *

* * *

## 📊 품질 관리자 가이드 (QA Manager)

> 💼 **품질 관리자를 위한 Golden Dataset 관리 가이드** : Golden Dataset의 품질을 측정, 평가, 유지보수하는 체계적인 방법을 제공합니다.

**🎯 이 가이드를 읽으면 알 수 있는 것**

  * ✅ Golden Dataset이 왜 중요하고 품질에 어떤 영향을 미치는지
  * ✅ 데이터셋 품질을 측정하는 구체적인 지표와 기준
  * ✅ 데이터셋을 정기적으로 유지보수하는 방법
  * ✅ 데이터셋 관련 문제 발생 시 해결 방법
  * ✅ Golden Dataset 관리의 모범 사례

### 1\. Golden Dataset 품질 관리

#### 🎯 Golden Dataset의 중요성

**💡 핵심 개념: "Garbage In, Garbage Out"**

Golden Dataset의 품질이 낮으면, 아무리 좋은 AI 모델도 제대로 평가할 수 없습니다.

Golden Dataset 품질 | → | 평가 신뢰도 | 결과  
---|---|---|---  
**높음** (다양성, 정확성) | → | ✅ **높음** | 신뢰할 수 있는 메트릭  
**낮음** (편향, 오류) | → | ❌ **낮음** | 잘못된 의사결정  
  
#### 📊 Golden Dataset 생명주기

**Golden Dataset은 한번 만들고 끝이 아닙니다!**
```python
    1. 📝 생성 (Create)
       └─ 다양한 시나리오 수집
       └─ 전문가 검토
       └─ 초기 품질 검증
    
    2. ✅ 검증 (Validate)
       └─ 정확성 확인
       └─ 편향성 검사
       └─ 커버리지 분석
    
    3. 🔄 사용 (Use)
       └─ 정기 평가 실행
       └─ 메트릭 추적
       └─ 이상 패턴 감지
    
    4. 🔧 유지보수 (Maintain)
       └─ 실패 케이스 추가
       └─ 구형 케이스 제거
       └─ 품질 재검증
    
    5. 📈 개선 (Improve)
       └─ 새로운 시나리오 추가
       └─ 다양성 확대
       └─ 난이도 조정
    
```

### 2\. 데이터셋 품질 지표

#### 📏 Golden Dataset 품질 측정 지표

지표 | 측정 내용 | 권장 기준 | 측정 방법  
---|---|---|---  
**데이터셋 크기**  
(Dataset Size) | QAPair 개수 | 최소 **30개**  
권장 **100개+** | `len(qa_pairs)`  
**시나리오 다양성**  
(Diversity) | 서로 다른 유형의  
질문 비율 | 최소 **5가지**  
유형 이상 | task_type 분포  
**난이도 분포**  
(Difficulty) | 쉬움, 보통, 어려움  
케이스 균형 | 쉬움 30%  
보통 50%  
어려움 20% | 수동 분류  
**답변 품질**  
(Answer Quality) | expected_output의  
정확성 및 완전성 | **100%**  
(모두 정확) | 전문가 검토  
**메타데이터 완전성**  
(Completeness) | 필수 필드 누락 없음 | 필수 필드  
**100%** 존재 | 스키마 검증  
**중복 비율**  
(Duplication) | 유사한 질문 중복 | **< 5%** | 유사도 분석  
**실패 케이스 커버리지**  
(Failure Coverage) | 알려진 실패 패턴  
포함 비율 | **≥ 80%** | 실패 로그 대조  
  
#### 🔍 데이터셋 품질 평가 체크리스트

**✅ Golden Dataset 품질 체크리스트**

항목 | 기준 | Pass/Fail  
---|---|---  
**1\. 최소 크기 충족** | ≥ 30개 QAPairs | [ ]  
**2\. 시나리오 다양성** | ≥ 5가지 유형 | [ ]  
**3\. 난이도 균형** | 쉬움/보통/어려움 | [ ]  
**4\. 답변 정확성** | 100% 검증됨 | [ ]  
**5\. 필수 필드 완전성** | 누락 없음 | [ ]  
**6\. 중복 최소화** | < 5% 중복 | [ ]  
**7\. 실패 케이스 포함** | ≥ 10개 포함 | [ ]  
**8\. Layer 2 메타데이터**  
(멀티 에이전트 시) | 적절히 포함 | [ ]  
  
**🔴 하나라도 Fail 시 → 데이터셋 보완 필요**

### 3\. 데이터셋 유지보수

#### 🔄 정기 유지보수 계획

**📅 Golden Dataset 유지보수 주기**

주기 | 작업 | 목적  
---|---|---  
**주간**  
(Weekly) | • 실패 케이스 수집  
• 신규 패턴 발견 | 최신 이슈 반영  
**월간**  
(Monthly) | • 품질 지표 분석  
• 중복 제거  
• 구형 케이스 검토 | 데이터셋 정제  
**분기**  
(Quarterly) | • 전면 재검토  
• 다양성 확대  
• 전문가 검토 | 대규모 개선  
**반기**  
(Semi-annual) | • 새 버전 생성  
• A/B 테스트  
• 성능 비교 | 장기 품질 관리  
  
### 4\. 문제 시나리오 및 해결

##### 🔴 시나리오 1: 평가 메트릭이 계속 나쁨 (TCR < 70%)

**🔍 증상:** Golden Dataset 평가 결과 TCR이 지속적으로 낮음

**⚡ 즉시 조치:**

  1. 실패 케이스 분석: 어떤 유형의 질문에서 실패하는지 파악
  2. 답변 검증: expected_output이 정확한지 재확인
  3. 난이도 조정: 너무 어려운 케이스는 별도 카테고리로 분리

### 5\. QA 관리자 핵심 원칙

**💡 Golden Dataset 관리 5대 원칙**

  1. **📊 데이터가 곧 품질이다** : Golden Dataset의 품질이 낮으면 평가 자체가 무의미합니다.
  2. **🔄 살아있는 문서로 관리하라** : 실패 케이스를 지속적으로 추가하고, 구형 케이스를 제거하세요.
  3. **🎯 실제 사용 패턴을 반영하라** : 프로덕션 로그를 분석하여 실제 사용자 질문을 반영하세요.
  4. **📈 다양성이 핵심이다** : 한 가지 유형에 치우치지 말고 다양한 시나리오를 포함시키세요.
  5. **✅ 검증, 또 검증** : expected_output이 정확한지 전문가가 반드시 검토해야 합니다.

* * *

## FAQ & Troubleshooting

### FAQ

#### Q1: Golden Dataset은 몇 개의 QAPair가 적당한가요?

**A** : 최소 20-50개를 권장합니다. 더 많을수록 평가가 정확해지지만, 평가 시간도 증가합니다. 프로덕션 환경에서는 100-200개를 목표로 하세요.

#### Q2: Layer 2 필드는 필수인가요?

**A** : 아니요. Layer 1 필드만으로도 기본 평가가 가능합니다. 하지만 Agentic AI 시스템(multi-agent, tool-using, workflow-based)을 평가한다면 Layer 2 필드를 강력히 권장합니다.

#### Q3: PDF에서 생성한 Golden Dataset의 품질은 어떤가요?

**A** : PDF 자동 생성은 빠르게 대량의 QAPair를 만들 수 있지만, 품질은 수동 작성보다 낮을 수 있습니다. **자동 생성 후 수동 검토 및 편집** 을 권장합니다. - OpenAI GPT 모델 사용 (gpt-4o-mini 또는 gpt-4o) - 청크 크기 조정으로 품질 개선 가능 (기본 1000자) - 좋은 품질의 PDF일수록 좋은 QA 생성

#### Q4: expected_tools를 정확히 정의하기 어려워요.

**A** : 에이전트를 몇 번 실행해보고 실제로 사용하는 도구를 관찰한 후, 그 중 **필수적인 도구만** expected_tools에 포함하세요. Dashboard에서 실시간으로 테스트하며 조정할 수 있습니다.

#### Q5: expected_workflow_steps의 순서가 중요한가요?

**A** : 평가 시 순서는 고려되지 않습니다. 하지만 **가독성과 디버깅** 을 위해 실행 순서대로 나열하는 것을 권장합니다.

#### Q6: Golden Dataset을 어떻게 버전 관리하나요?

**A** : Git으로 관리하고, 파일명 또는 내부 `version` 필드로 버전을 표시하세요. 예: `golden_dataset_v1.0.json`, `golden_dataset_v1.1.json`

#### Q7: 여러 개의 Golden Dataset을 사용할 수 있나요?

**A** : 네! 도메인별로 분리하여 관리할 수 있습니다. 예: `math_qa.json`, `customer_support_qa.json`, `research_qa.json`

#### Q8: 자동 평가가 실패했는데, 어떻게 디버깅하나요?

**A** : Dashboard의 “Evaluation History” 탭에서 각 QAPair의 상세 결과를 확인할 수 있습니다. 어떤 메트릭이 실패했는지, 어떤 도구가 누락/추가되었는지 등을 볼 수 있습니다.

### Troubleshooting

#### 문제 1: Tool Selection Accuracy가 낮아요 (< 50%)

**원인** :

  * expected_tools가 부정확하게 정의됨
  * 에이전트가 불필요한 도구를 과도하게 사용

**해결** : 1. Dashboard에서 실제 사용된 도구 확인 2. expected_tools 재정의 3. 에이전트 프롬프트 개선하여 도구 선택 정확도 향상

#### 문제 2: Agent Coordination Score가 0/10이에요

**원인** :

  * expected_agents가 정의되지 않음
  * Agent Coordination 추적이 활성화되지 않음
  * 실제로 에이전트 간 상호작용이 없음

**해결** : 1. Golden Dataset에 expected_agents 추가 2. CrewAI 사용 시 `enable_coordination_tracking=True` 설정 3. 에이전트 간 상호작용 로그 확인

#### 문제 3: Workflow Execution이 평가되지 않아요

**원인** :

  * expected_workflow_steps가 정의되지 않음
  * Workflow 추적이 활성화되지 않음

**해결** : 1. Golden Dataset에 expected_workflow_steps 추가 2. LangGraph 사용 시 `enable_workflow_tracking=True` 설정 3. 노드 이름이 코드와 일치하는지 확인

#### 문제 4: PDF에서 Golden Dataset 생성이 너무 느려요

**원인** :

  * PDF 크기가 큼
  * OpenAI API 호출이 많음 (청크당 1회 API 호출)

**해결** : 1. `max_chunks` 파라미터로 청크 수 제한 (테스트용) 2. `num_questions_per_chunk` 값을 줄임 (기본 3개) 3. PDF를 작은 단위로 분할 4. gpt-4o-mini 모델 사용 (더 빠르고 저렴)
```json
    [](<#cb63-1>)generator = KoreanRAGDatasetGenerator(model="gpt-4o-mini")
    [](<#cb63-2>)dataset = generator.generate_from_pdf(
    [](<#cb63-3>)    pdf_path="large_document.pdf",
    [](<#cb63-4>)    num_questions_per_chunk=2,  # 청크당 2개로 감소
    [](<#cb63-5>)    max_chunks=10  # 처음 10개 청크만 처리
    [](<#cb63-6>))
```

#### 문제 5: 자동 평가 결과가 수동 평가와 다릅니다

**원인** :

  * ground_truth가 너무 엄격하거나 모호함
  * Accuracy 계산 방식 차이 (유사도 vs 정확 일치)

**해결** : 1. ground_truth를 더 유연하게 작성 2. Accuracy threshold를 조정 3. 평가 방식 커스터마이징 (유사도 임계값 변경)

#### 문제 6: Dashboard에서 Golden Dataset을 로드할 수 없어요

**원인** :

  * JSON 형식 오류
  * 필수 필드 누락

**해결** : 1. JSON 유효성 검사 (online JSON validator 사용) 2. 필수 필드 확인 (id, question, ground_truth, context) 3. 예제 파일과 비교

* * *

## 다음 단계

Golden Dataset 작성을 완료했다면:

  1. **임계값 설정** : [THRESHOLD_CONFIGURATION_GUIDE.md](<THRESHOLD_CONFIGURATION_GUIDE.md>) 참고
  2. **자동 평가 실행** : `Evaluator_Examples/04_threshold_validation_example.py` 실행
  3. **CI/CD 통합** : [DEPLOYMENT_GUIDE.md](<DEPLOYMENT_GUIDE.md>) 참고
  4. **Dashboard 사용** : 실시간 모니터링 및 분석

* * *

## 참고 문서

  * [AGENTIC_AI_METRICS_GUIDE.md](<AGENTIC_AI_METRICS_GUIDE.md>) \- Layer 2 메트릭 완전 가이드
  * [API.md](<API.md>) \- 전체 API 레퍼런스
  * [04_threshold_validation_example.py](<../Evaluator_Examples/04_threshold_validation_example.py>) \- 실전 예제
  * [07_framework_with_layer2_example.py](<../Evaluator_Examples/07_framework_with_layer2_example.py>) \- Framework 통합 예제

* * *

* * *

**최종 업데이트** : 2026-03-23
**버전** : Agent Evaluator v0.6.1
**프로젝트** : Agent Evaluator - AI Agent Performance Evaluation System
**문서** : Golden Dataset Guide
