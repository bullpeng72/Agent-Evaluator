# 🇰🇷 한국어 RAG 평가 가이드

한국어 특화 RAG 시스템 평가 및 최적화 (Agent Evaluator v0.7.2)

# 한국어 RAG 평가 가이드

> Golden Dataset 생성 및 RAG 시스템 평가 완벽 가이드

## 목차

  1. [개요](<#개요>)
  2. [설치](<#설치>)
  3. [Golden Dataset 생성](<#golden-dataset-생성>)
  4. [RAG 시스템 평가](<#rag-시스템-평가>)
  5. [평가 메트릭](<#평가-메트릭>)
  6. [고급 사용법](<#고급-사용법>)
  7. [실전 예제: 기업 정책 문서 평가](<#실전-예제-기업-정책-문서-평가>)
  8. [💻 개발자 가이드 (Developer Guide)](<#dev-guide>)
     * [8.1 RAG 시스템 통합](<#dev-integration>)
     * [8.2 커스텀 메트릭 개발](<#dev-custom-metrics>)
     * [8.3 성능 최적화](<#dev-performance>)
     * [8.4 프로덕션 배포](<#dev-production>)
     * [8.5 문제 해결](<#dev-troubleshooting>)
  9. [FAQ](<#faq>)
  10. [구현 세부사항](<#구현-세부사항>)
  11. [추가 리소스](<#추가-리소스>)

* * *

## 개요

이 시스템은 기업 환경에서 한국어 RAG (Retrieval-Augmented Generation) 시스템을 평가하기 위한 완전한 솔루션을 제공합니다.

### 주요 기능

  * **📄 PDF에서 Ground Truth 자동 생성** : OpenAI GPT를 활용하여 한국어 PDF 문서에서 QA 쌍 자동 생성
  * **📊 표준 RAG 메트릭 평가** : Faithfulness, Context Recall, Context Precision, Answer Relevancy, Answer Similarity
  * **💾 다양한 입력/출력 형식** : JSON, CSV 지원
  * **🔧 유연한 통합** : RAGSystemInterface를 통한 기존 RAG 시스템과의 쉬운 통합
  * **🔍 고급 평가** : HybridPerformanceMonitor를 통한 심층 분석 (선택적)

### 워크플로우

graph LR A["📄 한국어 PDF  
문서 입력"] B["🤖 Golden Dataset 생성  
━━━━━━━━━━━━━━━  
• AI 기반 QA 쌍 생성  
• 질문/답변/컨텍스트  
• Ground Truth 포함"] C["💾 저장  
JSON/CSV 형식"] D["📊 RAG 시스템 평가  
━━━━━━━━━━━━━━━  
• Faithfulness  
• Context Recall  
• Context Precision  
• Answer Relevancy"] E["📈 평가 리포트 생성  
결과 분석 및 시각화"] A --> B B --> C C --> D D --> E style A fill:#e3f2fd,stroke:#2196f3,stroke-width:3px style B fill:#fff3e0,stroke:#ff9800,stroke-width:3px style C fill:#f3e5f5,stroke:#9c27b0,stroke-width:3px style D fill:#e8f5e9,stroke:#4caf50,stroke-width:3px style E fill:#fce4ec,stroke:#e91e63,stroke-width:3px 

* * *

## 설치

### 1\. 기본 설치
```bash
    [](<#cb2-1>)# Agent Evaluator 프로젝트 클론
    [](<#cb2-2>)# 프로젝트 디렉토리로 이동
    [](<#cb2-3>)cd Agent_Evaluator
    [](<#cb2-4>)
    [](<#cb2-5>)# Conda 환경 생성 (권장)
    [](<#cb2-6>)conda create -n agent_evaluator python=3.11
    [](<#cb2-7>)conda activate agent_evaluator
    [](<#cb2-8>)
    [](<#cb2-9>)# 의존성 설치
    [](<#cb2-10>)pip install -r requirements.txt
```

### 2\. 필수 라이브러리
```bash
    [](<#cb3-1>)# 코어 의존성 (필수)
    [](<#cb3-2>)pip install agent-evaluator[serve]
    [](<#cb3-3>)
    [](<#cb3-4>)# Golden Dataset 생성용
    [](<#cb3-5>)pip install pypdf openai python-dotenv
    [](<#cb3-6>)
    [](<#cb3-7>)# RAG 평가용 (Ragas)
    [](<#cb3-8>)pip install ragas langchain-openai datasets
    [](<#cb3-9>)
    [](<#cb3-10>)# 선택: PDF 추출 개선 (pypdf 대안)
    [](<#cb3-11>)pip install pdfplumber
    [](<#cb3-12>)
    [](<#cb3-13>)# 선택: DeepEval 고급 메트릭
    [](<#cb3-14>)pip install deepeval
```

**라이브러리 선택 가이드** :

  * **pypdf** : 기본 PDF 텍스트 추출 (빠름)
  * **pdfplumber** : 더 정확한 텍스트 추출 (권장, 특히 복잡한 레이아웃)
  * **ragas** : RAG 메트릭 계산 필수 (Faithfulness, Context Recall 등)
  * **deepeval** : 추가 메트릭 (G-Eval, Hallucination, Toxicity) - 선택적

### 3\. 환경 변수 설정
```json
    [](<#cb4-1>)# .env 파일 생성
    [](<#cb4-2>)cat > .env << EOF
    [](<#cb4-3>)OPENAI_API_KEY=your-openai-api-key-here
    [](<#cb4-4>)EOF
```

* * *

## Golden Dataset 생성

### 방법 1: PDF에서 자동 생성

가장 일반적인 방법으로, 한국어 PDF 문서에서 AI를 활용하여 QA 쌍을 자동으로 생성합니다.
```python
    [](<#cb5-1>)from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator
    [](<#cb5-2>)
    [](<#cb5-3>)# 1. Generator 초기화
    [](<#cb5-4>)generator = KoreanRAGDatasetGenerator(
    [](<#cb5-5>)    model="gpt-4o-mini",        # 또는 "gpt-4o" (더 비싸지만 품질 좋음)
    [](<#cb5-6>)    chunk_size=800,             # 청크 크기 (문자 수)
    [](<#cb5-7>)    chunk_overlap=150,          # 청크 간 겹침
    [](<#cb5-8>)    output_dir="golden_datasets"
    [](<#cb5-9>))
    [](<#cb5-10>)
    [](<#cb5-11>)# 2. PDF에서 Golden Dataset 생성
    [](<#cb5-12>)dataset = generator.generate_from_pdf(
    [](<#cb5-13>)    pdf_path="company_policy.pdf",       # PDF 경로
    [](<#cb5-14>)    num_questions_per_chunk=3,           # 청크당 질문 수
    [](<#cb5-15>)    question_types=["factual", "reasoning", "summary"],  # 질문 유형
    [](<#cb5-16>)    save_format="json",                  # "json" 또는 "csv"
    [](<#cb5-17>)    max_chunks=None                      # None이면 전체, 숫자면 테스트용
    [](<#cb5-18>))
```

#### 생성 프로세스

  1. **PDF 텍스트 추출** : 
     * `KoreanPDFExtractor` 클래스 사용
     * pypdf 또는 pdfplumber 자동 선택 (설치된 것 사용)
     * pdfplumber가 우선 (더 정확한 추출)
  2. **텍스트 정제** : 
     * `clean_text()` 메서드로 불필요한 공백 제거
     * 연속된 줄바꿈 정리
  3. **텍스트 청킹** : 
     * `TextChunker` 클래스 사용
     * 의미 단위로 분할 (문장 경계 자동 탐지)
     * 한국어 문장 부호 고려: `. ! ? 。！？`
     * chunk_overlap으로 컨텍스트 유지
  4. **QA 쌍 생성** : 
     * `KoreanQAGenerator` 클래스 사용
     * OpenAI GPT로 각 청크마다 질문-답변-ground_truth 생성
     * 메타 정보 질문 자동 필터링 (페이지 번호, 문서 구조 등)
     * 실용적인 질문만 생성 (factual, reasoning, summary)
  5. **검증 및 저장** : 
     * `GoldenDatasetManager`로 품질 검증
     * 필수 필드 체크 (질문, 답변, ground_truth, context)
     * 길이 검증 (너무 짧은 답변 경고)
     * JSON/CSV 형식으로 저장 (utf-8-sig for Excel)

#### 출력 예시
```json
    [](<#cb6-1>){
    [](<#cb6-2>)  "dataset_id": "dataset_abc12345",
    [](<#cb6-3>)  "source_document": "company_policy.pdf",
    [](<#cb6-4>)  "created_at": "2024-01-15T10:30:00",
    [](<#cb6-5>)  "total_qa_pairs": 45,
    [](<#cb6-6>)  "qa_pairs": [
    [](<#cb6-7>)    {
    [](<#cb6-8>)      "qa_id": "chunk_p1_i0_qa0",
    [](<#cb6-9>)      "question": "회사의 연차 휴가 정책은 어떻게 되나요?",
    [](<#cb6-10>)      "answer": "직원은 1년 근무 시 15일의 연차 휴가를 받을 수 있으며...",
    [](<#cb6-11>)      "context": "당사의 연차 휴가 정책에 따르면...",
    [](<#cb6-12>)      "ground_truth": "1년 근무 시 15일의 연차 휴가",
    [](<#cb6-13>)      "metadata": {
    [](<#cb6-14>)        "chunk_id": "chunk_p1_i0_abc123",
    [](<#cb6-15>)        "page_number": 1
    [](<#cb6-16>)      }
    [](<#cb6-17>)    }
    [](<#cb6-18>)  ]
    [](<#cb6-19>)}
```

### 방법 2: 수동으로 Golden Data 입력

기존 데이터나 전문가가 직접 작성한 QA 쌍을 사용할 수 있습니다.
```python
    [](<#cb7-1>)from agent_evaluator.datasets.korean_rag_dataset_generator import (
    [](<#cb7-2>)    QAPair, GoldenDataset, GoldenDatasetManager
    [](<#cb7-3>))
    [](<#cb7-4>)from datetime import datetime
    [](<#cb7-5>)
    [](<#cb7-6>)# 1. QA 쌍 수동 생성
    [](<#cb7-7>)qa_pairs = [
    [](<#cb7-8>)    QAPair(
    [](<#cb7-9>)        qa_id="manual_001",
    [](<#cb7-10>)        question="기업의 주요 제품은 무엇인가요?",
    [](<#cb7-11>)        answer="스마트폰, 태블릿, 웨어러블 기기입니다.",
    [](<#cb7-12>)        context="당사는 스마트폰, 태블릿, 웨어러블 기기를 주력 제품으로...",
    [](<#cb7-13>)        ground_truth="스마트폰, 태블릿, 웨어러블 기기",
    [](<#cb7-14>)        metadata={"source": "company_info"}
    [](<#cb7-15>)    ),
    [](<#cb7-16>)    # ... 더 많은 QA 쌍
    [](<#cb7-17>)]
    [](<#cb7-18>)
    [](<#cb7-19>)# 2. Golden Dataset 생성
    [](<#cb7-20>)dataset = GoldenDataset(
    [](<#cb7-21>)    dataset_id="manual_dataset",
    [](<#cb7-22>)    source_document="manual_input",
    [](<#cb7-23>)    created_at=datetime.now().isoformat(),
    [](<#cb7-24>)    total_qa_pairs=len(qa_pairs),
    [](<#cb7-25>)    qa_pairs=qa_pairs,
    [](<#cb7-26>)    metadata={"input_type": "manual"}
    [](<#cb7-27>))
    [](<#cb7-28>)
    [](<#cb7-29>)# 3. 저장
    [](<#cb7-30>)manager = GoldenDatasetManager()
    [](<#cb7-31>)saved_path = manager.save_dataset(dataset, format="json")
```

### 방법 3: CSV 파일에서 로드

Excel이나 스프레드시트에서 작성한 데이터를 사용할 수 있습니다.

#### CSV 형식
```python
    qa_id,question,answer,ground_truth,context,chunk_id,page_number,generated_at
    qa_001,회사 설립 연도는?,2010년에 설립되었습니다,2010년,당사는 2010년에 설립되어...,chunk_001,1,2024-01-15
    qa_002,직원 수는?,약 500명입니다,약 500명,현재 약 500명의 직원이...,chunk_002,1,2024-01-15
```

#### 로드 코드
```python
    [](<#cb9-1>)from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager
    [](<#cb9-2>)
    [](<#cb9-3>)manager = GoldenDatasetManager()
    [](<#cb9-4>)dataset = manager.load_dataset("golden_datasets/my_dataset.csv")
    [](<#cb9-5>)
    [](<#cb9-6>)print(f"로드 완료: {dataset.total_qa_pairs}개 QA 쌍")
```

* * *

## RAG 시스템 평가

### 1\. RAG 시스템 인터페이스 구현

평가를 위해 RAG 시스템을 `RAGSystemInterface`에 맞춰 구현해야 합니다.

**중요** : `query()` 메서드만 구현하면 됩니다. 반환 타입은 `RAGResponse`입니다.
```python
    [](<#cb10-1>)from agent_evaluator.datasets.korean_rag_evaluator import RAGSystemInterface, RAGResponse
    [](<#cb10-2>)
    [](<#cb10-3>)class MyRAGSystem(RAGSystemInterface):
    [](<#cb10-4>)    """사용자의 RAG 시스템"""
    [](<#cb10-5>)
    [](<#cb10-6>)    def __init__(self):
    [](<#cb10-7>)        # 벡터 DB, LLM 등 초기화
    [](<#cb10-8>)        self.vector_db = ...  # Chroma, Pinecone, Qdrant 등
    [](<#cb10-9>)        self.llm = ...        # OpenAI, Anthropic, local model 등
    [](<#cb10-10>)
    [](<#cb10-11>)    def query(self, question: str) -> RAGResponse:
    [](<#cb10-12>)        """
    [](<#cb10-13>)        RAG 쿼리 실행 - 필수 구현 메서드
    [](<#cb10-14>)
    [](<#cb10-15>)        Args:
    [](<#cb10-16>)            question: 사용자 질문
    [](<#cb10-17>)
    [](<#cb10-18>)        Returns:
    [](<#cb10-19>)            RAGResponse: 답변 및 검색된 컨텍스트
    [](<#cb10-20>)        """
    [](<#cb10-21>)        # 1. 벡터 검색
    [](<#cb10-22>)        retrieved_docs = self.vector_db.search(question, top_k=3)
    [](<#cb10-23>)
    [](<#cb10-24>)        # 2. LLM으로 답변 생성
    [](<#cb10-25>)        answer = self.llm.generate(
    [](<#cb10-26>)            prompt=self._build_prompt(question, retrieved_docs)
    [](<#cb10-27>)        )
    [](<#cb10-28>)
    [](<#cb10-29>)        # 3. 응답 반환 (필수: question, answer, retrieved_contexts)
    [](<#cb10-30>)        return RAGResponse(
    [](<#cb10-31>)            question=question,
    [](<#cb10-32>)            answer=answer,
    [](<#cb10-33>)            retrieved_contexts=retrieved_docs,  # List[str] 형태
    [](<#cb10-34>)            metadata={"num_retrieved": len(retrieved_docs)}  # 선택적
    [](<#cb10-35>)        )
    [](<#cb10-36>)
    [](<#cb10-37>)    def _build_prompt(self, question: str, contexts: list) -> str:
    [](<#cb10-38>)        """프롬프트 생성 헬퍼 메서드"""
    [](<#cb10-39>)        context_text = "\n\n".join(contexts)
    [](<#cb10-40>)        return f"""다음 문서를 참고하여 질문에 답변하세요.
    [](<#cb10-41>)
    [](<#cb10-42>)[문서]
    [](<#cb10-43>){context_text}
    [](<#cb10-44>)
    [](<#cb10-45>)[질문]
    [](<#cb10-46>){question}
    [](<#cb10-47>)
    [](<#cb10-48>)[답변]
    [](<#cb10-49>)"""
```

**RAGResponse 필드** :

  * `question` (str): 질문
  * `answer` (str): 생성된 답변
  * `retrieved_contexts` (List[str]): 검색된 컨텍스트 리스트
  * `metadata` (Dict[str, Any]): 추가 정보 (선택적)

### 2\. 평가 실행
```python
    [](<#cb11-1>)from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator
    [](<#cb11-2>)from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager
    [](<#cb11-3>)
    [](<#cb11-4>)# 1. Golden Dataset 로드
    [](<#cb11-5>)manager = GoldenDatasetManager()
    [](<#cb11-6>)dataset = manager.load_dataset("golden_datasets/my_dataset.json")
    [](<#cb11-7>)
    [](<#cb11-8>)# 2. RAG 시스템 초기화
    [](<#cb11-9>)rag_system = MyRAGSystem()
    [](<#cb11-10>)
    [](<#cb11-11>)# 3. 평가기 초기화
    [](<#cb11-12>)evaluator = KoreanRAGEvaluator(
    [](<#cb11-13>)    rag_system=rag_system,
    [](<#cb11-14>)    use_ragas=True,              # Ragas 메트릭 사용 (필수)
    [](<#cb11-15>)    ragas_model="gpt-4o-mini",   # 평가에 사용할 모델
    [](<#cb11-16>)    output_dir="evaluation_results"
    [](<#cb11-17>))
    [](<#cb11-18>)
    [](<#cb11-19>)# 4. 평가 실행
    [](<#cb11-20>)report = evaluator.evaluate_dataset(
    [](<#cb11-21>)    dataset,
    [](<#cb11-22>)    use_hybrid_monitor=False,  # Hybrid Monitor 사용 여부 (고급)
    [](<#cb11-23>)    max_samples=None            # None이면 전체 평가, 숫자면 샘플링
    [](<#cb11-24>))
```

**평가 프로세스** :

  1. **Golden Dataset의 각 QA 쌍에 대해** : 
     * RAG 시스템에 질문 전송 (`rag_system.query()`)
     * 생성된 답변과 컨텍스트 수집
  2. **Ragas 메트릭 계산** : 
     * 각 QA에 대해 5가지 메트릭 계산
     * `EvaluationDataset` / `SingleTurnSample`로 변환하여 ragas 0.4.x API 호출
  3. **결과 집계 및 리포트 생성** : 
     * 평균, 최소, 최대 값 계산
     * JSON/CSV로 결과 저장

### 3\. 평가 결과
```
    ================================================================================
    📊 RAG 평가 리포트
    ================================================================================
    
    리포트 ID: a1b2c3d4
    평가 시간: 2024-01-15T11:30:00
    Dataset: dataset_abc12345
    소스 문서: company_policy.pdf
    
    ================================================================================
    평가 결과 요약
    ================================================================================
    
    총 QA 쌍: 45개
    성공: 43개
    실패: 2개
    성공률: 95.6%
    
    ================================================================================
    Ragas 메트릭 (평균)
    ================================================================================
    
    ✓ Faithfulness       : 0.892 (목표: 0.8)
    ✓ Answer Relevancy   : 0.856 (목표: 0.8)
    ✓ Context Recall     : 0.834 (목표: 0.8)
    ✓ Context Precision  : 0.878 (목표: 0.8)
    ✓ Answer Similarity  : 0.823 (목표: 0.8)
    
    ================================================================================
    통계
    ================================================================================
    
    총 평가 시간: 125.34초
    평균 평가 시간: 2.78초/개
    Faithfulness 범위: 0.654 ~ 0.987
    Answer Relevancy 범위: 0.712 ~ 0.945
    
    ================================================================================
```

* * *

## 평가 메트릭

### Faithfulness (충실도)

**정의** : 생성된 답변이 검색된 컨텍스트에 얼마나 충실한지 측정 (환각 방지)

**계산 방법** (Ragas 내부): 1. LLM이 답변에서 주장(claims)들을 추출 2. 각 주장이 검색된 컨텍스트에서 뒷받침되는지 검증 3\. `(뒷받침된 주장 수) / (전체 주장 수)` 계산

**목표** : ≥ 0.8

**개선 방법** :

  * RAG 프롬프트에 "문서에 없는 내용은 답변하지 말 것" 명시
  * 답변 생성 시 temperature를 낮춤 (0.1-0.3)
  * 검색된 컨텍스트의 품질과 관련성 향상

**실제 구현** : `korean_rag_evaluator.py`의 `_calculate_ragas_metrics()`에서 `ragas.metrics.faithfulness` 사용

### Answer Relevancy (답변 관련성)

**정의** : 답변이 질문과 얼마나 관련있는지 측정

**계산 방법** (Ragas 내부): 1. 생성된 답변에서 LLM이 역으로 질문들을 생성 2. 생성된 질문들과 원래 질문의 임베딩 유사도 계산 3\. 평균 코사인 유사도 반환

**목표** : ≥ 0.8

**개선 방법** :

  * 프롬프트에 질문에 직접 답하도록 명시
  * 불필요한 부가 정보 제거
  * 질문의 핵심 키워드를 답변에 포함

**실제 구현** : `ragas.metrics.answer_relevancy` 사용

### Context Recall (컨텍스트 재현율)

**정의** : Ground truth를 생성하는 데 필요한 정보가 검색된 컨텍스트에 얼마나 포함되어 있는지 측정

**계산 방법** (Ragas 내부): 1. Ground truth를 문장들로 분리 2. 각 문장이 검색된 컨텍스트에서 추론 가능한지 LLM으로 검증 3. `(추론 가능한 문장 수) / (전체 문장 수)` 계산

**목표** : ≥ 0.8

**개선 방법** :

  * 검색 top_k 값 증가 (더 많은 컨텍스트 검색)
  * 벡터 임베딩 모델 개선 (multilingual 모델 사용)
  * 청크 크기 조정 (더 큰 청크로 컨텍스트 확보)
  * 하이브리드 검색 (벡터 + 키워드) 사용

**실제 구현** : `ragas.metrics.context_recall` 사용

### Context Precision (컨텍스트 정밀도)

**정의** : 검색된 컨텍스트가 질문에 얼마나 관련 있는지 측정 (노이즈 최소화)

**계산 방법** (Ragas 내부): 1. 검색된 각 컨텍스트가 Ground truth와 관련 있는지 LLM으로 판단 2. 관련 있는 컨텍스트들의 순위 기반 정밀도 계산 3. Precision@K를 평균하여 반환

**목표** : ≥ 0.8

**개선 방법** :

  * 리랭킹(reranking) 모델 추가 (Cohere Rerank, cross-encoder 등)
  * 검색 쿼리 개선 (쿼리 확장, HyDE 등)
  * 필터링 로직 추가 (관련성 임계값 설정)
  * 메타데이터 필터링 활용

**실제 구현** : `ragas.metrics.context_precision` 사용

### Answer Similarity (답변 유사도)

**정의** : 생성된 답변이 Ground truth와 얼마나 의미적으로 유사한지 측정

**계산 방법** (Ragas 내부): 1. 생성된 답변과 Ground truth의 임베딩 생성 2. 코사인 유사도 계산 3. 0~1 범위의 유사도 점수 반환

**목표** : ≥ 0.8

**개선 방법** :

  * 프롬프트 개선 (더 명확한 지시)
  * Few-shot 예시 추가
  * Ground truth 품질 개선 (더 구체적이고 완전하게)
  * Fine-tuning 고려 (도메인 특화)

**실제 구현** : `ragas.metrics.answer_similarity` 사용

**참고** : 모든 메트릭은 `korean_rag_evaluator.py`의 `_calculate_ragas_metrics()` 메서드에서 계산되며, 각 QA 쌍에 대해 개별적으로 평가된 후 평균이 리포트에 포함됩니다.

* * *

## 고급 사용법

### 1\. 커스텀 질문 유형
```json
    [](<#cb13-1>)generator = KoreanRAGDatasetGenerator(...)
    [](<#cb13-2>)
    [](<#cb13-3>)dataset = generator.generate_from_pdf(
    [](<#cb13-4>)    pdf_path="document.pdf",
    [](<#cb13-5>)    num_questions_per_chunk=5,
    [](<#cb13-6>)    question_types=["factual", "reasoning", "summary", "comparison", "opinion"],
    [](<#cb13-7>)    ...
    [](<#cb13-8>))
```

**질문 유형** :

  * `factual`: 사실 확인 질문
  * `reasoning`: 추론 질문
  * `summary`: 요약 질문
  * `comparison`: 비교 질문
  * `opinion`: 의견 질문

### 2\. 청크 크기 최적화

청크 크기는 텍스트 검색 품질과 QA 생성 품질에 직접 영향을 미칩니다.
```json
    [](<#cb14-1>)# 짧은 청크 (세밀한 정보, 빠른 검색)
    [](<#cb14-2>)generator = KoreanRAGDatasetGenerator(
    [](<#cb14-3>)    chunk_size=500,
    [](<#cb14-4>)    chunk_overlap=100
    [](<#cb14-5>))
    [](<#cb14-6>)
    [](<#cb14-7>)# 중간 청크 (균형잡힌 설정) - 기본값
    [](<#cb14-8>)generator = KoreanRAGDatasetGenerator(
    [](<#cb14-9>)    chunk_size=1000,
    [](<#cb14-10>)    chunk_overlap=200
    [](<#cb14-11>))
    [](<#cb14-12>)
    [](<#cb14-13>)# 긴 청크 (풍부한 맥락)
    [](<#cb14-14>)generator = KoreanRAGDatasetGenerator(
    [](<#cb14-15>)    chunk_size=1500,
    [](<#cb14-16>)    chunk_overlap=300
    [](<#cb14-17>))
```

**권장 설정** (문자 수 기준):

  * **기술 문서** : 800-1000자 (코드 예제, API 설명 등)
  * **정책/법률** : 1000-1500자 (복잡한 조항, 절차 등)
  * **일반 문서** : 600-800자 (뉴스, 블로그 등)
  * **FAQ/간단한 정보** : 400-600자

**청크 크기 선택 가이드** :

  * **작은 청크 (400-600자)** : 
    * 장점: 정확한 검색, 빠른 처리
    * 단점: 맥락 손실, 문장이 잘림 가능
    * 사용: 간단한 사실 기반 QA
  * **중간 청크 (800-1200자)** : 
    * 장점: 맥락과 정확도 균형
    * 단점: 특별한 단점 없음
    * 사용: 대부분의 경우 (권장)
  * **큰 청크 (1200-1800자)** : 
    * 장점: 풍부한 맥락, 복잡한 추론 가능
    * 단점: 노이즈 증가, 느린 처리
    * 사용: 복잡한 문서, 긴 설명이 필요한 경우

**overlap 설정** :

  * 일반적으로 chunk_size의 15-25%
  * 예:
chunk_size=1000 → overlap=150-250 - 너무 작으면 맥락 손실, 너무 크면 중복 증가 

**실제 구현** : `TextChunker` 클래스에서 한국어 문장 부호(`. ! ? 。！？`)를 기준으로 청크 경계 조정

### 3\. 배치 평가
``` [](<#cb15-1>)# 여러 데이터셋 평가
    [](<#cb15-2>)datasets = [
    [](<#cb15-3>)    "dataset_v1.json",
    [](<#cb15-4>)    "dataset_v2.json",
    [](<#cb15-5>)    "dataset_v3.json"
    [](<#cb15-6>)]
    [](<#cb15-7>)
    [](<#cb15-8>)for dataset_path in datasets:
    [](<#cb15-9>)    dataset = manager.load_dataset(dataset_path)
    [](<#cb15-10>)    report = evaluator.evaluate_dataset(dataset)
    [](<#cb15-11>)    # 결과 비교 분석
```

### 4\. Hybrid Monitor 통합 (고급)

`HybridPerformanceMonitor`를 사용하면 추가적인 고급 메트릭과 추적 기능을 활성화할 수 있습니다.
``` [](<#cb16-1>)from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator
    [](<#cb16-2>)from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager
    [](<#cb16-3>)
    [](<#cb16-4>)# Golden Dataset 로드
    [](<#cb16-5>)manager = GoldenDatasetManager()
    [](<#cb16-6>)dataset = manager.load_dataset("golden_datasets/my_dataset.json")
    [](<#cb16-7>)
    [](<#cb16-8>)# RAG 시스템 초기화
    [](<#cb16-9>)rag_system = MyRAGSystem()
    [](<#cb16-10>)
    [](<#cb16-11>)# 평가기 초기화 (Hybrid Monitor 활성화)
    [](<#cb16-12>)evaluator = KoreanRAGEvaluator(
    [](<#cb16-13>)    rag_system=rag_system,
    [](<#cb16-14>)    use_ragas=True,
    [](<#cb16-15>)    ragas_model="gpt-4o-mini",
    [](<#cb16-16>)    output_dir="evaluation_results"
    [](<#cb16-17>))
    [](<#cb16-18>)
    [](<#cb16-19>)# 평가 실행 (Hybrid Monitor 활성화)
    [](<#cb16-20>)report = evaluator.evaluate_dataset(
    [](<#cb16-21>)    dataset,
    [](<#cb16-22>)    use_hybrid_monitor=True,  # Hybrid Monitor 활성화
    [](<#cb16-23>)    max_samples=None
    [](<#cb16-24>))
    [](<#cb16-25>)
    [](<#cb16-26>)# Hybrid Monitor의 추가 메트릭 확인 (선택적)
    [](<#cb16-27>)if evaluator.monitor:
    [](<#cb16-28>)    # TaskResult로 기록된 정보 확인
    [](<#cb16-29>)    print(f"모니터링된 태스크 수: {len(evaluator.monitor.extended_tasks)}")
    [](<#cb16-30>)
    [](<#cb16-31>)    # Hybrid 리포트 생성 (DeepEval, Ragas 통합)
    [](<#cb16-32>)    hybrid_report = evaluator.monitor.generate_report()
```

**Hybrid Monitor 기능** : - **확장된 메트릭** : DeepEval (G-Eval, Hallucination, Toxicity, Bias) - **태스크 추적** : 각 QA 평가를 `TaskResult`로 기록 - **통합 리포트** : Native + Ragas + DeepEval 메트릭을 하나의 리포트로 - **성능 분석** : 평가 시간, 성공률, 오류 추적

**실제 구현** : - `korean_rag_evaluator.py`의 `_record_to_monitor()` 메서드 - `hybrid_monitor.py`의 `HybridPerformanceMonitor` 클래스 - 각 QA 평가 결과가 `TaskResult`로 변환되어 기록됨

* * *

## 실전 예제: 기업 정책 문서 평가

### 시나리오

회사의 인사 정책 PDF를 RAG 시스템에 적용하고, 직원들의 질문에 정확하게 답변하는지 평가합니다.

### 1단계: Golden Dataset 생성
``` [](<#cb17-1>)from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator
    [](<#cb17-2>)
    [](<#cb17-3>)generator = KoreanRAGDatasetGenerator(
    [](<#cb17-4>)    model="gpt-4o-mini",
    [](<#cb17-5>)    chunk_size=800,
    [](<#cb17-6>)    chunk_overlap=150
    [](<#cb17-7>))
    [](<#cb17-8>)
    [](<#cb17-9>)dataset = generator.generate_from_pdf(
    [](<#cb17-10>)    pdf_path="company_hr_policy.pdf",
    [](<#cb17-11>)    num_questions_per_chunk=4,
    [](<#cb17-12>)    question_types=["factual", "reasoning"],
    [](<#cb17-13>)    save_format="json"
    [](<#cb17-14>))
    [](<#cb17-15>)
    [](<#cb17-16>)print(f"생성 완료: {dataset.total_qa_pairs}개 QA 쌍")
```

### 2단계: RAG 시스템 구축
``` [](<#cb18-1>)from langchain.vectorstores import Chroma
    [](<#cb18-2>)from langchain.embeddings import OpenAIEmbeddings
    [](<#cb18-3>)from langchain.chat_models import ChatOpenAI
    [](<#cb18-4>)from agent_evaluator.datasets.korean_rag_evaluator import RAGSystemInterface, RAGResponse
    [](<#cb18-5>)
    [](<#cb18-6>)class HRPolicyRAG(RAGSystemInterface):
    [](<#cb18-7>)    def __init__(self, pdf_path):
    [](<#cb18-8>)        # 벡터 DB 구축
    [](<#cb18-9>)        from langchain.document_loaders import PyPDFLoader
    [](<#cb18-10>)        from langchain.text_splitter import RecursiveCharacterTextSplitter
    [](<#cb18-11>)
    [](<#cb18-12>)        loader = PyPDFLoader(pdf_path)
    [](<#cb18-13>)        documents = loader.load()
    [](<#cb18-14>)
    [](<#cb18-15>)        text_splitter = RecursiveCharacterTextSplitter(
    [](<#cb18-16>)            chunk_size=800,
    [](<#cb18-17>)            chunk_overlap=150
    [](<#cb18-18>)        )
    [](<#cb18-19>)        splits = text_splitter.split_documents(documents)
    [](<#cb18-20>)
    [](<#cb18-21>)        self.vectorstore = Chroma.from_documents(
    [](<#cb18-22>)            documents=splits,
    [](<#cb18-23>)            embedding=OpenAIEmbeddings()
    [](<#cb18-24>)        )
    [](<#cb18-25>)
    [](<#cb18-26>)        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    [](<#cb18-27>)
    [](<#cb18-28>)    def query(self, question: str) -> RAGResponse:
    [](<#cb18-29>)        # 검색
    [](<#cb18-30>)        docs = self.vectorstore.similarity_search(question, k=3)
    [](<#cb18-31>)        contexts = [doc.page_content for doc in docs]
    [](<#cb18-32>)
    [](<#cb18-33>)        # 답변 생성
    [](<#cb18-34>)        context_text = "\n\n".join(contexts)
    [](<#cb18-35>)        prompt = f"""다음 회사 정책 문서를 참고하여 질문에 답변하세요.
    [](<#cb18-36>)답변은 문서의 내용만을 기반으로 하며, 확실하지 않으면 "문서에 명시되지 않음"이라고 답하세요.
    [](<#cb18-37>)
    [](<#cb18-38>)[문서]
    [](<#cb18-39>){context_text}
    [](<#cb18-40>)
    [](<#cb18-41>)[질문]
    [](<#cb18-42>){question}
    [](<#cb18-43>)
    [](<#cb18-44>)[답변]
    [](<#cb18-45>)"""
    [](<#cb18-46>)        answer = self.llm.predict(prompt)
    [](<#cb18-47>)
    [](<#cb18-48>)        return RAGResponse(
    [](<#cb18-49>)            question=question,
    [](<#cb18-50>)            answer=answer,
    [](<#cb18-51>)            retrieved_contexts=contexts,
    [](<#cb18-52>)            metadata={"model": "gpt-4o-mini"}
    [](<#cb18-53>)        )
```

### 3단계: 평가
``` [](<#cb19-1>)from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator
    [](<#cb19-2>)from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager
    [](<#cb19-3>)
    [](<#cb19-4>)# Golden Dataset 로드
    [](<#cb19-5>)manager = GoldenDatasetManager()
    [](<#cb19-6>)dataset = manager.load_dataset("golden_datasets/hr_policy_dataset.json")
    [](<#cb19-7>)
    [](<#cb19-8>)# RAG 시스템 초기화
    [](<#cb19-9>)rag = HRPolicyRAG("company_hr_policy.pdf")
    [](<#cb19-10>)
    [](<#cb19-11>)# 평가
    [](<#cb19-12>)evaluator = KoreanRAGEvaluator(
    [](<#cb19-13>)    rag_system=rag,
    [](<#cb19-14>)    use_ragas=True,
    [](<#cb19-15>)    ragas_model="gpt-4o-mini"
    [](<#cb19-16>))
    [](<#cb19-17>)
    [](<#cb19-18>)report = evaluator.evaluate_dataset(dataset)
    [](<#cb19-19>)
    [](<#cb19-20>)# 결과 분석
    [](<#cb19-21>)if report.avg_faithfulness >= 0.8:
    [](<#cb19-22>)    print("✅ RAG 시스템이 정책 문서에 충실합니다")
    [](<#cb19-23>)else:
    [](<#cb19-24>)    print("⚠️  환각(hallucination) 문제가 있습니다")
    [](<#cb19-25>)
    [](<#cb19-26>)if report.avg_context_recall >= 0.8:
    [](<#cb19-27>)    print("✅ 검색 성능이 우수합니다")
    [](<#cb19-28>)else:
    [](<#cb19-29>)    print("⚠️  검색 성능 개선이 필요합니다")
```

* * *

## ✨ PerformanceMonitor 통합

이제 `PerformanceMonitor`가 RAG 메트릭을 직접 추적하고 관리할 수 있습니다. 이를 통해 한국어 RAG 평가 결과를 threshold와 비교하여 품질 게이트를 구현할 수 있습니다.

### 개요

`PerformanceMonitor`는 Agent Evaluator의 핵심 모니터링 도구로, ✨ 이제 다음 기능을 지원합니다:

    * **RAG 메트릭 기록** : `record_rag_metrics()`로 4가지 RAG 메트릭을 직접 추적
    * **자동 계산** : `compare_with_thresholds()`에서 실제 평균값을 자동 계산
    * **Threshold 비교** : 설정된 임계값과 비교하여 pass/fail 판정 (Quality Gate 구현)
    * **통합 리포트** : CSV export 시 RAG 메트릭 자동 포함 (13+ 메트릭)
    * **CSV export** : Dashboard에서 한 번의 클릭으로 모든 메트릭을 CSV로 내보내기

### 기본 사용법
``` [](<#cb19a-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb19a-2>)from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator
    [](<#cb19a-3>)
    [](<#cb19a-4>)# 1. PerformanceMonitor 초기화
    [](<#cb19a-5>)monitor = PerformanceMonitor()
    [](<#cb19a-6>)
    [](<#cb19a-7>)# 2. Threshold 설정
    [](<#cb19a-8>)monitor.thresholds = {
    [](<#cb19a-9>)    "faithfulness": 0.8,           # 환각 방지
    [](<#cb19a-10>)    "answer_relevancy": 0.85,      # 답변 관련성
    [](<#cb19a-11>)    "context_recall": 0.75,        # 검색 완전성
    [](<#cb19a-12>)    "context_precision": 0.8       # 검색 정확도
    [](<#cb19a-13>)}
    [](<#cb19a-14>)
    [](<#cb19a-15>)# 3. KoreanRAGEvaluator로 평가
    [](<#cb19a-16>)rag_evaluator = KoreanRAGEvaluator(rag_system=my_rag_system)
    [](<#cb19a-17>)
    [](<#cb19a-18>)result = rag_evaluator.evaluate_single(
    [](<#cb19a-19>)    question="한국의 수도는 어디인가요?",
    [](<#cb19a-20>)    expected_answer="서울입니다"
    [](<#cb19a-21>))
    [](<#cb19a-22>)
    [](<#cb19a-23>)# 4. 최신 기능: PerformanceMonitor에 RAG 메트릭 기록
    [](<#cb19a-24>)monitor.record_rag_metrics(
    [](<#cb19a-25>)    faithfulness=result.faithfulness,
    [](<#cb19a-26>)    answer_relevancy=result.answer_relevancy,
    [](<#cb19a-27>)    context_recall=result.context_recall,
    [](<#cb19a-28>)    context_precision=result.context_precision
    [](<#cb19a-29>))
    [](<#cb19a-30>)
    [](<#cb19a-31>)# 5. 최신 기능: Threshold와 자동 비교 (실제 값 계산)
    [](<#cb19a-32>)comparison = monitor.compare_with_thresholds()
    [](<#cb19a-33>)
    [](<#cb19a-34>)# 6. 결과 출력
    [](<#cb19a-35>)for metric in ["faithfulness", "answer_relevancy", "context_recall", "context_precision"]:
    [](<#cb19a-36>)    data = comparison[metric]
    [](<#cb19a-37>)    status = "✅" if data["status"] == "pass" else "❌"
    [](<#cb19a-38>)    print(f"{status} {data['name']}: {data['value']:.3f} (임계값: {data['threshold']})")
```

**출력 예제** :

```
    ✅ Faithfulness: 0.850 (임계값: 0.8)
    ✅ Answer Relevancy: 0.880 (임계값: 0.85)
    ✅ Context Recall: 0.780 (임계값: 0.75)
    ✅ Context Precision: 0.820 (임계값: 0.8)
```

### 완전한 워크플로우

Dataset 전체를 평가하고 PerformanceMonitor로 추적하는 완전한 예제입니다.
```python
    [](<#cb19b-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb19b-2>)from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator
    [](<#cb19b-3>)from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager
    [](<#cb19b-4>)
    [](<#cb19b-5>)# PerformanceMonitor 초기화 및 Threshold 설정
    [](<#cb19b-6>)monitor = PerformanceMonitor()
    [](<#cb19b-7>)monitor.thresholds = {
    [](<#cb19b-8>)    "faithfulness": 0.8,
    [](<#cb19b-9>)    "answer_relevancy": 0.85,
    [](<#cb19b-10>)    "context_recall": 0.75,
    [](<#cb19b-11>)    "context_precision": 0.8
    [](<#cb19b-12>)}
    [](<#cb19b-13>)
    [](<#cb19b-14>)# Dataset 로드
    [](<#cb19b-15>)manager = GoldenDatasetManager()
    [](<#cb19b-16>)dataset = manager.load_dataset("golden_datasets/hr_policy_dataset.json")
    [](<#cb19b-17>)
    [](<#cb19b-18>)# RAG Evaluator 초기화
    [](<#cb19b-19>)rag_evaluator = KoreanRAGEvaluator(
    [](<#cb19b-20>)    rag_system=my_rag_system,
    [](<#cb19b-21>)    use_ragas=True,
    [](<#cb19b-22>)    ragas_model="gpt-4o-mini"
    [](<#cb19b-23>))
    [](<#cb19b-24>)
    [](<#cb19b-25>)# Dataset 평가 및 메트릭 기록
    [](<#cb19b-26>)for qa_pair in dataset.qa_pairs:
    [](<#cb19b-27>)    result = rag_evaluator.evaluate_single(
    [](<#cb19b-28>)        question=qa_pair.question,
    [](<#cb19b-29>)        expected_answer=qa_pair.expected_answer
    [](<#cb19b-30>)    )
    [](<#cb19b-31>)    
    [](<#cb19b-32>)    # PerformanceMonitor에 기록
    [](<#cb19b-33>)    monitor.record_rag_metrics(
    [](<#cb19b-34>)        faithfulness=result.faithfulness,
    [](<#cb19b-35>)        answer_relevancy=result.answer_relevancy,
    [](<#cb19b-36>)        context_recall=result.context_recall,
    [](<#cb19b-37>)        context_precision=result.context_precision
    [](<#cb19b-38>)    )
    [](<#cb19b-39>)
    [](<#cb19b-40>)# 최신 기능: Threshold 비교 (자동 pass/fail 판정)
    [](<#cb19b-41>)comparison = monitor.compare_with_thresholds()
    [](<#cb19b-42>)
    [](<#cb19b-43>)# 품질 게이트 체크
    [](<#cb19b-44>)failed_metrics = [
    [](<#cb19b-45>)    metric for metric, data in comparison.items() 
    [](<#cb19b-46>)    if data["status"] == "fail"
    [](<#cb19b-47>)]
    [](<#cb19b-48>)
    [](<#cb19b-49>)if failed_metrics:
    [](<#cb19b-50>)    print(f"❌ RAG 품질 게이트 실패! 실패한 메트릭: {len(failed_metrics)}개")
    [](<#cb19b-51>)    for metric in failed_metrics:
    [](<#cb19b-52>)        data = comparison[metric]
    [](<#cb19b-53>)        print(f"  - {data['name']}: {data['value']:.3f} (필요: {data['threshold']})")
    [](<#cb19b-54>)else:
    [](<#cb19b-55>)    print("✅ RAG 품질 게이트 통과! 모든 메트릭이 임계값을 충족합니다.")
    [](<#cb19b-56>)
    [](<#cb19b-57>)# RAG 메트릭 요약 확인
    [](<#cb19b-58>)rag_summary = monitor.get_rag_metrics_summary()
    [](<#cb19b-59>)print(f"\nRAG 메트릭 요약:")
    [](<#cb19b-60>)print(f"  평균 Faithfulness: {rag_summary['faithfulness']['mean']:.3f}")
    [](<#cb19b-61>)print(f"  평균 Answer Relevancy: {rag_summary['answer_relevancy']['mean']:.3f}")
    [](<#cb19b-62>)print(f"  평균 Context Recall: {rag_summary['context_recall']['mean']:.3f}")
    [](<#cb19b-63>)print(f"  평균 Context Precision: {rag_summary['context_precision']['mean']:.3f}")
    [](<#cb19b-64>)
    [](<#cb19b-65>)# CSV 내보내기 (RAG 메트릭 포함)
    [](<#cb19b-66>)monitor.export_report("rag_evaluation_report.csv", format="csv")
    [](<#cb19b-67>)print("\n📊 리포트 저장 완료: rag_evaluation_report.csv")
```

### 핵심 기능

기능 | 메서드 | 설명  
---|---|---  
**RAG 메트릭 기록** | `record_rag_metrics()` | faithfulness, answer_relevancy, context_recall, context_precision 기록  
**실제 값 계산** | `compare_with_thresholds()` | 기록된 RAG 메트릭의 평균값을 자동 계산하여 반환  
**Pass/Fail 판정** | `compare_with_thresholds()` | 임계값과 비교하여 자동으로 'pass' 또는 'fail' 판정  
**통계 요약** | `get_rag_metrics_summary()` | RAG 메트릭의 평균, 최소, 최대, 표준편차 등 제공  
**CSV 내보내기** | `export_report()` | 13+ 메트릭(기본 + RAG) 포함하여 CSV 저장  
  
> **⚡ 핵심 개선사항** : 이전 버전에서는 RAG 메트릭이 'pending' 상태로 표시되었지만, 이제는 `record_rag_metrics()`로 기록하면 `compare_with_thresholds()`에서 자동으로 실제 평균값을 계산하고 pass/fail 판정을 수행합니다.

### Threshold 권장 설정

메트릭 | 일반적 | 엄격함 | 관대함 | 용도  
---|---|---|---|---  
`faithfulness` | ≥0.8 | ≥0.9 | ≥0.7 | 환각 방지 (가장 중요)  
`answer_relevancy` | ≥0.85 | ≥0.9 | ≥0.75 | 답변 품질  
`context_recall` | ≥0.75 | ≥0.85 | ≥0.65 | 검색 완전성  
`context_precision` | ≥0.8 | ≥0.9 | ≥0.7 | 검색 정확도  
  
**권장 시나리오** :

  * **프로덕션 RAG 시스템** : 일반적 설정 사용
  * **의료/금융/법률 시스템** : 엄격한 설정 사용 (특히 faithfulness ≥0.9)
  * **개발/테스트 환경** : 관대한 설정 사용
  * **CI/CD 품질 게이트** : 일반적 설정으로 자동 배포 차단

* * *

## 💻 개발자 가이드 (Developer Guide)

한국어 RAG 시스템을 효율적으로 통합하고 평가하기 위한 개발자 중심 가이드입니다.

### 8.1 RAG 시스템 통합

#### 8.1.1 RAGSystemInterface 구현
```python
    from abc import ABC, abstractmethod
    from typing import List, Dict, Tuple
    
    class RAGSystemInterface(ABC):
        """RAG 시스템 통합을 위한 표준 인터페이스"""
    
        @abstractmethod
        def retrieve_and_generate(
            self,
            query: str,
            top_k: int = 5
        ) -> Tuple[str, List[str]]:
            """
            질의에 대한 답변 생성 및 검색된 컨텍스트 반환
    
            Args:
                query: 사용자 질의
                top_k: 검색할 문서 수
    
            Returns:
                (answer, contexts): 생성된 답변과 검색된 컨텍스트 리스트
            """
            pass
    
    # 실전 구현 예제 1: LangChain 기반 RAG
    from langchain.embeddings import OpenAIEmbeddings
    from langchain.vectorstores import Chroma
    from langchain.chains import RetrievalQA
    from langchain.llms import OpenAI
    
    class LangChainRAGSystem(RAGSystemInterface):
        """LangChain 기반 RAG 시스템 구현"""
    
        def __init__(self, vectorstore_path: str):
            self.embeddings = OpenAIEmbeddings()
            self.vectorstore = Chroma(
                persist_directory=vectorstore_path,
                embedding_function=self.embeddings
            )
            self.llm = OpenAI(temperature=0)
            self.qa_chain = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type="stuff",
                retriever=self.vectorstore.as_retriever(search_kwargs={"k": 5}),
                return_source_documents=True
            )
    
        def retrieve_and_generate(
            self,
            query: str,
            top_k: int = 5
        ) -> Tuple[str, List[str]]:
            # 검색 및 생성
            result = self.qa_chain({"query": query})
    
            # 답변 추출
            answer = result['result']
    
            # 컨텍스트 추출
            contexts = [doc.page_content for doc in result['source_documents']]
    
            return answer, contexts
    
    # 실전 구현 예제 2: 커스텀 RAG (FAISS + OpenAI)
    import faiss
    import numpy as np
    from openai import OpenAI
    
    class CustomRAGSystem(RAGSystemInterface):
        """FAISS + OpenAI 기반 커스텀 RAG 시스템"""
    
        def __init__(self, index_path: str, docs_path: str):
            # FAISS 인덱스 로드
            self.index = faiss.read_index(index_path)
    
            # 문서 로드
            with open(docs_path, 'r', encoding='utf-8') as f:
                self.documents = json.load(f)
    
            # OpenAI 클라이언트
            self.client = OpenAI()
    
        def _embed_query(self, query: str) -> np.ndarray:
            """질의를 임베딩으로 변환"""
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            return np.array(response.data[0].embedding, dtype=np.float32)
    
        def retrieve_and_generate(
            self,
            query: str,
            top_k: int = 5
        ) -> Tuple[str, List[str]]:
            # 1. 질의 임베딩
            query_embedding = self._embed_query(query)
    
            # 2. FAISS 검색
            distances, indices = self.index.search(
                query_embedding.reshape(1, -1),
                top_k
            )
    
            # 3. 검색된 문서 추출
            contexts = [self.documents[idx] for idx in indices[0]]
    
            # 4. 프롬프트 구성
            context_text = "\n\n".join([f"[문서 {i+1}]\n{ctx}" for i, ctx in enumerate(contexts)])
            prompt = f"""다음 문서들을 참고하여 질문에 답변해주세요.
    
    문서:
    {context_text}
    
    질문: {query}
    
    답변:"""
    
            # 5. OpenAI로 답변 생성
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "당신은 주어진 문서를 기반으로 정확하게 답변하는 AI 어시스턴트입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
    
            answer = response.choices[0].message.content
    
            return answer, contexts
    
```

#### 8.1.2 평가 파이프라인 구축
```python
    #!/usr/bin/env python3
    """
    evaluate_rag.py - RAG 시스템 평가 파이프라인
    """
    from agent_evaluator.datasets import KoreanRAGEvaluator
    from typing import List, Dict
    import json
    from datetime import datetime
    
    class RAGEvaluationPipeline:
        """RAG 평가 자동화 파이프라인"""
    
        def __init__(
            self,
            rag_system: RAGSystemInterface,
            golden_dataset_path: str,
            output_dir: str = "evaluation_results"
        ):
            self.rag_system = rag_system
            self.golden_dataset = self._load_golden_dataset(golden_dataset_path)
            self.output_dir = output_dir
            self.evaluator = KoreanRAGEvaluator()
    
        def _load_golden_dataset(self, path: str) -> List[Dict]:
            """Golden Dataset 로드"""
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
        def run_evaluation(self, test_name: str = None) -> Dict:
            """전체 평가 실행"""
            if test_name is None:
                test_name = f"rag_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
            print(f"=== RAG System Evaluation: {test_name} ===")
            print(f"Golden Dataset: {len(self.golden_dataset)} QA pairs")
    
            results = []
            total_questions = len(self.golden_dataset)
    
            for i, qa_pair in enumerate(self.golden_dataset, 1):
                print(f"\nProcessing {i}/{total_questions}: {qa_pair['question'][:50]}...")
    
                try:
                    # RAG 시스템으로 답변 생성
                    answer, contexts = self.rag_system.retrieve_and_generate(
                        qa_pair['question']
                    )
    
                    # 평가 수행
                    metrics = self.evaluator.evaluate(
                        question=qa_pair['question'],
                        answer=answer,
                        contexts=contexts,
                        ground_truth=qa_pair['ground_truth']
                    )
    
                    result = {
                        "question": qa_pair['question'],
                        "ground_truth": qa_pair['ground_truth'],
                        "generated_answer": answer,
                        "contexts": contexts,
                        "metrics": metrics
                    }
    
                    results.append(result)
    
                    # 실시간 진행 상황 출력
                    print(f"  ✓ Faithfulness: {metrics['faithfulness']:.3f}")
                    print(f"  ✓ Answer Relevancy: {metrics['answer_relevancy']:.3f}")
    
                except Exception as e:
                    print(f"  ✗ Error: {str(e)}")
                    results.append({
                        "question": qa_pair['question'],
                        "error": str(e)
                    })
    
            # 결과 저장 및 통계 계산
            report = self._generate_report(results, test_name)
            self._save_results(results, report, test_name)
    
            return report
    
        def _generate_report(self, results: List[Dict], test_name: str) -> Dict:
            """평가 보고서 생성"""
            # 에러 케이스 제외
            valid_results = [r for r in results if 'metrics' in r]
    
            if not valid_results:
                return {"error": "No valid results"}
    
            # 평균 메트릭 계산
            metrics_sum = {
                'faithfulness': 0,
                'answer_relevancy': 0,
                'answer_similarity': 0,
                'context_recall': 0,
                'context_precision': 0
            }
    
            for result in valid_results:
                for key in metrics_sum.keys():
                    metrics_sum[key] += result['metrics'].get(key, 0)
    
            avg_metrics = {
                key: value / len(valid_results)
                for key, value in metrics_sum.items()
            }
    
            # 통과/실패 기준 (임계값)
            thresholds = {
                'faithfulness': 0.7,
                'answer_relevancy': 0.7,
                'answer_similarity': 0.7,
                'context_recall': 0.7,
                'context_precision': 0.7
            }
    
            passed = all(
                avg_metrics[key] >= threshold
                for key, threshold in thresholds.items()
            )
    
            report = {
                "test_name": test_name,
                "timestamp": datetime.now().isoformat(),
                "total_questions": len(results),
                "valid_results": len(valid_results),
                "errors": len(results) - len(valid_results),
                "average_metrics": avg_metrics,
                "thresholds": thresholds,
                "passed": passed
            }
    
            return report
    
        def _save_results(self, results: List[Dict], report: Dict, test_name: str):
            """결과 파일 저장"""
            import os
            os.makedirs(self.output_dir, exist_ok=True)
    
            # 상세 결과 저장
            results_file = f"{self.output_dir}/{test_name}_detailed.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n✓ Detailed results saved: {results_file}")
    
            # 요약 보고서 저장
            report_file = f"{self.output_dir}/{test_name}_report.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"✓ Report saved: {report_file}")
    
            # 사람이 읽기 쉬운 형식으로도 저장
            summary_file = f"{self.output_dir}/{test_name}_summary.txt"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"=== RAG System Evaluation Report ===\n")
                f.write(f"Test: {report['test_name']}\n")
                f.write(f"Date: {report['timestamp']}\n")
                f.write(f"Total Questions: {report['total_questions']}\n")
                f.write(f"Valid Results: {report['valid_results']}\n")
                f.write(f"\n=== Average Metrics ===\n")
                for metric, value in report['average_metrics'].items():
                    threshold = report['thresholds'][metric]
                    status = "✓" if value >= threshold else "✗"
                    f.write(f"{status} {metric}: {value:.3f} (threshold: {threshold})\n")
                f.write(f"\n=== Overall Result ===\n")
                f.write(f"{'PASSED' if report['passed'] else 'FAILED'}\n")
            print(f"✓ Summary saved: {summary_file}")
    
    # 사용 예시
    if __name__ == "__main__":
        # 1. RAG 시스템 초기화
        rag_system = LangChainRAGSystem(vectorstore_path="./chroma_db")
    
        # 2. 평가 파이프라인 생성
        pipeline = RAGEvaluationPipeline(
            rag_system=rag_system,
            golden_dataset_path="golden_qa_pairs.json",
            output_dir="evaluation_results"
        )
    
        # 3. 평가 실행
        report = pipeline.run_evaluation(test_name="v1.0_test")
    
        # 4. 결과 출력
        print("\n=== Evaluation Complete ===")
        print(f"Result: {'PASSED' if report['passed'] else 'FAILED'}")
        print(f"Average Metrics:")
        for metric, value in report['average_metrics'].items():
            print(f"  {metric}: {value:.3f}")
    
```

#### 8.1.3 다양한 RAG 프레임워크 통합 예제

프레임워크 | 구현 클래스 | 주요 특징 | 적용 사례  
---|---|---|---  
LangChain | LangChainRAGSystem | 체인 기반, 다양한 retriever 지원 | 프로토타입, MVP  
LlamaIndex | LlamaIndexRAGSystem | 인덱스 최적화, 쿼리 엔진 | 대용량 문서  
Haystack | HaystackRAGSystem | 파이프라인 기반, 프로덕션 ready | 엔터프라이즈  
Custom | CustomRAGSystem | 완전한 커스터마이징 | 특수 요구사항  
  
### 8.2 커스텀 메트릭 개발

#### 8.2.1 커스텀 메트릭 구현 가이드
```python
    from typing import Dict
    from agent_evaluator.datasets.korean_rag_evaluator import BaseMetric
    
    class CustomHallucinationDetector(BaseMetric):
        """환각(Hallucination) 탐지 커스텀 메트릭"""
    
        def __init__(self, openai_api_key: str):
            self.client = OpenAI(api_key=openai_api_key)
    
        def evaluate(
            self,
            question: str,
            answer: str,
            contexts: List[str],
            ground_truth: str = None
        ) -> float:
            """
            답변이 컨텍스트에 근거하지 않은 정보를 포함하는지 평가
    
            Returns:
                0.0 (심각한 환각) ~ 1.0 (환각 없음)
            """
            # 컨텍스트 병합
            context_text = "\n\n".join(contexts)
    
            # GPT-4로 환각 탐지
            prompt = f"""다음은 RAG 시스템이 생성한 답변입니다.
    답변이 제공된 문서에 근거하지 않은 정보를 포함하는지 평가해주세요.
    
    문서:
    {context_text}
    
    답변:
    {answer}
    
    평가 기준:
    1. 답변의 모든 사실적 주장이 문서에서 확인 가능한가?
    2. 문서에 없는 정보를 추론하여 추가하지 않았는가?
    3. 문서의 내용을 왜곡하거나 과장하지 않았는가?
    
    다음 형식으로 답변해주세요:
    {{
      "hallucination_score": 0.0 ~ 1.0 (0.0 = 심각한 환각, 1.0 = 환각 없음),
      "hallucinated_statements": ["환각된 문장1", "환각된 문장2", ...],
      "reasoning": "평가 이유"
    }}"""
    
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "당신은 RAG 시스템의 답변 품질을 평가하는 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
    
            result = json.loads(response.choices[0].message.content)
            return result['hallucination_score']
    
    class DomainSpecificAccuracy(BaseMetric):
        """도메인 특화 정확도 메트릭 (예: 법률, 의료, 금융)"""
    
        def __init__(self, domain: str, terminology_db: Dict[str, List[str]]):
            """
            Args:
                domain: 도메인 이름 (e.g., "legal", "medical")
                terminology_db: 도메인 용어 사전
                    {
                        "정확한_용어": ["잘못된_변형1", "잘못된_변형2"],
                        ...
                    }
            """
            self.domain = domain
            self.terminology_db = terminology_db
    
        def evaluate(
            self,
            question: str,
            answer: str,
            contexts: List[str],
            ground_truth: str = None
        ) -> float:
            """도메인 용어 사용의 정확도 평가"""
    
            errors = 0
            total_checks = 0
    
            for correct_term, incorrect_variants in self.terminology_db.items():
                # 정답에서 정확한 용어를 사용해야 하는 경우
                if correct_term in ground_truth:
                    total_checks += 1
    
                    # 답변에서 잘못된 변형 사용 여부 확인
                    if any(variant in answer for variant in incorrect_variants):
                        errors += 1
                    # 정확한 용어를 사용하지 않은 경우
                    elif correct_term not in answer:
                        errors += 0.5  # 부분 감점
    
            if total_checks == 0:
                return 1.0  # 검사 대상 없음
    
            accuracy = 1.0 - (errors / total_checks)
            return max(0.0, accuracy)
    
    class AnswerCompleteness(BaseMetric):
        """답변 완전성 메트릭 - 모든 하위 질문에 답변했는지 확인"""
    
        def __init__(self, openai_api_key: str):
            self.client = OpenAI(api_key=openai_api_key)
    
        def evaluate(
            self,
            question: str,
            answer: str,
            contexts: List[str],
            ground_truth: str = None
        ) -> float:
            """
            질문의 모든 부분에 대해 답변이 제공되었는지 평가
    
            Returns:
                0.0 (불완전) ~ 1.0 (완전)
            """
            prompt = f"""다음 질문과 답변을 분석해주세요.
    
    질문: {question}
    답변: {answer}
    
    질문이 여러 하위 질문으로 구성되어 있다면 각각 식별하고,
    답변이 각 하위 질문에 대해 적절히 답변했는지 평가해주세요.
    
    다음 형식으로 답변해주세요:
    {{
      "sub_questions": ["하위질문1", "하위질문2", ...],
      "answered": [true, false, ...],
      "completeness_score": 0.0 ~ 1.0,
      "missing_parts": ["답변되지 않은 부분1", ...]
    }}"""
    
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "당신은 답변 완전성을 평가하는 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
    
            result = json.loads(response.choices[0].message.content)
            return result['completeness_score']
    
    # 커스텀 메트릭 통합
    class EnhancedRAGEvaluator:
        """커스텀 메트릭을 포함한 향상된 평가기"""
    
        def __init__(self):
            # 기본 메트릭
            self.base_evaluator = KoreanRAGEvaluator()
    
            # 커스텀 메트릭
            self.custom_metrics = {
                'hallucination': CustomHallucinationDetector(openai_api_key="..."),
                'domain_accuracy': DomainSpecificAccuracy(
                    domain="legal",
                    terminology_db={
                        "계약서": ["약정서", "협약서"],
                        "피고": ["피고인", "피소자"],
                    }
                ),
                'completeness': AnswerCompleteness(openai_api_key="...")
            }
    
        def evaluate(
            self,
            question: str,
            answer: str,
            contexts: List[str],
            ground_truth: str
        ) -> Dict[str, float]:
            """기본 + 커스텀 메트릭 모두 평가"""
    
            # 기본 메트릭
            results = self.base_evaluator.evaluate(
                question=question,
                answer=answer,
                contexts=contexts,
                ground_truth=ground_truth
            )
    
            # 커스텀 메트릭 추가
            for metric_name, metric in self.custom_metrics.items():
                results[metric_name] = metric.evaluate(
                    question=question,
                    answer=answer,
                    contexts=contexts,
                    ground_truth=ground_truth
                )
    
            return results
    
```

#### 8.2.2 메트릭 조합 및 가중치 설정
```python
    class WeightedRAGEvaluator:
        """가중치 기반 종합 평가"""
    
        def __init__(self, metric_weights: Dict[str, float]):
            """
            Args:
                metric_weights: 메트릭별 가중치
                    {
                        'faithfulness': 0.3,
                        'answer_relevancy': 0.25,
                        'context_recall': 0.2,
                        'hallucination': 0.15,
                        'completeness': 0.1
                    }
            """
            self.weights = metric_weights
            self.evaluator = EnhancedRAGEvaluator()
    
            # 가중치 합이 1.0인지 확인
            assert abs(sum(metric_weights.values()) - 1.0) < 0.01, \
                "Metric weights must sum to 1.0"
    
        def evaluate(
            self,
            question: str,
            answer: str,
            contexts: List[str],
            ground_truth: str
        ) -> Dict:
            """가중치 적용 종합 평가"""
    
            # 개별 메트릭 평가
            metrics = self.evaluator.evaluate(
                question=question,
                answer=answer,
                contexts=contexts,
                ground_truth=ground_truth
            )
    
            # 가중 평균 계산
            weighted_score = sum(
                metrics[metric] * weight
                for metric, weight in self.weights.items()
                if metric in metrics
            )
    
            return {
                "metrics": metrics,
                "weighted_score": weighted_score,
                "weights": self.weights
            }
    
```

### 8.3 성능 최적화

#### 8.3.1 배치 처리 및 병렬화
```python
    import concurrent.futures
    from typing import List, Dict
    import time
    
    class OptimizedRAGEvaluator:
        """성능 최적화된 RAG 평가기"""
    
        def __init__(
            self,
            rag_system: RAGSystemInterface,
            max_workers: int = 4,
            batch_size: int = 10
        ):
            self.rag_system = rag_system
            self.max_workers = max_workers
            self.batch_size = batch_size
            self.evaluator = KoreanRAGEvaluator()
    
        def evaluate_batch(
            self,
            qa_pairs: List[Dict],
            use_cache: bool = True
        ) -> List[Dict]:
            """배치 평가 - 병렬 처리"""
    
            print(f"Evaluating {len(qa_pairs)} QA pairs with {self.max_workers} workers...")
            start_time = time.time()
    
            results = []
    
            # 배치 단위로 처리
            for i in range(0, len(qa_pairs), self.batch_size):
                batch = qa_pairs[i:i+self.batch_size]
                print(f"\nProcessing batch {i//self.batch_size + 1} ({len(batch)} items)...")
    
                # 병렬 처리
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_to_qa = {
                        executor.submit(self._evaluate_single, qa): qa
                        for qa in batch
                    }
    
                    for future in concurrent.futures.as_completed(future_to_qa):
                        qa = future_to_qa[future]
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            print(f"Error processing {qa['question'][:50]}: {str(e)}")
                            results.append({
                                "question": qa['question'],
                                "error": str(e)
                            })
    
            elapsed = time.time() - start_time
            print(f"\n✓ Completed in {elapsed:.1f}s ({len(qa_pairs)/elapsed:.1f} QA/s)")
    
            return results
    
        def _evaluate_single(self, qa_pair: Dict) -> Dict:
            """단일 QA 쌍 평가"""
            # RAG 시스템으로 답변 생성
            answer, contexts = self.rag_system.retrieve_and_generate(
                qa_pair['question']
            )
    
            # 메트릭 평가
            metrics = self.evaluator.evaluate(
                question=qa_pair['question'],
                answer=answer,
                contexts=contexts,
                ground_truth=qa_pair['ground_truth']
            )
    
            return {
                "question": qa_pair['question'],
                "ground_truth": qa_pair['ground_truth'],
                "generated_answer": answer,
                "contexts": contexts,
                "metrics": metrics
            }
    
    # 캐싱 전략
    import hashlib
    import json
    import os
    
    class CachedRAGEvaluator:
        """결과 캐싱을 통한 성능 향상"""
    
        def __init__(
            self,
            rag_system: RAGSystemInterface,
            cache_dir: str = ".rag_eval_cache"
        ):
            self.rag_system = rag_system
            self.cache_dir = cache_dir
            os.makedirs(cache_dir, exist_ok=True)
    
        def _get_cache_key(self, question: str) -> str:
            """질의에 대한 캐시 키 생성"""
            return hashlib.md5(question.encode()).hexdigest()
    
        def _load_from_cache(self, cache_key: str) -> Dict:
            """캐시에서 결과 로드"""
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
    
        def _save_to_cache(self, cache_key: str, result: Dict):
            """결과를 캐시에 저장"""
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
    
        def evaluate(
            self,
            question: str,
            ground_truth: str,
            use_cache: bool = True
        ) -> Dict:
            """캐시를 활용한 평가"""
            cache_key = self._get_cache_key(question)
    
            # 캐시 확인
            if use_cache:
                cached_result = self._load_from_cache(cache_key)
                if cached_result:
                    print(f"  ✓ Cache hit: {question[:50]}...")
                    return cached_result
    
            # 캐시 미스 - 실제 평가 수행
            print(f"  ⟳ Evaluating: {question[:50]}...")
            answer, contexts = self.rag_system.retrieve_and_generate(question)
    
            evaluator = KoreanRAGEvaluator()
            metrics = evaluator.evaluate(
                question=question,
                answer=answer,
                contexts=contexts,
                ground_truth=ground_truth
            )
    
            result = {
                "question": question,
                "ground_truth": ground_truth,
                "generated_answer": answer,
                "contexts": contexts,
                "metrics": metrics
            }
    
            # 캐시에 저장
            if use_cache:
                self._save_to_cache(cache_key, result)
    
            return result
    
```

#### 8.3.2 성능 프로파일링
```python
    import time
    from functools import wraps
    
    def profile_evaluation(func):
        """평가 함수 성능 프로파일링 데코레이터"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
    
            result = func(*args, **kwargs)
    
            elapsed = time.time() - start
    
            # 상세 타이밍 정보 추가
            if isinstance(result, dict):
                result['_profiling'] = {
                    'elapsed_seconds': elapsed,
                    'function': func.__name__
                }
    
            return result
    
        return wrapper
    
    class ProfilingRAGEvaluator:
        """성능 프로파일링 기능이 포함된 평가기"""
    
        def __init__(self, rag_system: RAGSystemInterface):
            self.rag_system = rag_system
            self.evaluator = KoreanRAGEvaluator()
            self.timings = {
                'retrieval': [],
                'generation': [],
                'evaluation': []
            }
    
        @profile_evaluation
        def evaluate_with_profiling(
            self,
            question: str,
            ground_truth: str
        ) -> Dict:
            """프로파일링과 함께 평가"""
    
            # 1. Retrieval + Generation
            start = time.time()
            answer, contexts = self.rag_system.retrieve_and_generate(question)
            rag_time = time.time() - start
            self.timings['retrieval'].append(rag_time)
    
            # 2. Evaluation
            start = time.time()
            metrics = self.evaluator.evaluate(
                question=question,
                answer=answer,
                contexts=contexts,
                ground_truth=ground_truth
            )
            eval_time = time.time() - start
            self.timings['evaluation'].append(eval_time)
    
            return {
                "question": question,
                "metrics": metrics,
                "timing": {
                    "rag_seconds": rag_time,
                    "evaluation_seconds": eval_time,
                    "total_seconds": rag_time + eval_time
                }
            }
    
        def print_profiling_summary(self):
            """프로파일링 결과 요약"""
            import statistics
    
            print("\n=== Performance Profiling Summary ===")
    
            for operation, times in self.timings.items():
                if times:
                    print(f"\n{operation.upper()}:")
                    print(f"  Count: {len(times)}")
                    print(f"  Mean: {statistics.mean(times):.3f}s")
                    print(f"  Median: {statistics.median(times):.3f}s")
                    print(f"  Min: {min(times):.3f}s")
                    print(f"  Max: {max(times):.3f}s")
                    print(f"  StdDev: {statistics.stdev(times):.3f}s" if len(times) > 1 else "")
    
```

### 8.4 프로덕션 배포

#### 8.4.1 프로덕션 설정
```python
    # production_config.py
    """프로덕션 환경 설정"""
    import os
    from dataclasses import dataclass
    
    @dataclass
    class ProductionConfig:
        """프로덕션 환경 설정"""
    
        # OpenAI 설정
        openai_api_key: str = os.getenv("OPENAI_API_KEY")
        openai_model: str = "gpt-4-turbo-preview"
        openai_max_retries: int = 3
        openai_timeout: int = 60
    
        # RAG 설정
        retrieval_top_k: int = 5
        chunk_size: int = 1000
        chunk_overlap: int = 200
    
        # 평가 설정
        evaluation_batch_size: int = 10
        evaluation_max_workers: int = 4
        evaluation_cache_enabled: bool = True
        evaluation_cache_dir: str = ".eval_cache"
    
        # 임계값
        thresholds: dict = None
    
        def __post_init__(self):
            if self.thresholds is None:
                self.thresholds = {
                    'faithfulness': 0.7,
                    'answer_relevancy': 0.7,
                    'context_recall': 0.7,
                    'context_precision': 0.7,
                    'answer_similarity': 0.7
                }
    
        @classmethod
        def from_env(cls):
            """환경 변수에서 설정 로드"""
            return cls(
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                openai_model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"),
                retrieval_top_k=int(os.getenv("RETRIEVAL_TOP_K", "5")),
                evaluation_batch_size=int(os.getenv("EVAL_BATCH_SIZE", "10")),
                evaluation_max_workers=int(os.getenv("EVAL_MAX_WORKERS", "4"))
            )
    
        def validate(self):
            """설정 유효성 검증"""
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required")
    
            if self.retrieval_top_k < 1:
                raise ValueError("retrieval_top_k must be >= 1")
    
            if self.evaluation_batch_size < 1:
                raise ValueError("evaluation_batch_size must be >= 1")
    
            print("✓ Configuration validated")
    
```

#### 8.4.2 에러 처리 및 재시도
```python
    import time
    from typing import Callable, Any
    import openai
    
    class RetryHandler:
        """재시도 로직을 포함한 에러 처리"""
    
        def __init__(
            self,
            max_retries: int = 3,
            backoff_factor: float = 2.0,
            retry_on_exceptions: tuple = (openai.APIError, openai.RateLimitError)
        ):
            self.max_retries = max_retries
            self.backoff_factor = backoff_factor
            self.retry_on_exceptions = retry_on_exceptions
    
        def execute_with_retry(
            self,
            func: Callable,
            *args,
            **kwargs
        ) -> Any:
            """재시도 로직과 함께 함수 실행"""
    
            for attempt in range(self.max_retries):
                try:
                    return func(*args, **kwargs)
    
                except self.retry_on_exceptions as e:
                    if attempt == self.max_retries - 1:
                        # 마지막 시도 실패
                        raise
    
                    # 대기 후 재시도
                    wait_time = self.backoff_factor ** attempt
                    print(f"⚠️  Retry {attempt + 1}/{self.max_retries} after {wait_time}s: {str(e)}")
                    time.sleep(wait_time)
    
                except Exception as e:
                    # 재시도 불가능한 에러
                    print(f"❌ Non-retryable error: {str(e)}")
                    raise
    
    class RobustRAGEvaluator:
        """견고한 에러 처리를 포함한 평가기"""
    
        def __init__(self, rag_system: RAGSystemInterface):
            self.rag_system = rag_system
            self.evaluator = KoreanRAGEvaluator()
            self.retry_handler = RetryHandler()
    
        def evaluate_safe(
            self,
            question: str,
            ground_truth: str
        ) -> Dict:
            """안전한 평가 - 에러 발생 시 부분 결과 반환"""
    
            result = {
                "question": question,
                "ground_truth": ground_truth,
                "status": "unknown"
            }
    
            try:
                # RAG 시스템 호출 (재시도 포함)
                answer, contexts = self.retry_handler.execute_with_retry(
                    self.rag_system.retrieve_and_generate,
                    question
                )
    
                result["generated_answer"] = answer
                result["contexts"] = contexts
    
                # 평가 수행 (재시도 포함)
                metrics = self.retry_handler.execute_with_retry(
                    self.evaluator.evaluate,
                    question=question,
                    answer=answer,
                    contexts=contexts,
                    ground_truth=ground_truth
                )
    
                result["metrics"] = metrics
                result["status"] = "success"
    
            except Exception as e:
                result["error"] = str(e)
                result["error_type"] = type(e).__name__
                result["status"] = "failed"
                print(f"❌ Evaluation failed for: {question[:50]}... - {str(e)}")
    
            return result
    
```

#### 8.4.3 모니터링 및 로깅
```python
    import logging
    from datetime import datetime
    import json
    
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('rag_evaluation.log'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    class MonitoredRAGEvaluator:
        """모니터링 및 로깅이 포함된 평가기"""
    
        def __init__(self, rag_system: RAGSystemInterface):
            self.rag_system = rag_system
            self.evaluator = KoreanRAGEvaluator()
            self.metrics_log = []
    
        def evaluate_with_monitoring(
            self,
            question: str,
            ground_truth: str
        ) -> Dict:
            """모니터링과 함께 평가"""
    
            start_time = time.time()
            logger.info(f"Starting evaluation for: {question[:50]}...")
    
            try:
                # RAG 시스템 호출
                answer, contexts = self.rag_system.retrieve_and_generate(question)
                logger.info(f"Generated answer ({len(answer)} chars) with {len(contexts)} contexts")
    
                # 평가 수행
                metrics = self.evaluator.evaluate(
                    question=question,
                    answer=answer,
                    contexts=contexts,
                    ground_truth=ground_truth
                )
    
                elapsed = time.time() - start_time
    
                # 메트릭 로깅
                self.metrics_log.append({
                    "timestamp": datetime.now().isoformat(),
                    "question_length": len(question),
                    "answer_length": len(answer),
                    "num_contexts": len(contexts),
                    "metrics": metrics,
                    "elapsed_seconds": elapsed
                })
    
                logger.info(f"✓ Evaluation completed in {elapsed:.2f}s")
                logger.info(f"Metrics: {json.dumps(metrics, indent=2)}")
    
                return {
                    "question": question,
                    "generated_answer": answer,
                    "metrics": metrics,
                    "elapsed_seconds": elapsed
                }
    
            except Exception as e:
                logger.error(f"❌ Evaluation failed: {str(e)}", exc_info=True)
                raise
    
        def export_metrics(self, output_file: str):
            """메트릭 로그 내보내기"""
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.metrics_log, f, ensure_ascii=False, indent=2)
            logger.info(f"✓ Metrics exported to {output_file}")
    
```

### 8.5 문제 해결

#### 8.5.1 일반적인 문제 및 해결책

문제 | 증상 | 원인 | 해결책  
---|---|---|---  
낮은 Faithfulness | 0.5 이하 | 컨텍스트와 답변 불일치 | 프롬프트 개선, retrieval top_k 증가  
낮은 Context Recall | 0.6 이하 | 검색된 문서가 정답 포함 안함 | 임베딩 모델 변경, chunk 크기 조정  
느린 평가 속도 | > 10s/query | OpenAI API 지연 | 배치 처리, 캐싱, 병렬화  
API Rate Limit | 429 에러 | 요청 빈도 초과 | 재시도 로직, 요청 간격 조정  
메모리 부족 | OOM 에러 | 대용량 문서 처리 | 배치 크기 감소, 청크 단위 처리  
  
#### 8.5.2 디버깅 도구
```python
    class RAGDebugger:
        """RAG 시스템 디버깅 도구"""
    
        @staticmethod
        def debug_retrieval(
            rag_system: RAGSystemInterface,
            question: str,
            top_k: int = 5
        ):
            """검색 결과 디버깅"""
            print(f"=== Retrieval Debug ===")
            print(f"Question: {question}")
    
            answer, contexts = rag_system.retrieve_and_generate(question, top_k=top_k)
    
            print(f"\nRetrieved {len(contexts)} contexts:")
            for i, context in enumerate(contexts, 1):
                print(f"\n[Context {i}] ({len(context)} chars)")
                print(context[:200] + "..." if len(context) > 200 else context)
    
            print(f"\nGenerated Answer ({len(answer)} chars):")
            print(answer)
    
        @staticmethod
        def debug_metrics(
            evaluator: KoreanRAGEvaluator,
            question: str,
            answer: str,
            contexts: List[str],
            ground_truth: str
        ):
            """메트릭 계산 디버깅"""
            print(f"=== Metrics Debug ===")
    
            # 각 메트릭 개별 계산 및 출력
            metrics = evaluator.evaluate(
                question=question,
                answer=answer,
                contexts=contexts,
                ground_truth=ground_truth
            )
    
            print(f"\nMetrics:")
            for metric, value in metrics.items():
                status = "✓" if value >= 0.7 else "⚠️" if value >= 0.5 else "✗"
                print(f"{status} {metric}: {value:.3f}")
    
        @staticmethod
        def compare_rag_systems(
            systems: Dict[str, RAGSystemInterface],
            question: str,
            ground_truth: str
        ):
            """여러 RAG 시스템 비교"""
            print(f"=== RAG Systems Comparison ===")
            print(f"Question: {question}")
            print(f"Ground Truth: {ground_truth}")
    
            evaluator = KoreanRAGEvaluator()
            results = {}
    
            for name, system in systems.items():
                print(f"\n--- {name} ---")
                answer, contexts = system.retrieve_and_generate(question)
    
                metrics = evaluator.evaluate(
                    question=question,
                    answer=answer,
                    contexts=contexts,
                    ground_truth=ground_truth
                )
    
                results[name] = {
                    "answer": answer,
                    "num_contexts": len(contexts),
                    "metrics": metrics
                }
    
                print(f"Answer: {answer[:100]}...")
                print(f"Metrics: {json.dumps(metrics, indent=2)}")
    
            # 최고 성능 시스템 식별
            best_system = max(
                results.items(),
                key=lambda x: x[1]['metrics']['faithfulness']
            )
            print(f"\n🏆 Best System: {best_system[0]}")
    
            return results
    
```

#### 8.5.3 문제 해결 체크리스트

**평가 품질 문제**

  * ☐ Golden Dataset 품질 확인 (오타, 불완전한 답변)
  * ☐ RAG 시스템 프롬프트 검토
  * ☐ 검색 파라미터 조정 (top_k, similarity threshold)
  * ☐ 청크 크기 및 오버랩 최적화
  * ☐ 임베딩 모델 평가 (한국어 특화 모델 고려)

**성능 문제**

  * ☐ 배치 처리 활성화
  * ☐ 병렬 처리 workers 수 조정
  * ☐ 캐싱 활성화
  * ☐ OpenAI API 요청 최적화 (batch API 고려)
  * ☐ 프로파일링으로 병목 지점 식별

**에러 처리**

  * ☐ 재시도 로직 구현
  * ☐ Rate limiting 처리
  * ☐ 타임아웃 설정
  * ☐ 에러 로깅 활성화
  * ☐ Fallback 전략 구현

## FAQ

### Q1: OpenAI API 비용은 얼마나 드나요?

**A** : 예상 비용 (gpt-4o-mini 기준):

  * Golden Dataset 생성: 100개 QA 쌍 기준 $0.50-1.00
  * RAG 평가: 100개 QA 쌍 기준 $1.00-2.00

**비용 절감 팁** : - `max_chunks` 파라미터로 테스트 시 샘플 수 제한 - `gpt-4o-mini` 사용 (gpt-4o의 1/10 가격) - 배치 처리로 API 호출 최적화

### Q2: PDF 추출이 제대로 안 될 때는?

**A** : 다음을 시도하세요:

**1단계: pdfplumber 사용**
```bash
    [](<#cb20-1>)# pypdf 대신 pdfplumber 사용 (더 정확함)
    [](<#cb20-2>)pip install pdfplumber
```

시스템이 자동으로 설치된 라이브러리를 감지합니다: - pypdf와 pdfplumber 둘 다 설치되어 있으면 pdfplumber 우선 사용 - `KoreanPDFExtractor` 클래스가 자동 선택

**2단계: 스캔된 PDF (이미지)**

OCR이 필요한 경우:
```bash
    [](<#cb21-1>)pip install pytesseract
    [](<#cb21-2>)# 한글 OCR 모델 설치 필요 (Tesseract-OCR)
```

**3단계: 문제가 계속되면**

직접 텍스트 추출 테스트:
```python
    [](<#cb22-1>)from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanPDFExtractor
    [](<#cb22-2>)
    [](<#cb22-3>)extractor = KoreanPDFExtractor()
    [](<#cb22-4>)print(f"사용 중인 라이브러리: {extractor.library}")
    [](<#cb22-5>)
    [](<#cb22-6>)pages = extractor.extract_text("your.pdf")
    [](<#cb22-7>)print(f"추출된 페이지 수: {len(pages)}")
    [](<#cb22-8>)print(f"첫 페이지 샘플:\n{pages[0][1][:200]}")
```

### Q3: Ragas 메트릭이 너무 낮게 나올 때는?

**A** : 다음을 확인하세요:

  1. **Golden Dataset 품질 확인**
     * Ground truth가 명확한지
     * Context가 충분한지
  2. **RAG 시스템 개선**
     * 검색 top_k 증가
     * 프롬프트 개선
     * 리랭킹 추가
  3. **평가 설정 조정**
     * `ragas_model`을 더 강력한 모델로 변경
     * Ground truth를 더 구체적으로 작성

### Q4: CSV 형식으로 Golden Data를 직접 만들고 싶어요

**A** : Excel에서 다음 형식으로 작성 후 CSV로 저장:

qa_id | question | answer | ground_truth | context  
---|---|---|---|---  
qa_001 | 연차는 몇 일? | 15일입니다 | 15일 | 연차는 1년 근무 시 15일…
```json
    [](<#cb23-1>)manager = GoldenDatasetManager()
    [](<#cb23-2>)dataset = manager.load_dataset("my_dataset.csv")
```
  
### Q5: 평가가 너무 오래 걸려요

**A** : 다음을 시도하세요:
```python
    [](<#cb24-1>)# 1. 샘플 수 제한 (테스트용)
    [](<#cb24-2>)report = evaluator.evaluate_dataset(dataset, max_samples=10)
    [](<#cb24-3>)
    [](<#cb24-4>)# 2. Ragas 비활성화 (빠른 테스트)
    [](<#cb24-5>)evaluator = KoreanRAGEvaluator(use_ragas=False)
    [](<#cb24-6>)
    [](<#cb24-7>)# 3. 병렬 처리 (향후 지원 예정)
```

* * *

## 구현 세부사항

### 주요 클래스 구조

#### 1\. Korean RAG Dataset Generator (`korean_rag_dataset_generator.py`)

**KoreanRAGDatasetGenerator** \- **역할** : PDF에서 Golden Dataset 생성 파이프라인 - **주요 메서드** : - `generate_from_pdf()`: PDF에서 QA 쌍 자동 생성 - **의존 클래스** : - `KoreanPDFExtractor`: PDF 텍스트 추출 - `TextChunker`: 텍스트 청킹 - `KoreanQAGenerator`: OpenAI GPT로 QA 생성 - `GoldenDatasetManager`: 저장/로드/검증

**데이터 클래스** :
```python
    [](<#cb25-1>)@dataclass
    [](<#cb25-2>)class QAPair:
    [](<#cb25-3>)    qa_id: str
    [](<#cb25-4>)    question: str
    [](<#cb25-5>)    answer: str
    [](<#cb25-6>)    context: str
    [](<#cb25-7>)    ground_truth: str
    [](<#cb25-8>)    metadata: Dict[str, Any]
    [](<#cb25-9>)    # Layer 2 필드 (Agentic AI 평가용, 선택적)
    [](<#cb25-10>)    expected_tools: Optional[List[str]] = None
    [](<#cb25-11>)    expected_agents: Optional[List[str]] = None
    [](<#cb25-12>)    expected_workflow_steps: Optional[List[str]] = None
    [](<#cb25-13>)
    [](<#cb25-14>)@dataclass
    [](<#cb25-15>)class GoldenDataset:
    [](<#cb25-16>)    dataset_id: str
    [](<#cb25-17>)    source_document: str
    [](<#cb25-18>)    created_at: str
    [](<#cb25-19>)    total_qa_pairs: int
    [](<#cb25-20>)    qa_pairs: List[QAPair]
    [](<#cb25-21>)    metadata: Dict[str, Any]
```

**KoreanPDFExtractor** : - pypdf 또는 pdfplumber 자동 선택 - `extract_text()`: 페이지별 텍스트 추출 - `clean_text()`: 공백 정리

**TextChunker** : - 문장 경계 인식 청킹 - 한국어 문장부호 지원: `. ! ? 。！？` \- overlap으로 컨텍스트 유지

**KoreanQAGenerator** : - OpenAI API 사용 - 프롬프트에 메타 정보 질문 필터링 포함 - 정규식으로 QA 파싱

#### 2\. Korean RAG Evaluator (`korean_rag_evaluator.py`)

**KoreanRAGEvaluator** \- **역할** : RAG 시스템 평가 및 메트릭 계산 - **주요 메서드** : - `evaluate_dataset()`: Golden Dataset 전체 평가 - `evaluate_single()`: 단일 질문 평가 - `_evaluate_single_qa()`: 개별 QA 평가 로직 - `_calculate_ragas_metrics()`: Ragas 메트릭 계산 - `_generate_report()`: 리포트 생성 - `_save_report()`: JSON/CSV 저장 - `_record_to_monitor()`: Hybrid Monitor 연동

**데이터 클래스** :
```python
    [](<#cb26-1>)@dataclass
    [](<#cb26-2>)class RAGResponse:
    [](<#cb26-3>)    question: str
    [](<#cb26-4>)    answer: str
    [](<#cb26-5>)    retrieved_contexts: List[str]
    [](<#cb26-6>)    metadata: Dict[str, Any]
    [](<#cb26-7>)
    [](<#cb26-8>)@dataclass
    [](<#cb26-9>)class EvaluationResult:
    [](<#cb26-10>)    qa_id: str
    [](<#cb26-11>)    question: str
    [](<#cb26-12>)    expected_answer: str
    [](<#cb26-13>)    generated_answer: str
    [](<#cb26-14>)    contexts: List[str]
    [](<#cb26-15>)    # Ragas 메트릭
    [](<#cb26-16>)    faithfulness: Optional[float] = None
    [](<#cb26-17>)    answer_relevancy: Optional[float] = None
    [](<#cb26-18>)    context_recall: Optional[float] = None
    [](<#cb26-19>)    context_precision: Optional[float] = None
    [](<#cb26-20>)    answer_similarity: Optional[float] = None
    [](<#cb26-21>)    # 메타데이터
    [](<#cb26-22>)    evaluation_time: float = 0.0
    [](<#cb26-23>)    error: Optional[str] = None
    [](<#cb26-24>)    metadata: Dict[str, Any] = None
    [](<#cb26-25>)
    [](<#cb26-26>)@dataclass
    [](<#cb26-27>)class RAGEvaluationReport:
    [](<#cb26-28>)    report_id: str
    [](<#cb26-29>)    dataset_id: str
    [](<#cb26-30>)    evaluated_at: str
    [](<#cb26-31>)    total_qa_pairs: int
    [](<#cb26-32>)    successful_evaluations: int
    [](<#cb26-33>)    failed_evaluations: int
    [](<#cb26-34>)    # 평균 메트릭
    [](<#cb26-35>)    avg_faithfulness: float
    [](<#cb26-36>)    avg_answer_relevancy: float
    [](<#cb26-37>)    avg_context_recall: float
    [](<#cb26-38>)    avg_context_precision: float
    [](<#cb26-39>)    avg_answer_similarity: float
    [](<#cb26-40>)    # 상세 결과
    [](<#cb26-41>)    detailed_results: List[EvaluationResult]
    [](<#cb26-42>)    statistics: Dict[str, Any]
    [](<#cb26-43>)    metadata: Dict[str, Any]
```

**RAGSystemInterface** : - 추상 인터페이스 - `query()` 메서드만 구현하면 됨 - 예제: `SimpleRAGSystem` (더미), `OpenAIRAGSystem` (실제)

### Ragas 통합 방식

`_calculate_ragas_metrics()` 메서드: 1. 데이터를 `EvaluationDataset` / `SingleTurnSample` 형식으로 변환 (ragas 0.4.x API) 2. 메트릭 인스턴스 기반으로 평가 호출: ```python from ragas import EvaluationDataset, SingleTurnSample
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextRecall, ContextPrecision

samples = [SingleTurnSample(user_input=q, response=a, retrieved_contexts=ctx, reference=gt) for ...]
dataset = EvaluationDataset(samples=samples)
result = evaluate(dataset, metrics=[Faithfulness(), AnswerRelevancy(), ContextRecall(), ContextPrecision()])
``` 3. 결과 딕셔너리에서 각 메트릭 추출 4. 에러 발생 시 빈 딕셔너리 반환 (graceful degradation)

### HybridPerformanceMonitor 통합

`_record_to_monitor()` 메서드: 1. `EvaluationResult`를 `TaskResult`로 변환 2. `TaskType.QA` 사용 3. `monitor.record_task()` 호출 4\. 추가 메트릭 활성화: - `enable_advanced_metrics=True` \- `input_text`, `output_text`, `expected_output`, `retrieved_context` 전달

### 파일 저장 형식

**JSON (요약)** :
```json
    [](<#cb27-1>){
    [](<#cb27-2>)  "report_id": "abc12345",
    [](<#cb27-3>)  "dataset_id": "dataset_xyz",
    [](<#cb27-4>)  "evaluated_at": "2024-01-15T10:30:00",
    [](<#cb27-5>)  "total_qa_pairs": 45,
    [](<#cb27-6>)  "successful_evaluations": 43,
    [](<#cb27-7>)  "failed_evaluations": 2,
    [](<#cb27-8>)  "avg_metrics": {
    [](<#cb27-9>)    "faithfulness": 0.892,
    [](<#cb27-10>)    "answer_relevancy": 0.856,
    [](<#cb27-11>)    "context_recall": 0.834,
    [](<#cb27-12>)    "context_precision": 0.878,
    [](<#cb27-13>)    "answer_similarity": 0.823
    [](<#cb27-14>)  },
    [](<#cb27-15>)  "statistics": {...},
    [](<#cb27-16>)  "metadata": {...}
    [](<#cb27-17>)}
```

**JSON (상세 결과)** : 별도 파일 (`rag_evaluation_details_*.json`) - 각 QA 쌍의 `EvaluationResult` 배열

**CSV** : - 각 행이 하나의 QA 평가 결과 - Excel 호환 (utf-8-sig 인코딩)

* * *

## 추가 리소스

### 문서

  * [Agent Evaluator 메인 가이드](<../README.md>)
  * [Ragas 공식 문서](<https://docs.ragas.io/>)
  * [OpenAI API 문서](<https://platform.openai.com/docs>)

### 예제 코드

  * [RAG 지표 평가 예제](<../Evaluator_Examples/01_quality_eval.py>) (RAG Metrics 섹션)
  * [성능 평가 예제](<../Evaluator_Examples/02_performance_eval.py>)

### 커뮤니티

* * *

## 검증 완료 사항

이 가이드는 다음 실제 구현과 비교하여 검증되었습니다:

### 검증된 파일

  1. **`korean_rag_dataset_generator.py`** (850줄) 
     * ✅ KoreanRAGDatasetGenerator 클래스
     * ✅ KoreanPDFExtractor (pypdf, pdfplumber 자동 선택)
     * ✅ TextChunker (한국어 문장 부호 인식)
     * ✅ KoreanQAGenerator (OpenAI GPT 통합)
     * ✅ GoldenDatasetManager (JSON/CSV 저장/로드)
     * ✅ 데이터 클래스: QAPair, GoldenDataset, DocumentChunk
  2. **`korean_rag_evaluator.py`** (690줄) 
     * ✅ KoreanRAGEvaluator 클래스
     * ✅ RAGSystemInterface (추상 인터페이스)
     * ✅ Ragas 통합 (5개 메트릭)
     * ✅ HybridPerformanceMonitor 통합
     * ✅ 데이터 클래스: RAGResponse, EvaluationResult, RAGEvaluationReport
     * ✅ SimpleRAGSystem 예제 구현
  3. **`Evaluator_Examples/01_quality_eval.py`** (RAG Metrics 섹션)
     * ✅ OpenAIRAGSystem 구현 예제
     * ✅ Golden Dataset 생성 예제
     * ✅ 더미 데이터셋 생성
     * ✅ CSV 로드 예제
     * ✅ 수동 Golden Data 입력 예제

### 검증된 기능

**PDF 처리** : - ✅ pypdf 지원 (기본) - ✅ pdfplumber 지원 (자동 우선 선택) - ✅ 한국어 텍스트 추출 - ✅ 텍스트 정제 (clean_text)

**텍스트 청킹** : - ✅ 문장 경계 인식 - ✅ 한국어 문장 부호: `. ! ? 。！？` \- ✅ chunk_overlap 지원 - ✅ 청크 ID 자동 생성 (MD5 해시 사용)

**QA 생성** : - ✅ OpenAI API 통합 - ✅ gpt-4o-mini, gpt-4o 모델 지원 - ✅ 메타 정보 질문 필터링 프롬프트 - ✅ factual, reasoning, summary 질문 유형 - ✅ 정규식 기반 QA 파싱

**RAG 평가** : - ✅ RAGSystemInterface 기반 통합 - ✅ Ragas 5개 메트릭 계산 - ✅ 배치 평가 - ✅ 에러 처리 (graceful degradation) - ✅ 진행 상황 출력

**Ragas 메트릭** : - ✅ Faithfulness (환각 탐지) - ✅ Answer Relevancy (답변 관련성) - ✅ Context Recall (검색 재현율) - ✅ Context Precision (검색 정밀도) - ✅ Answer Similarity (답변 유사도)

**저장/로드** : - ✅ JSON 형식 (요약 + 상세 결과 분리) - ✅ CSV 형식 (Excel 호환, utf-8-sig) - ✅ 데이터 검증 (validate_dataset)

**고급 기능** : - ✅ HybridPerformanceMonitor 통합 - ✅ TaskResult 변환 - ✅ 평가 시간 추적 - ✅ 성공/실패 통계

### 문서 개선 사항

이번 검증을 통해 다음 사항들이 개선되었습니다:

  1. **실제 구현 반영** : 
     * 클래스 구조와 메서드명 정확히 반영
     * 실제 데이터 클래스 필드 명시
     * 에러 처리 및 graceful degradation 설명
  2. **상세한 설명 추가** : 
     * PDF 라이브러리 자동 선택 로직
     * 한국어 문장 부호 지원
     * Ragas 메트릭 계산 방법 상세 설명
     * HybridPerformanceMonitor 통합 방식
  3. **사용 예제 개선** : 
     * RAGSystemInterface 구현 가이드
     * RAGResponse 필드 설명
     * 청크 크기 선택 가이드
     * 질문 유형 상세 설명
  4. **구현 세부사항 섹션 추가** : 
     * 주요 클래스 구조
     * Ragas 통합 방식
     * HybridPerformanceMonitor 통합
     * 파일 저장 형식

* * *

## 라이센스

MIT License - 자유롭게 사용, 수정, 배포 가능합니다.

* * *

* * *

**최종 업데이트** : 2026-04-01
**버전** : Agent Evaluator v0.7.2
**프로젝트** : Agent Evaluator - AI Agent Performance Evaluation System
**문서** : Korean RAG Evaluation Guide
