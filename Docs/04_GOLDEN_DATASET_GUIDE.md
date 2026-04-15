# Golden Dataset 가이드

Agent Evaluator v0.8.1 | 테스트 데이터셋 생성 및 관리

---

## 목차

1. [개요](#1-개요)
2. [QAPair 구조](#2-qapair-구조)
3. [생성 방법 3가지](#3-생성-방법-3가지)
4. [GoldenSetBuilder API](#4-goldensetbuilder-api)
5. [에이전트 평가 루프](#5-에이전트-평가-루프)
6. [Phoenix 업로드](#6-phoenix-업로드)
7. [저장 경로](#7-저장-경로)
8. [Best Practices](#8-best-practices)

---

## 1. 개요

**Golden Dataset**은 에이전트의 정확도와 일관성을 반복적으로 검증하기 위한 레퍼런스 QA 쌍 모음이다.

- **회귀 방지** — 신규 배포 전 기존 능력이 저하되지 않았음을 자동으로 확인한다.
- **CI/CD 통합** — `agent-eval gate` 명령어와 연동해 품질 기준 미달 시 파이프라인을 중단한다.
- **점진적 확장** — 운영 결과에서 우수한 케이스를 자동으로 추출해 데이터셋을 확장한다.

저장 기본 경로: `data/golden_datasets/`

---

## 2. QAPair 구조

`QAPair`는 `agent_evaluator/datasets/korean_rag_dataset_generator.py`에 정의된 dataclass다.

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `qa_id` | `str` | ✅ | 고유 식별자 (예: `"qa_001"`) |
| `question` | `str` | ✅ | 에이전트에게 전달할 질문 |
| `answer` | `str` | ✅ | 에이전트가 실제로 생성한 답변 (또는 기대 답변) |
| `context` | `str` | ✅ | RAG 컨텍스트 또는 관련 배경 정보 |
| `ground_truth` | `str` | ✅ | 정답 기준 (정확도 측정에 사용) |
| `metadata` | `Dict[str, Any]` | ✅ | 소스 파일, 생성 날짜 등 부가 정보 |
| `expected_tools` | `List[str]` | ❌ | Layer 2: Tool Selection 평가용 기대 도구 목록 |
| `expected_agents` | `List[str]` | ❌ | Layer 2: Agent Coordination 평가용 기대 에이전트 목록 |
| `expected_workflow_steps` | `List[str]` | ❌ | Layer 2: Workflow Execution 평가용 기대 단계 |

### JSON 표현 예시

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
        "created_at": "2026-04-07T00:00:00"
      },
      "expected_tools": null,
      "expected_agents": null,
      "expected_workflow_steps": null
    }
  ]
}
```

---

## 3. 생성 방법 3가지

### A. 수동 작성 (JSON)

소규모 데이터셋이나 특정 시나리오를 정밀하게 제어해야 할 때 사용한다.

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
        "created_at": "2026-04-07T00:00:00"
      },
      "expected_tools": ["tax_calculator", "regulation_search"],
      "expected_agents": null,
      "expected_workflow_steps": ["retrieve_regulation", "calculate", "format_response"]
    }
  ]
}
```

파일을 `data/golden_datasets/manual_dataset.json`으로 저장한다.

---

### B. GoldenSetBuilder 자동 추출 (from eval results)

`@agent_eval` 데코레이터나 `PerformanceMonitor`로 실행한 평가 결과에서 우수한 케이스를 자동으로 추출한다. 가장 권장하는 방법이다.

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

**추출 전략 (strategies)**

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

PDF 문서에서 한국어 RAG 평가용 QA 쌍을 자동 생성한다. OpenAI API 키가 필요하다.

```bash
# PDF 처리 및 LLM 기능은 기본 설치에 포함
pip install agent-evaluator
```

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator

generator = KoreanRAGDatasetGenerator(
    model="gpt-4o-mini",        # QA 생성에 사용할 LLM
    max_questions_per_chunk=3,  # 청크당 최대 질문 수
    chunk_size=500,             # 텍스트 청크 크기 (문자 단위)
)

# PDF에서 QA 쌍 생성
qa_pairs = generator.generate_from_pdf(
    pdf_path="docs/company_policy.pdf",
    output_path="data/golden_datasets/policy_dataset.json",
)

print(f"생성된 QA 쌍: {len(qa_pairs)}개")
```

생성된 파일은 동일한 `QAPair` 구조로 저장되어 평가 루프에 바로 사용할 수 있다.

**필요 패키지:** `pdfplumber` (PDF 파싱), `openai` (QA 생성)

---

## 4. GoldenSetBuilder API

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder
```

### 생성자

```python
builder = GoldenSetBuilder(
    source_dir="results/",           # 평가 결과 JSON 디렉토리
    output_dir="data/golden_datasets/",  # 출력 디렉토리
)
```

### 주요 메서드

```python
# 1. 후보 케이스 추출
candidates = builder.extract(
    strategies=["high_value", "failure_cases", "edge_cases", "coverage_gap"],
    max_cases=50,               # 최대 케이스 수 (기본: 50)
    require_human_review=True,  # 검토 필요 플래그 설정 (기본: True)
    min_question_length=10,     # 질문 최소 길이 필터 (기본: 10)
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

# 1단계: 에이전트를 실행해 평가 결과 생성
eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 운영 데이터로 평가 실행 (결과가 results/에 저장됨)
for q, gt in production_data:
    my_agent(q, ground_truth=gt)

eval.save()  # results/quickeval.json 생성

# 2단계: 우수 케이스를 골든 데이터셋으로 추출
builder = GoldenSetBuilder(
    source_dir="results/",
    output_dir="data/golden_datasets/",
)

candidates = builder.extract(
    strategies=["high_value"],
    max_cases=100,
)

path = builder.save_candidates(candidates, filename="golden_v1.json")
print(f"골든 데이터셋 저장: {path} ({len(candidates)}개 케이스)")
```

---

## 5. 에이전트 평가 루프

골든 데이터셋을 로드해 에이전트를 반복 평가하고, CI/CD 게이팅을 적용하는 패턴이다.

```python
import json
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    # 실제 에이전트 로직
    return llm.invoke(question)

# 골든 데이터셋 로드
with open("data/golden_datasets/golden_v1.json") as f:
    dataset = json.load(f)

# 평가 실행
qa_pairs = dataset.get("qa_pairs", dataset)  # list 또는 {"qa_pairs": [...]} 모두 지원
for pair in qa_pairs:
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

with open("data/golden_datasets/rag_golden.json") as f:
    dataset = json.load(f)

for pair in dataset.get("qa_pairs", dataset):
    rag_agent(
        pair["question"],
        context=pair.get("context", ""),
        ground_truth=pair["ground_truth"],
    )

eval.save()
eval.gate(tcr=80, accuracy=65)
```

### Tool Use 에이전트 평가

```python
@eval.tool_use
def tool_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})

# expected_tools 필드가 있는 경우 Tool Selection F1 자동 측정
for pair in dataset.get("qa_pairs", dataset):
    tool_agent(pair["question"], ground_truth=pair["ground_truth"])
```

---

## 6. Phoenix 업로드

Arize Phoenix의 Datasets & Experiments 탭에서 골든 데이터셋을 시각화하고 관리할 수 있다.

```bash
# Phoenix 서버 먼저 기동
agent-eval monitor
```

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(
    source_dir="results/",
    output_dir="data/golden_datasets/",
)

candidates = builder.extract(strategies=["high_value"], max_cases=50)
path = builder.save_candidates(candidates, filename="golden_v1.json")

# Phoenix 업로드
dataset_id = builder.upload_to_phoenix(
    dataset_path=str(path),
    dataset_name="production-golden-v1",   # Phoenix UI에 표시될 이름
    phoenix_endpoint="http://localhost:6006",
)

if dataset_id:
    print(f"Phoenix 업로드 완료: dataset_id={dataset_id}")
    print("Phoenix UI → Datasets 탭에서 확인하세요.")
else:
    print("업로드 실패 — Phoenix 서버가 실행 중인지 확인하세요.")
```

**필요 패키지:**

```bash
# OTEL 및 Phoenix 기능은 기본 설치에 포함
pip install agent-evaluator
```

---

## 7. 저장 경로

| 경로 | 설명 |
|------|------|
| `data/golden_datasets/` | 골든 데이터셋 기본 저장 경로 |
| `results/` | 평가 결과 JSON 저장 경로 (GoldenSetBuilder의 source_dir) |
| `data/golden_datasets/candidates.json` | `save_candidates()` 기본 파일명 |

`data/golden_datasets/` 디렉토리는 `save_candidates()` 호출 시 자동 생성된다.

**파일 구조:**

```
data/
└── golden_datasets/
    ├── golden_v1.json        # 버전별 골든 데이터셋
    ├── rag_golden.json       # RAG 전용 데이터셋
    └── candidates.json       # 검토 대기 후보 케이스
```

---

## 8. Best Practices

1. **버전 관리** — 골든 데이터셋 파일을 Git으로 관리한다. `data/golden_datasets/*.json`을 저장소에 커밋하면 팀 전체가 동일한 기준으로 평가할 수 있다.

2. **점진적 확장** — 한 번에 대량 생성하기보다 매 배포 사이클마다 `GoldenSetBuilder`로 고품질 케이스를 추가한다. `max_cases=20~50`으로 작게 시작하는 것을 권장한다.

3. **human review 필수** — `require_human_review=True`(기본값)로 추출한 케이스는 반드시 사람이 검토 후 확정한다. 자동 추출된 `ground_truth`는 부정확할 수 있다.

4. **전략 다양화** — `["high_value", "failure_cases", "coverage_gap"]`을 함께 사용해 성공/실패/미커버리지 케이스를 균형 있게 포함한다.

5. **CI/CD 통합** — PR 머지 전 골든 데이터셋으로 자동 평가를 실행하고 `eval.gate()`로 품질 기준을 강제한다.

   ```yaml
   # .github/workflows/eval.yml
   - name: Golden Dataset Evaluation
     run: |
       python scripts/run_golden_eval.py
       agent-eval gate results/quickeval.json --tcr 85 --accuracy 70
   ```

6. **태스크 유형별 분리** — QA, RAG, Tool Use 등 태스크 유형별로 별도 파일을 유지한다. 하나의 파일에 혼합하면 집계 지표가 왜곡될 수 있다.
