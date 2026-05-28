# 데이터 가이드

골든 데이터셋 구성 · 한국어 RAG 평가 · PDF 파이프라인

**v0.9.4 | Python 3.8+**

---

## 목차

1. [개요](#1-개요)
2. [QAPair 구조](#2-qapair-구조)
3. [골든 데이터셋 생성 방법](#3-골든-데이터셋-생성-방법)
4. [GoldenSetBuilder API](#4-goldensetbuilder-api)
5. [에이전트 평가 루프](#5-에이전트-평가-루프)
6. [한국어 RAG 평가 파이프라인](#6-한국어-rag-평가-파이프라인)
7. [RAG 평가 메트릭](#7-rag-평가-메트릭)
8. [데코레이터 방식 RAG 평가](#8-데코레이터-방식-rag-평가)
9. [KoreanRAGEvaluator 상세](#9-koreanragevaluator-상세)
10. [실전 예제: 기업 정책 문서](#10-실전-예제-기업-정책-문서)
11. [Phoenix 업로드](#11-phoenix-업로드)
12. [Best Practices](#12-best-practices)

---

## 1. 개요

**Golden Dataset**은 에이전트의 정확도와 일관성을 반복적으로 검증하기 위한 레퍼런스 QA 쌍 모음입니다.

- **회귀 방지** — 신규 배포 전 기존 능력이 저하되지 않았음을 자동 확인
- **CI/CD 통합** — `agent-eval gate`와 연동해 품질 기준 미달 시 파이프라인 중단
- **점진적 확장** — 운영 결과에서 우수한 케이스를 자동 추출해 데이터셋 확장

기본 저장 경로: `data/golden_datasets/`

---

## 2. QAPair 구조

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `qa_id` | `str` | ✅ | 고유 식별자 (예: `"qa_001"`) |
| `question` | `str` | ✅ | 에이전트에게 전달할 질문 |
| `answer` | `str` | ✅ | 에이전트가 실제로 생성한 답변 (또는 기대 답변) |
| `context` | `str` | ✅ | RAG 컨텍스트 또는 관련 배경 정보 |
| `ground_truth` | `str` | ✅ | 정답 기준 (정확도 측정에 사용) |
| `metadata` | `Dict[str, Any]` | ✅ | 소스 파일, 생성 날짜 등 부가 정보 |
| `expected_tools` | `List[str]` | ❌ | Layer 2: Tool Selection 평가용 기대 도구 목록 |
| `expected_agents` | `List[str]` | ❌ | Layer 2: Agent Coordination 평가용 기대 에이전트 |
| `expected_workflow_steps` | `List[str]` | ❌ | Layer 2: Workflow Execution 평가용 기대 단계 |

```json
{
  "qa_pairs": [
    {
      "qa_id": "qa_001",
      "question": "한국의 수도는 어디인가요?",
      "answer": "서울입니다.",
      "context": "대한민국은 동아시아에 위치한 나라로...",
      "ground_truth": "서울",
      "metadata": {
        "source": "geography.pdf",
        "page": 1,
        "created_at": "2026-04-17T00:00:00"
      }
    }
  ]
}
```

---

## 3. 골든 데이터셋 생성 방법

### A. 수동 작성 (JSON)

소규모 데이터셋이나 특정 시나리오를 정밀하게 제어할 때 사용합니다.

```json
{
  "qa_pairs": [
    {
      "qa_id": "manual_001",
      "question": "세금 계산 방법을 설명해주세요.",
      "answer": "",
      "context": "소득세법 제55조에 따르면...",
      "ground_truth": "과세표준에 세율을 곱하고 누진공제액을 뺍니다.",
      "metadata": {
        "category": "tax",
        "difficulty": "medium",
        "created_by": "human",
        "created_at": "2026-04-17T00:00:00"
      },
      "expected_tools": ["tax_calculator", "regulation_search"],
      "expected_workflow_steps": ["retrieve_regulation", "calculate", "format_response"]
    }
  ]
}
```

파일을 `data/golden_datasets/manual_dataset.json`으로 저장합니다.

---

### B. GoldenSetBuilder 자동 추출 (권장)

`@agent_eval` 데코레이터나 `PerformanceMonitor`로 실행한 평가 결과에서 우수한 케이스를 자동으로 추출합니다.

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(
    source_dir="results/",          # 평가 결과 JSON 파일 디렉토리
    output_dir="data/golden_datasets/",
)

candidates = builder.extract(
    strategies=["high_value", "failure_cases"],  # 추출 전략
    max_cases=50,
    require_human_review=True,
)

path = builder.save_candidates(candidates, filename="my_dataset.json")
print(f"저장 완료: {path}")
```

**추출 전략**

| 전략 | 설명 |
|------|------|
| `"high_value"` | accuracy_score >= 0.9 또는 completion_score >= 0.95인 고품질 케이스 |
| `"failure_cases"` | 실패한 케이스 (회귀 방지용) |
| `"edge_cases"` | 점수가 0 또는 1인 극단값 케이스 |
| `"coverage_gap"` | 태스크 유형 분포에서 부족한 유형 우선 추출 |

**CLI로도 동일하게 실행 가능:**

```bash
agent-eval dataset build results/ --min-score 0.8
```

---

### C. KoreanRAGDatasetGenerator (PDF → Golden Dataset)

PDF 문서에서 한국어 RAG 평가용 QA 쌍을 자동 생성합니다. OpenAI API 키가 필요합니다.

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator

generator = KoreanRAGDatasetGenerator(
    model="gpt-4o-mini",        # QA 생성에 사용할 LLM
    chunk_size=800,             # 텍스트 청크 크기 (문자 단위)
    chunk_overlap=150,
    output_dir="golden_datasets"
)

# PDF에서 Golden Dataset 생성
dataset = generator.generate_from_pdf(
    pdf_path="company_policy.pdf",
    num_questions_per_chunk=3,
    question_types=["factual", "reasoning", "summary"],
    save_format="json",         # "json" 또는 "csv"
    max_chunks=None             # None이면 전체, 숫자면 테스트용 샘플링
)

print(f"생성된 QA 쌍: {len(dataset.qa_pairs)}개")
```

**생성 프로세스**:
1. PDF 텍스트 추출 — `KoreanPDFExtractor`로 pypdf/pdfplumber 자동 선택 (pdfplumber 우선)
2. 텍스트 청킹 — `TextChunker`로 의미 단위 분할 (한국어 문장 부호 자동 인식)
3. QA 쌍 생성 — `KoreanQAGenerator`로 OpenAI GPT 기반 질문-답변-ground_truth 생성
4. 검증 및 저장 — `GoldenDatasetManager`로 품질 검증 후 JSON/CSV 저장

**청크 크기 최적화:**

| 문서 유형 | chunk_size | overlap |
|----------|-----------|---------|
| 기술 문서 (코드, API) | 800~1000 | 150~200 |
| 정책/법률 (복잡한 조항) | 1000~1500 | 200~300 |
| 일반 문서 (뉴스, 블로그) | 600~800 | 100~150 |
| FAQ/간단한 정보 | 400~600 | 80~120 |

---

## 4. GoldenSetBuilder API

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(
    source_dir="results/",
    output_dir="data/golden_datasets/",
)

# 1. 후보 케이스 추출
candidates = builder.extract(
    strategies=["high_value", "failure_cases", "edge_cases", "coverage_gap"],
    max_cases=50,
    require_human_review=True,
    min_question_length=10,
)

# 2. 저장
path = builder.save_candidates(candidates, filename="my_dataset.json")

# 3. Phoenix 업로드 (선택)
dataset_id = builder.upload_to_phoenix(
    dataset_path=str(path),
    dataset_name="my-golden-v1",
    phoenix_endpoint="http://localhost:6006",
)
```

### 전체 워크플로우 예시

```python
from agent_evaluator import QuickEval
from agent_evaluator.datasets.builder import GoldenSetBuilder

# 1단계: 평가 결과 생성
eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in production_data:
    my_agent(q, ground_truth=gt)

eval.save()  # results/quickeval.json 생성

# 2단계: 우수 케이스를 골든 데이터셋으로 추출
builder = GoldenSetBuilder(source_dir="results/", output_dir="data/golden_datasets/")
candidates = builder.extract(strategies=["high_value"], max_cases=100)
path = builder.save_candidates(candidates, filename="golden_v1.json")
print(f"골든 데이터셋 저장: {path} ({len(candidates)}개 케이스)")
```

---

## 5. 에이전트 평가 루프

```python
import json
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 골든 데이터셋 로드
with open("data/golden_datasets/golden_v1.json") as f:
    dataset = json.load(f)

# 평가 실행
for pair in dataset.get("qa_pairs", dataset):
    my_agent(pair["question"], ground_truth=pair["ground_truth"])

# 결과 저장 및 품질 게이팅
eval.save()
eval.gate(tcr=85, accuracy=70)  # 기준 미달 시 sys.exit(1)
```

### RAG 에이전트 평가

```python
eval = QuickEval.for_rag("results/")  # hallucination_detection=True 자동 활성

@eval.rag
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return retriever_chain.invoke({"question": question, "context": context})

for pair in dataset.get("qa_pairs", dataset):
    rag_agent(
        pair["question"],
        context=pair.get("context", ""),
        ground_truth=pair["ground_truth"],
    )
```

---

## 6. 한국어 RAG 평가 파이프라인

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

### 설치

```bash
# 한국어 RAG 평가용 의존성
pip install "agent-evaluator[eval]"

# PDF 처리
pip install pdfplumber    # 복잡한 레이아웃 PDF 권장
```

### RAGSystemInterface 구현

평가를 위해 RAG 시스템을 `RAGSystemInterface`에 맞춰 구현합니다. `query()` 메서드만 구현하면 됩니다.

```python
from agent_evaluator.datasets.korean_rag_evaluator import RAGSystemInterface, RAGResponse

class MyRAGSystem(RAGSystemInterface):
    def __init__(self):
        self.vector_db = ...  # Chroma, Pinecone, Qdrant 등
        self.llm = ...

    def query(self, question: str) -> RAGResponse:
        retrieved_docs = self.vector_db.search(question, top_k=3)
        context_text = "\n\n".join(retrieved_docs)
        answer = self.llm.generate(question, context_text)

        return RAGResponse(
            question=question,
            answer=answer,
            retrieved_contexts=retrieved_docs,  # List[str]
            metadata={"num_retrieved": len(retrieved_docs)}
        )
```

### 평가 실행

```python
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator
from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager

manager = GoldenDatasetManager()
dataset = manager.load_dataset("golden_datasets/my_dataset.json")

rag_system = MyRAGSystem()

evaluator = KoreanRAGEvaluator(rag_system=rag_system, use_ragas=True, ragas_model="gpt-5-nano", output_dir="evaluation_results")

report = evaluator.evaluate_dataset(dataset)
```

**평가 결과 예시:**

```
Faithfulness       : 0.892  (목표: >= 0.8)
Answer Relevancy   : 0.856  (목표: >= 0.8)
Context Recall     : 0.834  (목표: >= 0.8)
Context Precision  : 0.878  (목표: >= 0.8)
Answer Similarity  : 0.823  (목표: >= 0.8)
```

---

## 7. RAG 평가 메트릭

### Faithfulness (충실도)

생성된 답변이 검색된 컨텍스트에 얼마나 충실한지 측정합니다 (환각 방지).

- **계산**: 답변에서 주장(claims) 추출 → 각 주장이 컨텍스트에서 뒷받침되는지 검증 → `뒷받침된 주장 수 / 전체 주장 수`
- **목표**: >= 0.8
- **개선**: 프롬프트에 "문서에 없는 내용은 답변하지 말 것" 명시 / temperature 낮춤 (0.1~0.3)

### Answer Relevancy (답변 관련성)

답변이 질문과 얼마나 관련있는지 측정합니다.

- **계산**: 답변에서 역으로 질문들을 생성 → 생성된 질문과 원래 질문의 임베딩 유사도 계산
- **목표**: >= 0.8

### Context Recall (컨텍스트 재현율)

Ground truth를 생성하는 데 필요한 정보가 검색된 컨텍스트에 포함되어 있는지 측정합니다.

- **계산**: Ground truth를 문장들로 분리 → 각 문장이 컨텍스트에서 추론 가능한지 검증
- **목표**: >= 0.8
- **개선**: 검색 top_k 증가 / multilingual 임베딩 모델 / 하이브리드 검색

### Context Precision (컨텍스트 정밀도)

검색된 컨텍스트가 질문에 얼마나 관련 있는지 측정합니다.

- **계산**: 검색된 각 컨텍스트가 Ground truth와 관련 있는지 판단 → Precision@K 평균
- **목표**: >= 0.8
- **개선**: 리랭킹 모델 추가 / 쿼리 확장 / 메타데이터 필터링

### Answer Similarity (답변 유사도)

생성된 답변이 Ground truth와 얼마나 의미적으로 유사한지 측정합니다.

- **계산**: 답변과 Ground truth의 임베딩 코사인 유사도
- **목표**: >= 0.8

### Threshold 권장 설정

| 메트릭 | 일반적 | 엄격함 | 관대함 | 용도 |
|--------|--------|--------|--------|------|
| `faithfulness` | >= 0.8 | >= 0.9 | >= 0.7 | 환각 방지 (가장 중요) |
| `answer_relevancy` | >= 0.85 | >= 0.9 | >= 0.75 | 답변 품질 |
| `context_recall` | >= 0.75 | >= 0.85 | >= 0.65 | 검색 완전성 |
| `context_precision` | >= 0.8 | >= 0.9 | >= 0.7 | 검색 정확도 |

> 의료/금융/법률 시스템: 엄격한 설정 (특히 faithfulness >= 0.9)

---

## 8. 데코레이터 방식 RAG 평가

### QuickEval.for_rag() 사용 (권장)

```python
from agent_evaluator import QuickEval

eval = QuickEval.for_rag("results/")  # hallucination_detection 자동 활성화

@eval.rag  # task_type="information_retrieval" + hallucination detection 자동 적용
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    retrieved = vector_db.search(question, top_k=3)
    context = "\n".join(retrieved)
    return llm.generate(question, context)

for qa in golden_dataset.qa_pairs:
    rag_agent(
        question=qa.question,
        context=qa.context,
        ground_truth=qa.ground_truth
    )

eval.save()
eval.gate(tcr=85, accuracy=70)
```

### PerformanceMonitor.for_rag_evaluation() 사용

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

@agent_eval(monitor, task_type="information_retrieval", rag_mode=True)
def rag_agent(question: str, ground_truth: str = "") -> str:
    retrieved = vector_db.search(question, top_k=3)
    context = "\n".join(retrieved)
    return llm.generate(question, context)
```

### LLMJudge Faithfulness (네이티브, Ragas 불필요)

```python
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,
    llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6"),
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})
# 결과: task.extra["llm_judge"]["faithfulness"] 자동 기록 (Ragas 불필요)
```

---

## 9. KoreanRAGEvaluator 상세

### PerformanceMonitor 통합

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator

monitor = PerformanceMonitor()
monitor.thresholds = {
    "faithfulness": 0.8,
    "answer_relevancy": 0.85,
    "context_recall": 0.75,
    "context_precision": 0.8
}

rag_evaluator = KoreanRAGEvaluator(rag_system=my_rag_system)

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

comparison = monitor.compare_with_thresholds()
failed_metrics = [m for m, d in comparison.items() if d["status"] == "fail"]

if failed_metrics:
    print(f"RAG 품질 게이트 실패: {failed_metrics}")
else:
    print("RAG 품질 게이트 통과!")
```

### 트러블슈팅

| 문제 | 원인 | 해결책 |
|------|------|--------|
| 낮은 Faithfulness (0.5 이하) | 컨텍스트와 답변 불일치 | 프롬프트 개선, top_k 증가 |
| 낮은 Context Recall (0.6 이하) | 검색된 문서가 정답 미포함 | 임베딩 모델 변경, chunk 크기 조정 |
| 느린 평가 속도 | OpenAI API 지연 | `max_samples` 제한, `use_ragas=False` 테스트 |
| PDF 추출 불량 | 스캔된 PDF (이미지) | pdfplumber 설치 또는 OCR 사용 |

---

## 10. 실전 예제: 기업 정책 문서

### 1단계: Golden Dataset 생성

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator

generator = KoreanRAGDatasetGenerator(model="gpt-5-nano", chunk_size=800, chunk_overlap=150)

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
from agent_evaluator.datasets.korean_rag_evaluator import RAGSystemInterface, RAGResponse

class HRPolicyRAG(RAGSystemInterface):
    def __init__(self, pdf_path: str):
        # ... LangChain vectorstore 초기화 ...
        pass

    def query(self, question: str) -> RAGResponse:
        docs = self.vectorstore.similarity_search(question, k=3)
        contexts = [doc.page_content for doc in docs]
        answer = self.llm.predict(f"[문서]\n{chr(10).join(contexts)}\n[질문]\n{question}\n[답변]")
        return RAGResponse(
            question=question, answer=answer,
            retrieved_contexts=contexts, metadata={}
        )
```

### 3단계: QuickEval 데코레이터로 평가

```python
from agent_evaluator import QuickEval
from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager

rag_system = HRPolicyRAG("company_hr_policy.pdf")
eval = QuickEval.for_rag("results/")

@eval.rag
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    response = rag_system.query(question)
    return response.answer

manager = GoldenDatasetManager()
dataset = manager.load_dataset("golden_datasets/hr_policy_dataset.json")

for qa in dataset.qa_pairs:
    rag_agent(question=qa.question, context=qa.context, ground_truth=qa.ground_truth)

eval.save()
eval.gate(tcr=85, accuracy=70)
```

### 4단계: 상세 Ragas 평가

```python
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator

evaluator = KoreanRAGEvaluator(rag_system=rag_system, use_ragas=True, ragas_model="gpt-5-nano")
report = evaluator.evaluate_dataset(dataset)

if report.avg_faithfulness >= 0.8:
    print("RAG 시스템이 정책 문서에 충실합니다")
else:
    print("환각(hallucination) 문제가 있습니다")
```

---

## 11. Phoenix 업로드

```bash
# Phoenix 서버 먼저 기동
agent-eval monitor
```

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(source_dir="results/", output_dir="data/golden_datasets/")
candidates = builder.extract(strategies=["high_value"], max_cases=50)
path = builder.save_candidates(candidates, filename="golden_v1.json")

dataset_id = builder.upload_to_phoenix(
    dataset_path=str(path),
    dataset_name="production-golden-v1",
    phoenix_endpoint="http://localhost:6006",
)

if dataset_id:
    print(f"Phoenix 업로드 완료: {dataset_id}")
    print("Phoenix UI → Datasets 탭에서 확인하세요.")
```

---

## 12. Best Practices

1. **버전 관리** — `data/golden_datasets/*.json`을 Git으로 관리합니다. 팀 전체가 동일한 기준으로 평가할 수 있습니다.

2. **점진적 확장** — 한 번에 대량 생성하기보다 매 배포 사이클마다 `GoldenSetBuilder`로 고품질 케이스를 추가합니다. `max_cases=20~50`으로 작게 시작하세요.

3. **Human Review 필수** — `require_human_review=True`(기본값)로 추출한 케이스는 반드시 사람이 검토 후 확정합니다. 자동 추출된 `ground_truth`는 부정확할 수 있습니다.

4. **전략 다양화** — `["high_value", "failure_cases", "coverage_gap"]`을 함께 사용해 성공/실패/미커버리지 케이스를 균형 있게 포함합니다.

5. **CI/CD 통합** — PR 머지 전 골든 데이터셋으로 자동 평가를 실행하고 `eval.gate()`로 품질 기준을 강제합니다.

   ```yaml
   - name: Golden Dataset Evaluation
     run: |
       python scripts/run_golden_eval.py
       agent-eval gate results/quickeval.json --tcr 85 --accuracy 70
   ```

6. **태스크 유형별 분리** — QA, RAG, Tool Use 등 태스크 유형별로 별도 파일을 유지합니다. 하나의 파일에 혼합하면 집계 지표가 왜곡될 수 있습니다.

7. **Faithfulness 우선** — RAG 시스템에서는 Faithfulness를 가장 중요한 지표로 다룹니다. 환각 문제가 있으면 다른 지표가 높아도 신뢰할 수 없습니다.

---

| 목적 | 문서 |
|------|------|
| 설치 · 기본 사용법 | [01_GETTING_STARTED.md](01_GETTING_STARTED.md) |
| 58개 지표 상세 | [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md) |
| 데코레이터 · 프레임워크 통합 | [03_INTEGRATION_GUIDE.md](03_INTEGRATION_GUIDE.md) |
| 품질 임계값 · CI/CD | [05_QUALITY_GATE.md](05_QUALITY_GATE.md) |
| 전체 API 레퍼런스 | [08_API_REFERENCE.md](08_API_REFERENCE.md) |
I_REFERENCE.md) |
