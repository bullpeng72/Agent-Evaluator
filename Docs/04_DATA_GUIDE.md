# Data Guide

Golden-dataset construction · Korean RAG evaluation · PDF pipeline.

**v1.0.0 | Python 3.8+**

---

## Table of Contents

1. [Overview](#1-overview)
2. [QAPair structure](#2-qapair-structure)
3. [Ways to build a golden dataset](#3-ways-to-build-a-golden-dataset)
4. [GoldenSetBuilder API](#4-goldensetbuilder-api)
5. [Agent evaluation loop](#5-agent-evaluation-loop)
6. [Korean RAG evaluation pipeline](#6-korean-rag-evaluation-pipeline)
7. [RAG evaluation metrics](#7-rag-evaluation-metrics)
8. [Decorator-style RAG evaluation](#8-decorator-style-rag-evaluation)
9. [KoreanRAGEvaluator in detail](#9-koreanragevaluator-in-detail)
10. [Worked example: a corporate policy document](#10-worked-example-a-corporate-policy-document)
11. [Uploading to Phoenix](#11-uploading-to-phoenix)
12. [Best Practices](#12-best-practices)

---

## 1. Overview

A **golden dataset** is a collection of reference QA pairs used to repeatedly verify an agent's accuracy and consistency.

- **Regression prevention** — automatically confirm that existing capability has not degraded before a new deployment
- **CI/CD integration** — hook into `agent-eval gate` to stop the pipeline when the quality bar is missed
- **Incremental growth** — automatically extract high-quality cases from production results to grow the dataset

Default output path: `data/golden_datasets/`

---

## 2. QAPair structure

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `qa_id` | `str` | ✅ | unique identifier (e.g. `"qa_001"`) |
| `question` | `str` | ✅ | the question to send to the agent |
| `answer` | `str` | ✅ | the answer the agent actually produced (or the expected answer) |
| `context` | `str` | ✅ | RAG context or relevant background |
| `ground_truth` | `str` | ✅ | reference answer (used for accuracy measurement) |
| `metadata` | `Dict[str, Any]` | ✅ | ancillary info — source file, creation date, etc. |
| `expected_tools` | `List[str]` | ❌ | Layer 2: expected-tool list for Tool Selection evaluation |
| `expected_agents` | `List[str]` | ❌ | Layer 2: expected agents for Agent Coordination evaluation |
| `expected_workflow_steps` | `List[str]` | ❌ | Layer 2: expected steps for Workflow Execution evaluation |

```json
{
  "qa_pairs": [
    {
      "qa_id": "qa_001",
      "question": "What is the capital of Korea?",
      "answer": "It is Seoul.",
      "context": "The Republic of Korea is a country in East Asia...",
      "ground_truth": "Seoul",
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

## 3. Ways to build a golden dataset

### A. Manual authoring (JSON)

Use this for small datasets or when you need precise control over a specific scenario.

```json
{
  "qa_pairs": [
    {
      "qa_id": "manual_001",
      "question": "Explain how to calculate the tax.",
      "answer": "",
      "context": "Under Article 55 of the Income Tax Act...",
      "ground_truth": "Multiply the tax base by the rate and subtract the progressive deduction.",
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

Save the file as `data/golden_datasets/manual_dataset.json`.

---

### B. GoldenSetBuilder automatic extraction (recommended)

Automatically extracts high-quality cases from evaluation results produced by the `@agent_eval` decorator or `PerformanceMonitor`.

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(
    source_dir="results/",          # directory of evaluation-result JSON files
    output_dir="data/golden_datasets/",
)

candidates = builder.extract(
    strategies=["high_value", "failure_cases"],  # extraction strategies
    max_cases=50,
    require_human_review=True,
)

path = builder.save_candidates(candidates, filename="my_dataset.json")
print(f"saved: {path}")
```

**Extraction strategies**

| Strategy | Description |
|----------|-------------|
| `"high_value"` | high-quality cases with accuracy_score >= 0.9 or completion_score >= 0.95 |
| `"failure_cases"` | failed cases (for regression prevention) |
| `"edge_cases"` | extreme-value cases with a score of 0 or 1 |
| `"coverage_gap"` | prioritizes task types underrepresented in the distribution |

**The same via the CLI:**

```bash
agent-eval dataset build --source results/ --strategy high_value --max-cases 30

# Promote approved cases from the HITL review queue to golden regression cases (SPEC-041 P15)
agent-eval dataset promote result.json --min-priority high

# Golden-set health — does it still exercise the current failure modes + stale / duplicate cases (SPEC-041 P58)
agent-eval dataset health golden.json --against results/latest.json
```

The `uncovered_failure_modes` from `dataset health` is a **blind spot** — a failure mode observed in
production that no case in the golden set reproduces. Adding cases that cover these modes is the priority.

### The closed loop — review queue → golden set → regression gate

`dataset promote` is the middle step of a loop that keeps the golden set aligned with what actually
breaks:

1. A run's report (and `extra_metrics.insights.review_queue`) lists the tasks whose automatic verdict
   is least trustworthy — judge↔heuristic disagreement, borderline scores, a task that regressed.
2. `agent-eval dataset promote result.json --min-priority high` turns the ones you approve into golden
   regression cases (preserving each `task_id`).
3. `agent-eval gate <next_run>.json --golden-set <golden>.json --fail-on-golden-regression` then fails
   CI (exit 3) if any of those approved cases goes missing or starts failing again.
4. `agent-eval dataset health <golden>.json --against <latest>.json` periodically checks the golden set
   still covers the failure modes production is producing.

> `GoldenSetBuilder` only sees `results/` sessions already instrumented with `PerformanceMonitor`. To mine
> cases from ordinary conversations that ran without `@agent_eval` (e.g. a Claude Code session) — an
> optional, core-independent personal tool — see
> [Workflow B in `CTX_SESSION_SEARCH.md`](CTX_SESSION_SEARCH.md#workflow-b--mining-golden-set-raw-material-from-uninstrumented-past-sessions).

---

### C. KoreanRAGDatasetGenerator (PDF → golden dataset)

Automatically generates Korean RAG-evaluation QA pairs from a PDF document. Requires an OpenAI API key.

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator

generator = KoreanRAGDatasetGenerator(
    model="gpt-4o-mini",        # LLM used to generate QA
    chunk_size=800,             # text chunk size (characters)
    chunk_overlap=150,
    output_dir="golden_datasets"
)

# Generate a golden dataset from a PDF
dataset = generator.generate_from_pdf(
    pdf_path="company_policy.pdf",
    num_questions_per_chunk=3,
    question_types=["factual", "reasoning", "summary"],
    save_format="json",         # "json" or "csv"
    max_chunks=None             # None = all; a number = sampling for testing
)

print(f"generated QA pairs: {len(dataset.qa_pairs)}")
```

**Generation process**:
1. PDF text extraction — `KoreanPDFExtractor` auto-selects pypdf/pdfplumber (pdfplumber preferred)
2. Text chunking — `TextChunker` splits into semantic units (auto-recognizes Korean punctuation)
3. QA-pair generation — `KoreanQAGenerator` produces question / answer / ground_truth via OpenAI GPT
4. Validation and save — `GoldenDatasetManager` validates quality and saves as JSON/CSV

**Chunk-size tuning:**

| Document type | chunk_size | overlap |
|---------------|------------|---------|
| technical docs (code, API) | 800–1000 | 150–200 |
| policy / legal (complex clauses) | 1000–1500 | 200–300 |
| general docs (news, blog) | 600–800 | 100–150 |
| FAQ / simple info | 400–600 | 80–120 |

---

## 4. GoldenSetBuilder API

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(
    source_dir="results/",
    output_dir="data/golden_datasets/",
)

# 1. Extract candidate cases
candidates = builder.extract(
    strategies=["high_value", "failure_cases", "edge_cases", "coverage_gap"],
    max_cases=50,
    require_human_review=True,
    min_question_length=10,
)

# 2. Save
path = builder.save_candidates(candidates, filename="my_dataset.json")

# 3. Upload to Phoenix (optional)
dataset_id = builder.upload_to_phoenix(
    dataset_path=str(path),
    dataset_name="my-golden-v1",
    phoenix_endpoint="http://localhost:6006",
)
```

### End-to-end workflow example

```python
from agent_evaluator import QuickEval
from agent_evaluator.datasets.builder import GoldenSetBuilder

# Step 1: produce evaluation results
eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in production_data:
    my_agent(q, ground_truth=gt)

eval.save()  # creates results/quickeval.json

# Step 2: extract high-quality cases into a golden dataset
builder = GoldenSetBuilder(source_dir="results/", output_dir="data/golden_datasets/")
candidates = builder.extract(strategies=["high_value"], max_cases=100)
path = builder.save_candidates(candidates, filename="golden_v1.json")
print(f"golden dataset saved: {path} ({len(candidates)} cases)")
```

---

## 5. Agent evaluation loop

```python
import json
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# Load the golden dataset
with open("data/golden_datasets/golden_v1.json") as f:
    dataset = json.load(f)

# Run the evaluation
for pair in dataset.get("qa_pairs", dataset):
    my_agent(pair["question"], ground_truth=pair["ground_truth"])

# Save results and apply quality gating
eval.save()
eval.gate(tcr=85, accuracy=70)  # sys.exit(1) if the bar is missed
```

### RAG agent evaluation

```python
eval = QuickEval.for_rag("results/")  # hallucination_detection=True is enabled automatically

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

## 6. Korean RAG evaluation pipeline

```
PDF document input
    ↓
KoreanRAGDatasetGenerator (AI-based QA-pair generation)
    ↓
GoldenDataset saved (JSON/CSV)
    ↓
KoreanRAGEvaluator (measures Faithfulness / Context Recall, etc.)
    ↓
Evaluation report generated
```

### Installation

```bash
# dependencies for Korean RAG evaluation
pip install "agent-evaluator[eval]"

# PDF processing
pip install pdfplumber    # recommended for complex-layout PDFs
```

### Implementing RAGSystemInterface

Implement your RAG system against `RAGSystemInterface`. You only need to implement the `query()` method.

```python
from agent_evaluator.datasets.korean_rag_evaluator import RAGSystemInterface, RAGResponse

class MyRAGSystem(RAGSystemInterface):
    def __init__(self):
        self.vector_db = ...  # Chroma, Pinecone, Qdrant, etc.
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

### Running the evaluation

```python
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator
from agent_evaluator.datasets.korean_rag_dataset_generator import GoldenDatasetManager

manager = GoldenDatasetManager()
dataset = manager.load_dataset("golden_datasets/my_dataset.json")

rag_system = MyRAGSystem()

evaluator = KoreanRAGEvaluator(rag_system=rag_system, use_ragas=True, ragas_model="gpt-5-nano", output_dir="evaluation_results")

report = evaluator.evaluate_dataset(dataset)
```

**Example evaluation output:**

```
Faithfulness       : 0.892  (target: >= 0.8)
Answer Relevancy   : 0.856  (target: >= 0.8)
Context Recall     : 0.834  (target: >= 0.8)
Context Precision  : 0.878  (target: >= 0.8)
Answer Similarity  : 0.823  (target: >= 0.8)
```

---

## 7. RAG evaluation metrics

### Faithfulness

Measures how faithful the generated answer is to the retrieved context (hallucination prevention).

- **Computation**: extract claims from the answer → verify each claim is supported by the context → `supported claims / total claims`
- **Target**: >= 0.8
- **Improvement**: state "do not answer anything not in the document" in the prompt / lower the temperature (0.1–0.3)

### Answer Relevancy

Measures how relevant the answer is to the question.

- **Computation**: back-generate questions from the answer → compute embedding similarity between the generated questions and the original question
- **Target**: >= 0.8

### Context Recall

Measures whether the information needed to produce the ground truth is present in the retrieved context.

- **Computation**: split the ground truth into sentences → verify each sentence is inferable from the context
- **Target**: >= 0.8
- **Improvement**: increase retrieval top_k / use a multilingual embedding model / use hybrid retrieval

### Context Precision

Measures how relevant the retrieved context is to the question.

- **Computation**: judge whether each retrieved context is relevant to the ground truth → average Precision@K
- **Target**: >= 0.8
- **Improvement**: add a reranking model / use query expansion / use metadata filtering

### Answer Similarity

Measures how semantically similar the generated answer is to the ground truth.

- **Computation**: cosine similarity between the embeddings of the answer and the ground truth
- **Target**: >= 0.8

### Recommended threshold settings

| Metric | Typical | Strict | Lenient | Purpose |
|--------|---------|--------|---------|---------|
| `faithfulness` | >= 0.8 | >= 0.9 | >= 0.7 | hallucination prevention (most important) |
| `answer_relevancy` | >= 0.85 | >= 0.9 | >= 0.75 | answer quality |
| `context_recall` | >= 0.75 | >= 0.85 | >= 0.65 | retrieval completeness |
| `context_precision` | >= 0.8 | >= 0.9 | >= 0.7 | retrieval accuracy |

> Medical / financial / legal systems: use the strict settings (especially faithfulness >= 0.9).

---

## 8. Decorator-style RAG evaluation

### Using QuickEval.for_rag() (recommended)

```python
from agent_evaluator import QuickEval

eval = QuickEval.for_rag("results/")  # hallucination_detection enabled automatically

@eval.rag  # task_type="information_retrieval" + hallucination detection applied automatically
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

### Using PerformanceMonitor.for_rag_evaluation()

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

### LLMJudge Faithfulness (native, no Ragas needed)

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
# result: task.extra["llm_judge"]["faithfulness"] recorded automatically (no Ragas needed)
```

---

## 9. KoreanRAGEvaluator in detail

### PerformanceMonitor integration

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
    print(f"RAG quality gate failed: {failed_metrics}")
else:
    print("RAG quality gate passed!")
```

### Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Low Faithfulness (≤ 0.5) | context and answer mismatch | improve the prompt, increase top_k |
| Low Context Recall (≤ 0.6) | retrieved documents don't contain the answer | change the embedding model, adjust chunk size |
| Slow evaluation | OpenAI API latency | limit `max_samples`, test with `use_ragas=False` |
| Poor PDF extraction | scanned PDF (image) | install pdfplumber or use OCR |

---

## 10. Worked example: a corporate policy document

### Step 1: generate the golden dataset

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator

generator = KoreanRAGDatasetGenerator(model="gpt-5-nano", chunk_size=800, chunk_overlap=150)

dataset = generator.generate_from_pdf(
    pdf_path="company_hr_policy.pdf",
    num_questions_per_chunk=4,
    question_types=["factual", "reasoning"],
    save_format="json"
)
print(f"done: {dataset.total_qa_pairs} QA pairs")
```

### Step 2: build the RAG system

```python
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from agent_evaluator.datasets.korean_rag_evaluator import RAGSystemInterface, RAGResponse

class HRPolicyRAG(RAGSystemInterface):
    def __init__(self, pdf_path: str):
        # ... initialize the LangChain vectorstore ...
        pass

    def query(self, question: str) -> RAGResponse:
        docs = self.vectorstore.similarity_search(question, k=3)
        contexts = [doc.page_content for doc in docs]
        answer = self.llm.predict(f"[docs]\n{chr(10).join(contexts)}\n[question]\n{question}\n[answer]")
        return RAGResponse(
            question=question, answer=answer,
            retrieved_contexts=contexts, metadata={}
        )
```

### Step 3: evaluate with the QuickEval decorator

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

### Step 4: detailed Ragas evaluation

```python
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator

evaluator = KoreanRAGEvaluator(rag_system=rag_system, use_ragas=True, ragas_model="gpt-5-nano")
report = evaluator.evaluate_dataset(dataset)

if report.avg_faithfulness >= 0.8:
    print("The RAG system is faithful to the policy document")
else:
    print("There is a hallucination problem")
```

---

## 11. Uploading to Phoenix

```bash
# Start the Phoenix server first
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
    print(f"Phoenix upload complete: {dataset_id}")
    print("Check it in the Phoenix UI → Datasets tab.")
```

---

## 12. Best Practices

1. **Version control** — keep `data/golden_datasets/*.json` in Git so the whole team evaluates against the same baseline.

2. **Incremental growth** — rather than generating a large batch at once, add high-quality cases with `GoldenSetBuilder` each deployment cycle. Start small with `max_cases=20–50`.

3. **Human review is mandatory** — cases extracted with `require_human_review=True` (the default) must be reviewed and confirmed by a person. Auto-extracted `ground_truth` can be inaccurate.

4. **Mix strategies** — use `["high_value", "failure_cases", "coverage_gap"]` together to include success / failure / coverage-gap cases in balance.

5. **CI/CD integration** — run an automatic evaluation against the golden dataset before a PR merge and enforce the quality bar with `eval.gate()`. To use the golden dataset itself directly as a CI gate criterion, check with `--golden-set` / `--fail-on-golden-regression` whether approved cases have regressed or gone missing (use the file extracted and approved via `agent-eval dataset build` as is).

   ```yaml
   - name: Golden Dataset Evaluation
     run: |
       python scripts/run_golden_eval.py
       agent-eval gate results/quickeval.json --tcr 85 --accuracy 70

   - name: Golden-Set Regression Gate
     run: |
       agent-eval gate results/quickeval.json \
         --golden-set data/golden_datasets/golden_1.json \
         --fail-on-golden-regression   # exit 3 — fail if an approved case is missing / failing
   ```

6. **Separate by task type** — keep a separate file per task type (QA, RAG, Tool Use, etc.). Mixing them in one file can skew the aggregate metrics.

7. **Faithfulness first** — for a RAG system, treat Faithfulness as the single most important metric. If there is a hallucination problem, high scores on the other metrics cannot be trusted.

---

| Goal | Document |
|------|----------|
| Installation · basic usage | [01_GETTING_STARTED.md](01_GETTING_STARTED.md) |
| All 58 metrics in detail | [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md) |
| Decorators · framework integration | [03_INTEGRATION_GUIDE.md](03_INTEGRATION_GUIDE.md) |
| Quality thresholds · CI/CD | [05_QUALITY_GATE.md](05_QUALITY_GATE.md) |
| Full API reference | [08_API_REFERENCE.md](08_API_REFERENCE.md) |
| ctx session search (optional personal workflow) | [CTX_SESSION_SEARCH.md](CTX_SESSION_SEARCH.md) |
