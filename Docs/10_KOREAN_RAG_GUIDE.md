# 한국어 RAG 평가 가이드

Golden Dataset 생성 및 RAG 시스템 평가 완벽 가이드 — Agent Evaluator v0.7.6

## 목차

1. [개요](#개요)
2. [설치](#설치)
3. [Golden Dataset 생성](#golden-dataset-생성)
4. [RAG 시스템 평가](#rag-시스템-평가)
5. [평가 메트릭](#평가-메트릭)
6. [데코레이터 방식 RAG 평가](#데코레이터-방식-rag-평가)
7. [PerformanceMonitor 통합](#performancemonitor-통합)
8. [고급 사용법](#고급-사용법)
9. [실전 예제: 기업 정책 문서 평가](#실전-예제)
10. [문제 해결](#문제-해결)
11. [FAQ](#faq)
12. [클래스 참조](#클래스-참조)

---

## 개요

이 시스템은 기업 환경에서 한국어 RAG (Retrieval-Augmented Generation) 시스템을 평가하기 위한 완전한 솔루션을 제공합니다.

### 주요 기능

- **PDF에서 Ground Truth 자동 생성** — OpenAI GPT를 활용하여 한국어 PDF 문서에서 QA 쌍 자동 생성
- **표준 RAG 메트릭 평가** — Faithfulness, Context Recall, Context Precision, Answer Relevancy, Answer Similarity
- **다양한 입출력 형식** — JSON, CSV 지원
- **유연한 통합** — `RAGSystemInterface`를 통한 기존 RAG 시스템과의 쉬운 통합
- **고급 평가** — `HybridPerformanceMonitor`를 통한 심층 분석 (선택적)
- **데코레이터 방식** — `QuickEval.for_rag()`로 2줄 시작

### 워크플로우

```
PDF 문서 입력
    ↓
KoreanRAGDatasetGenerator (AI 기반 QA 쌍 생성)
    ↓
GoldenDataset 저장 (JSON/CSV)
    ↓
KoreanRAGEvaluator (Faithfulness / Context Recall 등 측정)
    ↓
평가 리포트 생성
```

---

## 설치

```bash
# 핵심 + RAG 평가 의존성
pip install agent-evaluator[eval]

# 또는 개별 설치
pip install agent-evaluator
pip install pypdf openai python-dotenv    # Golden Dataset 생성용
pip install ragas langchain-openai datasets  # RAG 평가용 (Ragas)
pip install pdfplumber                    # PDF 추출 개선 (권장)
pip install deepeval                      # 선택: DeepEval 고급 메트릭
```

**라이브러리 선택 가이드**:

| 라이브러리 | 용도 | 비고 |
|-----------|------|------|
| `pypdf` | 기본 PDF 텍스트 추출 | 빠름 |
| `pdfplumber` | 더 정확한 텍스트 추출 | 권장 (복잡한 레이아웃) |
| `ragas` | Faithfulness, Context Recall 등 계산 | 필수 |
| `deepeval` | G-Eval, Hallucination, Toxicity | 선택 |

### 환경 변수 설정

```bash
# .env 파일
OPENAI_API_KEY=your-openai-api-key-here
```

---

## Golden Dataset 생성

### 방법 1: PDF에서 자동 생성

가장 일반적인 방법으로, 한국어 PDF 문서에서 AI를 활용하여 QA 쌍을 자동 생성합니다.

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator

# Generator 초기화
generator = KoreanRAGDatasetGenerator(
    model="gpt-4o-mini",        # 또는 "gpt-4o" (더 비싸지만 품질 좋음)
    chunk_size=800,             # 청크 크기 (문자 수)
    chunk_overlap=150,          # 청크 간 겹침
    output_dir="golden_datasets"
)

# PDF에서 Golden Dataset 생성
dataset = generator.generate_from_pdf(
    pdf_path="company_policy.pdf",
    num_questions_per_chunk=3,
    question_types=["factual", "reasoning", "summary"],
    save_format="json",          # "json" 또는 "csv"
    max_chunks=None              # None이면 전체, 숫자면 테스트용 샘플링
)
```

#### 생성 프로세스

1. **PDF 텍스트 추출** — `KoreanPDFExtractor`로 pypdf/pdfplumber 자동 선택 (pdfplumber 우선)
2. **텍스트 정제** — `clean_text()`로 불필요한 공백 제거
3. **텍스트 청킹** — `TextChunker`로 의미 단위 분할 (한국어 문장 부호 자동 인식: `. ! ? 。！？`)
4. **QA 쌍 생성** — `KoreanQAGenerator`로 OpenAI GPT 기반 질문-답변-ground_truth 생성
5. **검증 및 저장** — `GoldenDatasetManager`로 품질 검증 후 JSON/CSV 저장

#### 출력 예시

```json
{
  "dataset_id": "dataset_abc12345",
  "source_document": "company_policy.pdf",
  "created_at": "2026-04-10T10:30:00",
  "total_qa_pairs": 45,
  "qa_pairs": [
    {
      "qa_id": "chunk_p1_i0_qa0",
      "question": "회사의 연차 휴가 정책은 어떻게 되나요?",
      "answer": "직원은 1년 근무 시 15일의 연차 휴가를 받을 수 있으며...",
      "context": "당사의 연차 휴가 정책에 따르면...",
      "ground_truth": "1년 근무 시 15일의 연차 휴가",
      "metadata": {
        "chunk_id": "chunk_p1_i0_abc123",
        "page_number": 1
      }
    }
  ]
}
```

### 방법 2: 수동으로 QA 쌍 입력

기존 데이터나 전문가가 작성한 QA 쌍을 사용할 수 있습니다.

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import (
    QAPair, GoldenDataset, GoldenDatasetManager
)
from datetime import datetime

qa_pairs = [
    QAPair(
        qa_id="manual_001",
        question="기업의 주요 제품은 무엇인가요?",
        answer="스마트폰, 태블릿, 웨어러블 기기입니다.",
        context="당사는 스마트폰, 태블릿, 웨어러블 기기를 주력 제품으로...",
        ground_truth="스마트폰, 태블릿, 웨어러블 기기",
        metadata={"source": "company_info"}
    ),
    # ... 더 많은 QA 쌍
]

dataset = GoldenDataset(
    dataset_id="manual_dataset",
    source_document="manual_input",
    created_at=datetime.now().isoformat(),
    total_qa_pairs=len(qa_pairs),
    qa_pairs=qa_pairs,
    metadata={"input_type": "manual"}
)

manager = GoldenDatasetManager()
saved_path = manager.save_dataset(dataset, format="json")
```

### 방법 3: CSV 파일에서 로드

Excel/스프레드시트에서 작성한 데이터를 사용하려면 다음 형식으로 CSV를 준비합니다:

```
qa_id,question,answer,ground_truth,context,chunk_id,page_number,generated_at
qa_001,회사 설립 연도는?,2010년에 설립되었습니다,2010년,당사는 2010년에 설립되어...,chunk_001,1,2026-04-10
qa_002,직원 수는?,약 500명입니다,약 500명,현재 약 500명의 직원이...,chunk_002,1,2026-04-10
```

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager

manager = GoldenDatasetManager()
dataset = manager.load_dataset("golden_datasets/my_dataset.csv")
print(f"로드 완료: {dataset.total_qa_pairs}개 QA 쌍")
```

---

## RAG 시스템 평가

### 1. RAGSystemInterface 구현

평가를 위해 RAG 시스템을 `RAGSystemInterface`에 맞춰 구현합니다. `query()` 메서드만 구현하면 됩니다.

```python
from agent_evaluator.datasets.korean_rag_evaluator import RAGSystemInterface, RAGResponse

class MyRAGSystem(RAGSystemInterface):
    def __init__(self):
        self.vector_db = ...  # Chroma, Pinecone, Qdrant 등
        self.llm = ...        # OpenAI, Anthropic, local model 등

    def query(self, question: str) -> RAGResponse:
        # 1. 벡터 검색
        retrieved_docs = self.vector_db.search(question, top_k=3)

        # 2. LLM으로 답변 생성
        context_text = "\n\n".join(retrieved_docs)
        prompt = f"""다음 문서를 참고하여 질문에 답변하세요.

[문서]
{context_text}

[질문]
{question}

[답변]
"""
        answer = self.llm.generate(prompt)

        # 3. 응답 반환 (필수: question, answer, retrieved_contexts)
        return RAGResponse(
            question=question,
            answer=answer,
            retrieved_contexts=retrieved_docs,  # List[str] 형태
            metadata={"num_retrieved": len(retrieved_docs)}
        )
```

**RAGResponse 필드**:

| 필드 | 타입 | 설명 |
|------|------|------|
| `question` | str | 질문 |
| `answer` | str | 생성된 답변 |
| `retrieved_contexts` | List[str] | 검색된 컨텍스트 리스트 |
| `metadata` | Dict | 추가 정보 (선택적) |

### 2. 평가 실행

```python
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator
from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager

# Golden Dataset 로드
manager = GoldenDatasetManager()
dataset = manager.load_dataset("golden_datasets/my_dataset.json")

# RAG 시스템 초기화
rag_system = MyRAGSystem()

# 평가기 초기화
evaluator = KoreanRAGEvaluator(
    rag_system=rag_system,
    use_ragas=True,
    ragas_model="gpt-4o-mini",
    output_dir="evaluation_results"
)

# 평가 실행
report = evaluator.evaluate_dataset(
    dataset,
    use_hybrid_monitor=False,  # True로 설정하면 HybridPerformanceMonitor 활성화
    max_samples=None           # None이면 전체 평가, 숫자면 샘플링
)
```

### 3. 평가 결과 예시

```
================================================================================
RAG 평가 리포트
================================================================================

리포트 ID: a1b2c3d4
평가 시간: 2026-04-10T11:30:00
총 QA 쌍: 45개  |  성공: 43개  |  실패: 2개  |  성공률: 95.6%

================================================================================
Ragas 메트릭 (평균)
================================================================================

Faithfulness       : 0.892  (목표: >= 0.8)
Answer Relevancy   : 0.856  (목표: >= 0.8)
Context Recall     : 0.834  (목표: >= 0.8)
Context Precision  : 0.878  (목표: >= 0.8)
Answer Similarity  : 0.823  (목표: >= 0.8)
================================================================================
```

---

## 평가 메트릭

### Faithfulness (충실도)

생성된 답변이 검색된 컨텍스트에 얼마나 충실한지 측정합니다 (환각 방지).

- **계산**: 답변에서 주장(claims)을 추출 → 각 주장이 컨텍스트에서 뒷받침되는지 검증 → `뒷받침된 주장 수 / 전체 주장 수`
- **목표**: >= 0.8
- **개선 방법**: 프롬프트에 "문서에 없는 내용은 답변하지 말 것" 명시 / temperature 낮춤 (0.1~0.3)

### Answer Relevancy (답변 관련성)

답변이 질문과 얼마나 관련있는지 측정합니다.

- **계산**: 답변에서 역으로 질문들을 생성 → 생성된 질문과 원래 질문의 임베딩 유사도 계산
- **목표**: >= 0.8
- **개선 방법**: 프롬프트에 질문에 직접 답하도록 명시 / 핵심 키워드를 답변에 포함

### Context Recall (컨텍스트 재현율)

Ground truth를 생성하는 데 필요한 정보가 검색된 컨텍스트에 포함되어 있는지 측정합니다.

- **계산**: Ground truth를 문장들로 분리 → 각 문장이 컨텍스트에서 추론 가능한지 검증 → `추론 가능한 문장 수 / 전체 문장 수`
- **목표**: >= 0.8
- **개선 방법**: 검색 top_k 증가 / multilingual 임베딩 모델 사용 / 하이브리드 검색 (벡터 + 키워드)

### Context Precision (컨텍스트 정밀도)

검색된 컨텍스트가 질문에 얼마나 관련 있는지 측정합니다 (노이즈 최소화).

- **계산**: 검색된 각 컨텍스트가 Ground truth와 관련 있는지 판단 → Precision@K 평균
- **목표**: >= 0.8
- **개선 방법**: 리랭킹 모델 추가 (Cohere Rerank) / 쿼리 확장 / 메타데이터 필터링

### Answer Similarity (답변 유사도)

생성된 답변이 Ground truth와 얼마나 의미적으로 유사한지 측정합니다.

- **계산**: 답변과 Ground truth의 임베딩 코사인 유사도
- **목표**: >= 0.8
- **개선 방법**: 프롬프트 개선 / Few-shot 예시 추가 / Ground truth 품질 개선

---

## 데코레이터 방식 RAG 평가

### QuickEval.for_rag() 사용 (권장)

```python
from agent_evaluator import QuickEval

# RAG 최적화 설정으로 초기화 (hallucination_detection 자동 활성화)
eval = QuickEval.for_rag("results/")

@eval.rag  # task_type="information_retrieval" + hallucination detection 자동 적용
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    # 실제 RAG 시스템 호출
    retrieved = vector_db.search(question, top_k=3)
    context = "\n".join(retrieved)
    return llm.generate(question, context)

# 평가 실행
for qa in golden_dataset.qa_pairs:
    rag_agent(
        question=qa.question,
        context=qa.context,
        ground_truth=qa.ground_truth
    )

eval.save()                          # results/quickeval.json + quickeval.html
eval.gate(tcr=85, accuracy=70)       # CI/CD 품질 게이트
```

### PerformanceMonitor.for_rag_evaluation() 사용

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# RAG 평가 최적 설정 (hallucination_detection=True 자동 적용)
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

@agent_eval(monitor, task_type="information_retrieval", rag_mode=True)
def rag_agent(question: str, ground_truth: str = "") -> str:
    retrieved = vector_db.search(question, top_k=3)
    context = "\n".join(retrieved)
    return llm.generate(question, context)

# 평가 실행
for qa in golden_dataset.qa_pairs:
    rag_agent(qa.question, ground_truth=qa.ground_truth)

report = monitor.generate_report()
monitor.save_to_file("rag_evaluation")
```

---

## PerformanceMonitor 통합

### 기본 사용법

`PerformanceMonitor`로 RAG 메트릭을 직접 추적하고 품질 게이트를 구현할 수 있습니다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator

# Monitor 초기화 및 Threshold 설정
monitor = PerformanceMonitor()
monitor.thresholds = {
    "faithfulness": 0.8,
    "answer_relevancy": 0.85,
    "context_recall": 0.75,
    "context_precision": 0.8
}

# 단일 평가
rag_evaluator = KoreanRAGEvaluator(rag_system=my_rag_system)
result = rag_evaluator.evaluate_single(
    question="한국의 수도는 어디인가요?",
    expected_answer="서울입니다"
)

# Monitor에 RAG 메트릭 기록
monitor.record_rag_metrics(
    faithfulness=result.faithfulness,
    answer_relevancy=result.answer_relevancy,
    context_recall=result.context_recall,
    context_precision=result.context_precision
)

# Threshold와 자동 비교 (실제 평균값 계산 + pass/fail 판정)
comparison = monitor.compare_with_thresholds()

for metric in ["faithfulness", "answer_relevancy", "context_recall", "context_precision"]:
    data = comparison[metric]
    status = "pass" if data["status"] == "pass" else "FAIL"
    print(f"[{status}] {data['name']}: {data['value']:.3f} (임계값: {data['threshold']})")
```

**출력 예시**:
```
[pass] Faithfulness: 0.850 (임계값: 0.8)
[pass] Answer Relevancy: 0.880 (임계값: 0.85)
[pass] Context Recall: 0.780 (임계값: 0.75)
[pass] Context Precision: 0.820 (임계값: 0.8)
```

### Dataset 전체 평가 + 품질 게이트

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator
from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager

monitor = PerformanceMonitor()
monitor.thresholds = {
    "faithfulness": 0.8,
    "answer_relevancy": 0.85,
    "context_recall": 0.75,
    "context_precision": 0.8
}

manager = GoldenDatasetManager()
dataset = manager.load_dataset("golden_datasets/hr_policy_dataset.json")

rag_evaluator = KoreanRAGEvaluator(
    rag_system=my_rag_system,
    use_ragas=True,
    ragas_model="gpt-4o-mini"
)

# 각 QA 쌍 평가 및 기록
for qa_pair in dataset.qa_pairs:
    result = rag_evaluator.evaluate_single(
        question=qa_pair.question,
        expected_answer=qa_pair.ground_truth
    )
    monitor.record_rag_metrics(
        faithfulness=result.faithfulness,
        answer_relevancy=result.answer_relevancy,
        context_recall=result.context_recall,
        context_precision=result.context_precision
    )

# 품질 게이트 체크
comparison = monitor.compare_with_thresholds()
failed_metrics = [m for m, d in comparison.items() if d["status"] == "fail"]

if failed_metrics:
    print(f"RAG 품질 게이트 실패! 실패 메트릭: {len(failed_metrics)}개")
    for metric in failed_metrics:
        data = comparison[metric]
        print(f"  - {data['name']}: {data['value']:.3f} (필요: {data['threshold']})")
else:
    print("RAG 품질 게이트 통과!")

# 메트릭 요약
rag_summary = monitor.get_rag_metrics_summary()
print(f"\n평균 Faithfulness: {rag_summary['faithfulness']['mean']:.3f}")
print(f"평균 Answer Relevancy: {rag_summary['answer_relevancy']['mean']:.3f}")
```

### Threshold 권장 설정

| 메트릭 | 일반적 | 엄격함 | 관대함 | 용도 |
|--------|--------|--------|--------|------|
| `faithfulness` | >= 0.8 | >= 0.9 | >= 0.7 | 환각 방지 (가장 중요) |
| `answer_relevancy` | >= 0.85 | >= 0.9 | >= 0.75 | 답변 품질 |
| `context_recall` | >= 0.75 | >= 0.85 | >= 0.65 | 검색 완전성 |
| `context_precision` | >= 0.8 | >= 0.9 | >= 0.7 | 검색 정확도 |

- **프로덕션 RAG 시스템**: 일반적 설정
- **의료/금융/법률 시스템**: 엄격한 설정 (특히 faithfulness >= 0.9)
- **개발/테스트 환경**: 관대한 설정
- **CI/CD 품질 게이트**: 일반적 설정으로 자동 배포 차단

---

## 고급 사용법

### 커스텀 질문 유형

```python
dataset = generator.generate_from_pdf(
    pdf_path="document.pdf",
    num_questions_per_chunk=5,
    question_types=["factual", "reasoning", "summary", "comparison", "opinion"],
)
```

| 질문 유형 | 설명 |
|----------|------|
| `factual` | 사실 확인 질문 |
| `reasoning` | 추론 질문 |
| `summary` | 요약 질문 |
| `comparison` | 비교 질문 |
| `opinion` | 의견 질문 |

### 청크 크기 최적화

```python
# 짧은 청크 (세밀한 정보, 빠른 검색)
generator = KoreanRAGDatasetGenerator(chunk_size=500, chunk_overlap=100)

# 중간 청크 (균형잡힌 설정 — 권장)
generator = KoreanRAGDatasetGenerator(chunk_size=800, chunk_overlap=150)

# 긴 청크 (풍부한 맥락, 복잡한 추론)
generator = KoreanRAGDatasetGenerator(chunk_size=1500, chunk_overlap=300)
```

**문서 유형별 권장 설정** (문자 수 기준):

| 문서 유형 | chunk_size | overlap |
|----------|-----------|---------|
| 기술 문서 (코드, API) | 800~1000 | 150~200 |
| 정책/법률 (복잡한 조항) | 1000~1500 | 200~300 |
| 일반 문서 (뉴스, 블로그) | 600~800 | 100~150 |
| FAQ/간단한 정보 | 400~600 | 80~120 |

### HybridPerformanceMonitor 통합

`use_hybrid_monitor=True`로 DeepEval, Ragas 통합 심층 분석을 활성화합니다.

```python
report = evaluator.evaluate_dataset(
    dataset,
    use_hybrid_monitor=True,
    max_samples=None
)

# Hybrid Monitor의 추가 메트릭 확인
if evaluator.monitor:
    print(f"모니터링된 태스크 수: {len(evaluator.monitor.extended_tasks)}")
    hybrid_report = evaluator.monitor.generate_report()
```

**Hybrid Monitor 기능**:
- 확장된 메트릭: DeepEval (G-Eval, Hallucination, Toxicity, Bias)
- 태스크 추적: 각 QA 평가를 `TaskResult`로 기록
- 통합 리포트: Native + Ragas + DeepEval 메트릭을 하나의 리포트로
- 성능 분석: 평가 시간, 성공률, 오류 추적

### GoldenSetBuilder 통합

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(output_dir="data/golden_datasets/")

# 고품질 평가 결과를 골든 케이스로 추가
builder.add_case(
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    score=0.95,
    metadata={"source": "hr_policy.pdf"}
)

# 저장 및 Phoenix 업로드 (선택)
builder.merge_to_golden()
# builder.push_to_phoenix(cases, "hr_policy_dataset")
```

---

## 실전 예제

### 시나리오: 기업 인사 정책 문서 평가

회사의 인사 정책 PDF를 RAG 시스템에 적용하고, 직원들의 질문에 정확하게 답변하는지 평가합니다.

### 1단계: Golden Dataset 생성

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator

generator = KoreanRAGDatasetGenerator(
    model="gpt-4o-mini",
    chunk_size=800,
    chunk_overlap=150
)

dataset = generator.generate_from_pdf(
    pdf_path="company_hr_policy.pdf",
    num_questions_per_chunk=4,
    question_types=["factual", "reasoning"],
    save_format="json"
)

print(f"생성 완료: {dataset.total_qa_pairs}개 QA 쌍")
```

### 2단계: RAG 시스템 구축

```python
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from agent_evaluator.datasets.korean_rag_evaluator import RAGSystemInterface, RAGResponse

class HRPolicyRAG(RAGSystemInterface):
    def __init__(self, pdf_path: str):
        loader = PyPDFLoader(pdf_path)
        documents = loader.load()

        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
        splits = splitter.split_documents(documents)

        self.vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=OpenAIEmbeddings()
        )
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

    def query(self, question: str) -> RAGResponse:
        docs = self.vectorstore.similarity_search(question, k=3)
        contexts = [doc.page_content for doc in docs]
        context_text = "\n\n".join(contexts)

        prompt = f"""다음 회사 정책 문서를 참고하여 질문에 답변하세요.
답변은 문서의 내용만을 기반으로 하며, 확실하지 않으면 "문서에 명시되지 않음"이라고 답하세요.

[문서]
{context_text}

[질문]
{question}

[답변]
"""
        answer = self.llm.predict(prompt)

        return RAGResponse(
            question=question,
            answer=answer,
            retrieved_contexts=contexts,
            metadata={"model": "gpt-4o-mini"}
        )
```

### 3단계: QuickEval 데코레이터로 평가

```python
from agent_evaluator import QuickEval

rag_system = HRPolicyRAG("company_hr_policy.pdf")
eval = QuickEval.for_rag("results/")

@eval.rag
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    response = rag_system.query(question)
    return response.answer

from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager
manager = GoldenDatasetManager()
dataset = manager.load_dataset("golden_datasets/hr_policy_dataset.json")

for qa in dataset.qa_pairs:
    rag_agent(
        question=qa.question,
        context=qa.context,
        ground_truth=qa.ground_truth
    )

eval.save()
eval.gate(tcr=85, accuracy=70)
```

### 4단계: KoreanRAGEvaluator로 상세 평가

```python
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator

evaluator = KoreanRAGEvaluator(
    rag_system=rag_system,
    use_ragas=True,
    ragas_model="gpt-4o-mini"
)

report = evaluator.evaluate_dataset(dataset)

if report.avg_faithfulness >= 0.8:
    print("RAG 시스템이 정책 문서에 충실합니다")
else:
    print("환각(hallucination) 문제가 있습니다")

if report.avg_context_recall >= 0.8:
    print("검색 성능이 우수합니다")
else:
    print("검색 성능 개선이 필요합니다")
```

---

## 문제 해결

### 일반적인 문제

| 문제 | 증상 | 원인 | 해결책 |
|------|------|------|--------|
| 낮은 Faithfulness | 0.5 이하 | 컨텍스트와 답변 불일치 | 프롬프트 개선, top_k 증가 |
| 낮은 Context Recall | 0.6 이하 | 검색된 문서가 정답 미포함 | 임베딩 모델 변경, chunk 크기 조정 |
| 느린 평가 속도 | > 10s/query | OpenAI API 지연 | `max_samples` 제한, `use_ragas=False` 테스트 |
| API Rate Limit | 429 에러 | 요청 빈도 초과 | 요청 간격 조정, 배치 처리 |
| PDF 추출 불량 | 빈 텍스트 | 스캔된 PDF (이미지) | pdfplumber 설치 또는 OCR 사용 |

### PDF 추출 문제 진단

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanPDFExtractor

extractor = KoreanPDFExtractor()
print(f"사용 중인 라이브러리: {extractor.library}")  # "pdfplumber" 또는 "pypdf"

pages = extractor.extract_text("your.pdf")
print(f"추출된 페이지 수: {len(pages)}")
print(f"첫 페이지 샘플:\n{pages[0][1][:200]}")
```

### 평가 속도 개선

```python
# 1. 샘플 수 제한 (테스트용)
report = evaluator.evaluate_dataset(dataset, max_samples=10)

# 2. Ragas 비활성화 (빠른 기능 테스트)
evaluator = KoreanRAGEvaluator(use_ragas=False)
```

---

## FAQ

**Q1: OpenAI API 비용은 얼마나 드나요?**

gpt-4o-mini 기준 예상 비용:
- Golden Dataset 생성: 100개 QA 쌍 → $0.50~1.00
- RAG 평가 (Ragas): 100개 QA 쌍 → $1.00~2.00

비용 절감: `max_chunks` 파라미터로 테스트 시 샘플 제한, `gpt-4o-mini` 사용 (gpt-4o의 1/10 가격)

**Q2: PDF 추출이 제대로 안 될 때는?**

pdfplumber를 먼저 시도합니다 — 시스템이 자동으로 설치된 라이브러리를 선택합니다 (pdfplumber 우선).

스캔된 PDF (이미지)인 경우 OCR이 필요합니다:
```bash
pip install pytesseract
# Tesseract-OCR 한글 모델 별도 설치 필요
```

**Q3: Ragas 메트릭이 너무 낮게 나올 때는?**

1. **Golden Dataset 품질 확인** — Ground truth가 명확한지, Context가 충분한지
2. **RAG 시스템 개선** — 검색 top_k 증가, 리랭킹 추가
3. **평가 설정 조정** — `ragas_model`을 더 강력한 모델로 변경

**Q4: CSV 형식으로 Golden Data를 직접 만들고 싶어요**

Excel에서 다음 형식으로 작성 후 CSV로 저장하세요:

| qa_id | question | answer | ground_truth | context |
|-------|----------|--------|--------------|---------|
| qa_001 | 연차는 몇 일? | 15일입니다 | 15일 | 연차는 1년 근무 시 15일... |

```python
manager = GoldenDatasetManager()
dataset = manager.load_dataset("my_dataset.csv")
```

---

## 클래스 참조

### KoreanRAGDatasetGenerator

PDF에서 Golden Dataset 생성 파이프라인.

| 메서드 | 설명 |
|--------|------|
| `generate_from_pdf(pdf_path, ...)` | PDF에서 QA 쌍 자동 생성 |

내부 의존 클래스:
- `KoreanPDFExtractor` — pypdf/pdfplumber 자동 선택
- `TextChunker` — 한국어 문장 부호 인식 청킹 (`. ! ? 。！？`)
- `KoreanQAGenerator` — OpenAI GPT 기반 QA 생성
- `GoldenDatasetManager` — JSON/CSV 저장/로드/검증

### KoreanRAGEvaluator

RAG 시스템 평가 및 Ragas 메트릭 계산.

| 메서드 | 설명 |
|--------|------|
| `evaluate_dataset(dataset, ...)` | Golden Dataset 전체 평가 |
| `evaluate_single(question, ...)` | 단일 질문 평가 |
| `_calculate_ragas_metrics()` | Ragas 0.4.x API 기반 메트릭 계산 |

### 데이터 클래스

```python
@dataclass
class QAPair:
    qa_id: str
    question: str
    answer: str
    context: str
    ground_truth: str
    metadata: Dict[str, Any]
    expected_tools: Optional[List[str]] = None
    expected_agents: Optional[List[str]] = None

@dataclass
class RAGResponse:
    question: str
    answer: str
    retrieved_contexts: List[str]
    metadata: Dict[str, Any]

@dataclass
class RAGEvaluationReport:
    report_id: str
    dataset_id: str
    evaluated_at: str
    total_qa_pairs: int
    successful_evaluations: int
    failed_evaluations: int
    avg_faithfulness: float
    avg_answer_relevancy: float
    avg_context_recall: float
    avg_context_precision: float
    avg_answer_similarity: float
    detailed_results: List[EvaluationResult]
    statistics: Dict[str, Any]
    metadata: Dict[str, Any]
```

### Ragas 통합 방식

`_calculate_ragas_metrics()` 내부 동작:

```python
from ragas import EvaluationDataset, SingleTurnSample
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextRecall, ContextPrecision

samples = [
    SingleTurnSample(
        user_input=q,
        response=a,
        retrieved_contexts=ctx,
        reference=gt
    )
    for q, a, ctx, gt in qa_data
]
dataset = EvaluationDataset(samples=samples)
result = evaluate(dataset, metrics=[Faithfulness(), AnswerRelevancy(), ContextRecall(), ContextPrecision()])
```

에러 발생 시 빈 딕셔너리 반환 (graceful degradation).

---

## 추가 리소스

- [Agent Evaluator 메인 가이드](../README.md)
- [Ragas 공식 문서](https://docs.ragas.io/)
- [OpenAI API 문서](https://platform.openai.com/docs)
- [RAG 지표 평가 예제](../Evaluator_Examples/01_layer1_all_metrics.py)
- [하이브리드 평가 예제](../Evaluator_Examples/07_phoenix_hybrid.py)

---

**문서 버전**: v0.7.6  
**최종 업데이트**: 2026-04-10
