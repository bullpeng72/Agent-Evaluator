# Chapter 13. 평가 데이터 설계

이 챕터에서 배우는 것: SDK의 핵심 데이터 구조인 `TaskResult`의 24개 필드를 이해하고, 안전하게 생성하는 방법을 익힌다. 10종 `TaskType`별로 자동 활성화되는 지표가 무엇인지 파악하고, 프로덕션 트래픽에서 골든 데이터셋을 자동으로 마이닝하는 전략을 배운다. 마지막으로 개발 환경부터 프로덕션까지 상황별 샘플링 전략과 A/B 테스트 설계 방법을 습득한다.

---

## 13.1 TaskResult — SDK의 핵심 데이터 구조

`TaskResult`는 에이전트 실행 결과를 담는 불변(immutable) 데이터 클래스다. SDK의 모든 평가 데이터는 이 구조를 통해 흐른다.

```python
from agent_evaluator.core.trackers.base import TaskResult
```

`@dataclass(frozen=True)`로 선언되어 생성 후 수정이 불가능하다. 불변 설계의 이유는 두 가지다. 첫째, 여러 트래커가 동시에 같은 `TaskResult`를 읽어도 데이터 오염이 없다. 둘째, 직렬화/역직렬화 시 동일성이 보장된다.

### 24개 필드 목록

**필수 11개 필드** (모두 값을 제공해야 함):

| 필드 | 타입 | 설명 |
|------|------|------|
| `task_id` | `str` | 태스크 고유 식별자 |
| `task_type` | `TaskType` | 태스크 유형 (Enum) |
| `success` | `bool` | 실행 성공 여부 |
| `completion_score` | `float` | 완료 점수 (0.0~1.0) |
| `accuracy_score` | `float` | 정확도 점수 (0.0~1.0) |
| `execution_time` | `float` | 실행 시간 (초) |
| `tokens_used` | `Dict[str, int]` | 토큰 사용량 `{"input": N, "output": M, "total": T}` |
| `tool_calls` | `List` | 사용된 도구 호출 목록 |
| `attempts` | `int` | 시도 횟수 (재시도 포함) |
| `errors` | `List[str]` | 발생한 오류 목록 |
| `timestamp` | `datetime` | 기록 시각 (UTC) |

**선택 13개 필드** (기본값 제공됨):

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `question` | `str` | `""` | 입력 질문 |
| `response` | `str` | `""` | 에이전트 응답 |
| `ground_truth` | `str` | `""` | 정답 기준 |
| `context` | `str` | `""` | RAG 컨텍스트 |
| `expected_tools` | `List[str]` | `[]` | 기대 도구 목록 (Tool Selection F1용) |
| `framework` | `str` | `""` | 사용 프레임워크 |
| `model` | `str` | `""` | 사용 모델명 |
| `cost_usd` | `float` | `0.0` | 비용 (USD) |
| `hallucination_score` | `float` | `0.0` | 환각 점수 (낮을수록 좋음) |
| `quality_score` | `float` | `0.0` | 응답 품질 종합 점수 |
| `latency_percentile` | `Dict` | `{}` | 지연 시간 백분위 |
| `partial_reason` | `str` | `""` | 부분 완료 사유 |
| `extra` | `Dict` | `{}` | 추가 메타데이터 (LLM Judge 점수, chain_steps 등) |

### TaskResult 직접 생성 vs create_taskresult() 비교

```python
from agent_evaluator import TaskResult, TaskType, create_taskresult
from datetime import datetime

# 방법 1: TaskResult 직접 생성 — 11개 필수 필드를 모두 직접 채워야 함
result_manual = TaskResult(
    task_id="task_001",
    task_type=TaskType.QA,
    success=True,
    completion_score=1.0,
    accuracy_score=0.0,        # 직접 계산 필요
    execution_time=1.23,
    tokens_used={"input": 50, "output": 30, "total": 80},
    tool_calls=[],
    attempts=1,
    errors=[],
    timestamp=datetime.utcnow(),
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
)

# 방법 2: create_taskresult() 헬퍼 — 점수 자동 계산 (권장)
result_auto = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=1.23,
    task_type="qa",
    tokens_used={"input": 50, "output": 30, "total": 80},
)
# accuracy_score, completion_score, timestamp 자동 계산
print(f"정확도: {result_auto.accuracy_score:.2f}")  # → 0.95 (4-way 계산)
```

`create_taskresult()`가 자동으로 계산하는 항목:
- `accuracy_score`: TokenOverlapF1(40%) + Jaccard Similarity(30%) + LCS Ratio(20%) + CharSimilarity/Levenshtein(10%)
- `completion_score`: task_type 인식 — `code_generation`/`coding`은 AST 파싱 성공 여부, `tool_use`는 tool_calls 존재 여부, 기타는 길이 기반
- `timestamp`: `datetime.utcnow()` 자동 생성

### 직렬화 / 역직렬화

```python
import json

# 직렬화
d = result_auto.to_dict()           # dict 변환
json_str = json.dumps(d, default=str)

# 역직렬화
result_restored = TaskResult.from_dict(d)   # ISO-8601 timestamp 자동 변환
result_from_json = TaskResult.from_json(json_str)

# TaskResult 수정이 필요할 때 — dataclasses.replace() 사용 (frozen이므로)
import dataclasses
updated = dataclasses.replace(result_auto, framework="openai", model="gpt-4o-mini")
```

---

## 13.2 TaskType 10종 완전 가이드

`TaskType`은 Python Enum으로, 문자열과 혼용 가능하다:

```python
from agent_evaluator import TaskType

# Enum과 문자열 모두 허용
result1 = create_taskresult(task_type=TaskType.QA, ...)
result2 = create_taskresult(task_type="qa", ...)       # 동일하게 동작
```

**각 TaskType별 자동 활성 지표:**

| TaskType | 문자열 값 | 자동 활성 지표 | 특이 동작 |
|---------|----------|-------------|---------|
| `QA` | `"qa"` | Accuracy(4-way), TCR, Quality | Token Overlap F1 기반 정확도 |
| `TOOL_USE` | `"tool_use"` | Tool Call Analyzer, Tool Selection F1, Coordination | `tool_calls` 필드 필수 |
| `INFORMATION_RETRIEVAL` | `"information_retrieval"` | Hallucination (context 있을 때), Accuracy | `rag_mode=True`와 함께 사용 권장 |
| `CODE_GENERATION` | `"code_generation"` | AST 비교 기반 Accuracy, Quality | Python 코드 AST 파싱 → 정규화 비교 |
| `REASONING` | `"reasoning"` | Accuracy, Quality, Multi-step chain | chain_steps 분석 |
| `PLANNING` | `"planning"` | Workflow Execution, Accuracy | 단계별 실행 순서 평가 |
| `DATA_ANALYSIS` | `"data_analysis"` | Accuracy, Quality(5차원) | 수치/통계 응답 처리 |
| `CREATIVE` | `"creative"` | Quality(5차원), TCR | 정확도 대신 품질 중심 |
| `CODING` | `"coding"` | AST 비교 기반 Accuracy | CODE_GENERATION과 동일 동작 |
| `DOCUMENT_CREATION` | `"document_creation"` | Quality, Completeness | 구조/형식 평가 |

> **📋 QA 관리자 연결 포인트**: `task_type`은 개발자가 선택하지만, 그 결과는 QA 대시보드의 **Harness Gate 점수**에 직접 반영됩니다. 아래 표는 어떤 `task_type`이 어느 Gate를 활성화하는지 보여줍니다.

**TaskType → 활성화되는 Harness Gate:**

| TaskType | 주요 기여 Gate | Gate가 회색(비활성)인 경우 |
|---------|-------------|--------------------------|
| `qa` | **Gate A** (목표달성: accuracy·TCR) | `ground_truth` 미제공 시 accuracy 0 |
| `tool_use` | **Gate B** (행동무결성: tool 안전성·루프) + **Gate A** | `tool_calls` 필드 비어있으면 Gate B 데이터 없음 |
| `information_retrieval` | **Gate A** + **Gate C** (신뢰성: hallucination) | `context` 미제공 시 hallucination 지표 미수집 |
| `code_generation` / `coding` | **Gate A** (AST 정확도) + **Gate D** (latency) | AST 파싱 실패 시 길이 기반으로 fallback |
| `reasoning` / `planning` | **Gate A** + **Gate B** (workflow 실행) | `expected_tools` 제공 시 Gate B Tool Selection 활성 |
| `data_analysis` / `document_creation` / `creative` | **Gate A** (quality 5차원) | `ground_truth` 없으면 accuracy 미산정 |

```
개발자가 task_type을 선택  →  해당 Tracker 자동 활성  →  Gate 점수 계산
"tool_use" 선택             →  ToolCallAnalyzer 수집   →  Gate B 점수 생성
"information_retrieval" + context  →  HallucinationDetector  →  Gate C 점수 생성
```

> **실무 팁**: QA 관리자가 "Gate B가 항상 회색이에요"라고 하면, 개발자는 `task_type="tool_use"` 설정 여부와 `tool_calls` 필드 수집 여부를 먼저 확인한다.

```python
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor("results/")

# code_generation — AST 비교 자동 활성
@agent_eval(monitor, task_type="code_generation")
def code_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(f"Python 코드를 작성해주세요: {question}")

# tool_use — expected_tools 제공 시 Tool Selection F1 자동 계산
@agent_eval(monitor, task_type="tool_use", expected_tools_arg="expected_tools")
def tool_agent(
    question: str,
    ground_truth: str = "",
    expected_tools: list = None,
) -> str:
    return agent_executor.invoke({"input": question})

tool_agent(
    "서울 날씨 알려줘",
    ground_truth="맑음",
    expected_tools=["weather_api", "location_service"],
)
```

---

## 13.3 골든 데이터셋 구축 전략

### 골든 데이터셋의 역할

골든 데이터셋은 에이전트의 기준 품질을 정의하는 레퍼런스 QA 쌍 모음이다:

- **회귀 방지**: 신규 배포 전 기존 능력이 저하되지 않았음을 자동으로 검증
- **CI/CD 통합**: `agent-eval gate` 명령어와 연동해 품질 기준 미달 시 파이프라인 중단
- **점진적 확장**: 운영 결과에서 우수한 케이스를 자동으로 추출해 데이터셋 확장

저장 경로: `data/golden_datasets/`

### GoldenSetBuilder — 프로덕션 트래픽 자동 마이닝

가장 권장하는 골든 데이터셋 구축 방법은 실제 운영 트래픽에서 고품질 케이스를 자동으로 추출하는 것이다:

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(
    source_dir="results/",              # 평가 결과 JSON 파일 디렉토리
    output_dir="data/golden_datasets/",
)

# 추출 전략 지정
candidates = builder.extract(
    strategies=["high_value", "failure_cases"],
    max_cases=100,
    require_human_review=True,  # 검토 필요 플래그 설정
    min_question_length=10,     # 너무 짧은 질문 제외
)

print(f"추출된 후보 케이스: {len(candidates)}개")
path = builder.save_candidates(candidates, filename="golden_v1.json")
print(f"저장 완료: {path}")
```

**추출 전략 4종:**

| 전략 | 기준 | 목적 |
|------|------|------|
| `"high_value"` | accuracy_score ≥ 0.85 또는 completion_score ≥ 0.95 | 모범 케이스 확보 |
| `"failure_cases"` | success=False 또는 accuracy_score < 0.3 | 회귀 방지용 엣지 케이스 |
| `"edge_cases"` | 점수가 0 또는 1인 극단값 | 경계 조건 커버리지 |
| `"coverage_gap"` | task_type 분포에서 부족한 유형 우선 | 균형 잡힌 데이터셋 |

### 프로덕션 마이닝 전체 워크플로우

```python
from agent_evaluator import QuickEval
from agent_evaluator.datasets.builder import GoldenSetBuilder

# 1단계: 프로덕션 에이전트 실행 + 평가 결과 누적
eval = QuickEval("results/", auto_save=True, auto_save_interval=50)

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 실제 사용자 트래픽 처리 (예시: 배치 실행)
for q, gt in production_traffic_sample:
    my_agent(q, ground_truth=gt)

eval.save()   # results/quickeval.json 생성

# 2단계: 고품질 케이스 자동 추출
builder = GoldenSetBuilder(
    source_dir="results/",
    output_dir="data/golden_datasets/",
)

candidates = builder.extract(
    strategies=["high_value", "edge_cases"],
    max_cases=200,
)

path = builder.save_candidates(candidates, filename="golden_v2.json")
print(f"골든 데이터셋 저장: {path} ({len(candidates)}개 케이스)")

# 3단계: Phoenix에 업로드 (선택 — agent-eval monitor 실행 중이어야 함)
dataset_id = builder.upload_to_phoenix(
    dataset_path=str(path),
    dataset_name="production-golden-v2",
    phoenix_endpoint="http://localhost:6006",
)
if dataset_id:
    print(f"Phoenix 업로드 완료: {dataset_id}")
```

**CLI로 간단히 실행:**

```bash
# 평가 결과 디렉토리에서 min_score=0.8 이상 케이스 자동 추출
agent-eval dataset build results/ --min-score 0.8
```

---

## 13.4 샘플링 전략 — 언제 전수 평가, 언제 샘플링

모든 요청을 평가하면 비용과 지연이 증가한다. 상황별 적절한 샘플링 전략이 필요하다:

| 환경 | 전략 | sample_rate | 이유 |
|------|------|------------|------|
| 개발 | 전수 평가 | `1.0` | 빠른 피드백, 데이터 수가 적음 |
| CI/CD | 골든셋만 | 해당 없음 (별도 파일) | 100~200개로 충분 |
| 스테이징 | 50% | `0.5` | 절충안 |
| 프로덕션 | 10% | `0.1` | 비용 절감 + 통계적 유의성 유지 |
| 이상 탐지 | 조건부 | `sample_condition` | 오류 발생 케이스만 전수 기록 |

```python
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor("results/")

# 개발 환경 — 전수 기록
@agent_eval(monitor, task_type="qa", sample_rate=1.0)
def dev_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 프로덕션 — 10% 랜덤 샘플링
@agent_eval(monitor, task_type="qa", sample_rate=0.1)
def prod_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 조건부 샘플링 — 특정 조건에서만 기록
@agent_eval(
    monitor,
    task_type="qa",
    # 응답이 짧거나 오류가 의심될 때만 기록
    sample_condition=lambda args, kwargs: (
        len(kwargs.get("ground_truth", "")) > 0  # 정답이 있는 케이스만
    ),
)
def selective_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

> 📋 **QA 관리자 TIP**: 프로덕션에서 `sample_rate=0.1`을 적용하더라도 하루 1만 건의 요청이면 1,000개의 평가 데이터가 쌓인다. 이 정도면 통계적으로 충분한 품질 지표를 계산할 수 있다. 반면 CI 파이프라인에서는 샘플링 없이 골든 데이터셋 전체를 돌린다.

---

## 13.5 A/B 테스트 설계

두 가지 에이전트(모델 버전, 프롬프트 변형 등)를 통계적으로 비교하는 패턴이다.

```python
from agent_evaluator import QuickEval

# 모델 A 평가
eval_a = QuickEval("results/model_a/")

@eval_a.qa
def agent_a(question: str, ground_truth: str = "") -> str:
    return llm_v1.invoke(question)   # 구버전 모델

# 모델 B 평가
eval_b = QuickEval("results/model_b/")

@eval_b.qa
def agent_b(question: str, ground_truth: str = "") -> str:
    return llm_v2.invoke(question)   # 신버전 모델

# 동일 데이터셋으로 양쪽 평가
import json
with open("data/golden_datasets/golden_v1.json") as f:
    golden = json.load(f)

for pair in golden["qa_pairs"]:
    agent_a(pair["question"], ground_truth=pair["ground_truth"])
    agent_b(pair["question"], ground_truth=pair["ground_truth"])

eval_a.save()
eval_b.save()

# 비교
comparison = eval_a.compare(eval_b)
print(f"정확도 차이: {comparison.get('accuracy_delta', 0):+.1%}")
print(f"지연 차이: {comparison.get('latency_delta', 0):+.2f}초")

# 통계적 유의성 검정 (scipy 설치 시 t-검정 자동 실행)
ab_result = eval_a.ab_test(eval_b)
p_value = ab_result.get("p_value", None)
if p_value is not None:
    if p_value < 0.05:
        print(f"통계적으로 유의미한 차이 (p={p_value:.4f})")
    else:
        print(f"통계적으로 유의미하지 않은 차이 (p={p_value:.4f})")
```

---

## 13.6 evaluation_session — 컨텍스트 매니저 패턴

데코레이터 대신 with 블록으로 세션을 관리하고 싶을 때, 또는 세션 종료 시 자동 저장을 원할 때 사용한다:

```python
from agent_evaluator import evaluation_session, create_taskresult

# 동기 세션 — 블록 종료 시 자동 저장 (예외 발생 시에도 안전)
with evaluation_session("eval_output") as monitor:
    for question, answer in test_data:
        result = my_agent(question)  # 직접 에이전트 호출
        task = create_taskresult(
            task_id=f"task_{i}",
            question=question,
            response=result,
            ground_truth=answer,
            execution_time=elapsed,
            task_type="qa",
        )
        monitor.record_task(task)
# 세션 종료 시 eval_output.json + eval_output.html 자동 생성

# 비동기 세션 — async 에이전트 사용 시
import asyncio
from agent_evaluator import async_evaluation_session

async def run_async_eval():
    async with async_evaluation_session("async_eval") as monitor:
        for question, answer in test_data:
            result = await async_agent(question)
            task = create_taskresult(
                task_id=f"async_{i}",
                question=question,
                response=result,
                ground_truth=answer,
                execution_time=elapsed,
                task_type="qa",
            )
            monitor.record_task(task)

asyncio.run(run_async_eval())
```

> 👨‍💻 **개발자 TIP**: `evaluation_session`은 내부적으로 try/finally 패턴을 사용하므로, 에이전트 실행 중 예외가 발생해도 그때까지 수집된 데이터가 안전하게 저장된다. 장시간 실행 배치에서는 `auto_save=True, auto_save_interval=10`을 함께 사용해 중간 결과를 보존하는 것을 권장한다.

---

## 13.7 한국어 평가 특화 전략

한국어 에이전트를 평가할 때는 언어 특성을 고려한 전략이 필요하다.

### 한국어 토큰 특성

한국어는 BPE(Byte Pair Encoding) 분할 특성상 영어보다 토큰 효율이 낮다. 같은 의미의 문장이 영어보다 약 1.5~2배 많은 토큰을 소비한다. "서울"은 약 2~3 토큰, "Seoul"은 1 토큰으로 처리된다.

비용 예측 시 이를 고려해야 한다:

```python
from agent_evaluator import create_taskresult

# 한국어 응답 — 토큰 수 수동 측정 후 주입 (tiktoken 또는 API 응답값 사용)
import tiktoken
enc = tiktoken.encoding_for_model("gpt-4o-mini")

question = "한국의 역사에 대해 설명해주세요."
response = "한국은 5,000년의 역사를 가진 나라로..."
ground_truth = "5천년 역사"

tokens_input = len(enc.encode(question))
tokens_output = len(enc.encode(response))

result = create_taskresult(
    task_id="ko_001",
    question=question,
    response=response,
    ground_truth=ground_truth,
    execution_time=1.5,
    task_type="qa",
    tokens_used={
        "input": tokens_input,
        "output": tokens_output,
        "total": tokens_input + tokens_output,
    },
)
```

### AccuracyEvaluator의 한국어 처리

SDK의 `AccuracyEvaluator`는 4-way 가중치 계산 방식을 사용한다:

| 지표 | 가중치 | 한국어 특성 |
|------|--------|-----------|
| Token Overlap F1 | 40% | 형태소 분할 전 어절 단위 비교 |
| Jaccard Similarity | 30% | 어절 집합 교집합/합집합 |
| LCS Ratio | 20% | 최장 공통 부분 수열 |
| 문자 유사도 | 10% | 자모 단위 문자 비교 |

한국어의 경우 "서울입니다"와 "서울"을 비교할 때 형태소 분석 없이도 문자 유사도(10%)와 LCS(20%)가 높은 유사도를 반환하므로 기본적인 QA 평가는 무리 없이 동작한다.

### 한국어 RAG 데이터셋 자동 구성

PDF 문서에서 한국어 QA 쌍을 자동 생성하는 파이프라인:

```python
from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator
from agent_evaluator import QuickEval

# 1단계: PDF에서 한국어 QA 쌍 자동 생성
generator = KoreanRAGDatasetGenerator(
    model="gpt-4o-mini",          # QA 생성 LLM
    max_questions_per_chunk=3,    # 청크당 최대 3개 질문
    chunk_size=500,               # 500자 청크
    chunk_overlap=100,
)

qa_pairs = generator.generate_from_pdf(
    pdf_path="docs/company_policy_kor.pdf",
    output_path="data/golden_datasets/kor_policy_dataset.json",
)
print(f"생성된 QA 쌍: {len(qa_pairs)}개")

# 2단계: 생성된 데이터셋으로 RAG 에이전트 평가
eval = QuickEval.for_rag("results/")

@eval.rag
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    docs = retriever.invoke(question)
    context_text = "\n".join([d.page_content for d in docs[:3]])
    return llm.invoke(f"다음 내용을 참고하여 답해주세요:\n{context_text}\n\n질문: {question}")

import json
with open("data/golden_datasets/kor_policy_dataset.json") as f:
    dataset = json.load(f)

for pair in dataset.get("qa_pairs", []):
    rag_agent(
        pair["question"],
        context=pair.get("context", ""),
        ground_truth=pair["ground_truth"],
    )

eval.save()
eval.gate(tcr=80, accuracy=65)
```

### KorQuAD 기반 평가 설계

공개 한국어 QA 데이터셋 KorQuAD를 활용한 벤치마킹 패턴:

```python
from agent_evaluator import QuickEval
import json

# KorQuAD 형식 데이터 로드 (SQuAD 호환 JSON)
with open("data/korquad_v1_dev.json") as f:
    korquad = json.load(f)

eval = QuickEval("results/korquad_bench/")

@eval.qa
def korean_qa_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(f"다음 질문에 한국어로 답해주세요: {question}")

# KorQuAD 구조 파싱
count = 0
for article in korquad["data"][:10]:  # 처음 10개 문서만
    for paragraph in article["paragraphs"]:
        for qa in paragraph["qas"]:
            if count >= 100:  # 최대 100개
                break
            korean_qa_agent(
                qa["question"],
                ground_truth=qa["answers"][0]["text"] if qa["answers"] else "",
            )
            count += 1

eval.save()
summary = eval.summary()
print(f"KorQuAD 정확도: {summary.get('accuracy', 0):.1%}")
print(f"평균 지연: {summary.get('avg_latency', 0):.2f}초")
```

---

## 13.8 에이전트 유형별 최소 Tracker + Config 세트

에이전트를 처음 평가할 때 "모든 지표를 다 켜야 하는가?"라는 질문이 자주 나온다.  
답은 **아니다**. 에이전트 유형별로 **최소한으로 필요한 Tracker + Harness Config 조합**이 있다.  
이 최소 세트로 시작하고, 운영 경험이 쌓이면 점진적으로 확장한다.

┌─────────────────────────────────────────────────────┐
│ 🔗 Harness 연결                                      │
│ 이 절은 모든 Group에 걸쳐 있습니다.                    │
│ 에이전트 유형이 "어떤 Group을 우선 활성화할지"를 결정.  │
│ Gate 판정: HarnessEvaluationGate(group_configs={...}) │
└─────────────────────────────────────────────────────┘

### 에이전트 유형별 최소 세트 표

| 에이전트 유형 | 필수 Group | 필수 Tracker | 최소 Config 세트 | 선택 확장 |
|------------|-----------|-------------|-----------------|----------|
| **단순 QA** | A, C | TaskCompletionTracker, AccuracyEvaluator | `InstructionConfig`, `ReproducibilityConfig` | Group D (SLA) |
| **RAG** | A, C, E | + HallucinationDetector | + `ThreatSeverityConfig`, `IdempotencyConfig` | Group G (LLM Judge) |
| **코드 생성** | A, B, E | + ToolCallAnalyzer | `ScopeConfig`, `ComplianceConfig`, `InstructionConfig` | Group C (신뢰성) |
| **도구 사용** | A, B, D | + ToolSelectionTracker, LatencyTracker | `SLAConfig`, `LoopDetectionConfig`, `SubtaskConfig` | Group F (멀티에이전트) |
| **멀티에이전트** | A, B, F, G | + AgentCoordinationTracker | `DeadlockConfig`, `AgentRoleConfig`, `ObservabilityConfig` | Group C, E 전체 |
| **보안 민감** | A, E (전부) | + InputSanitizationTracker, OutputLeakageDetector | `ThreatSeverityConfig`, `ComplianceConfig`, `ThreatResponseConfig` | Group B ToolParameterSafety |
| **장기 대화** | A, C, F | + ConversationSession | `ContextRetentionConfig`, `FaultToleranceConfig` | Group D TTFT |

### 코드로 최소 세트 적용

```python
from agent_evaluator import PerformanceMonitor, agent_eval, TaskResult

# ── 단순 QA 에이전트 최소 세트 ──────────────────────────────────────
from agent_evaluator.core.trackers.base import (
    InstructionConfig, ReproducibilityConfig
)

monitor = PerformanceMonitor(
    output_dir="results/",
    harness_configs={
        "instruction": InstructionConfig(min_completion_rate=0.85),
        "reproducibility": ReproducibilityConfig(min_consistency_score=0.80),
    }
)

@agent_eval(monitor, task_type="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)


# ── RAG 에이전트 최소 세트 ───────────────────────────────────────────
from agent_evaluator.core.trackers.base import (
    ThreatSeverityConfig, IdempotencyConfig
)

monitor_rag = PerformanceMonitor.for_rag_evaluation(
    output_dir="results/",
    harness_configs={
        "threat": ThreatSeverityConfig(max_severity_level="medium", fail_on_violation=True),
        "idempotency": IdempotencyConfig(min_idempotency_score=0.75),
    }
)

@agent_eval(monitor_rag, task_type="information_retrieval")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return llm.invoke(f"컨텍스트: {context}\n질문: {question}")


# ── 멀티에이전트 최소 세트 ──────────────────────────────────────────
from agent_evaluator.core.trackers.base import (
    DeadlockConfig, AgentRoleConfig, ObservabilityConfig
)

monitor_multi = PerformanceMonitor(
    output_dir="results/",
    harness_configs={
        "deadlock": DeadlockConfig(max_wait_cycles=3, fail_on_violation=True),
        "roles": AgentRoleConfig(
            allowed_roles=["researcher", "writer", "reviewer"],
            require_role_declaration=True,
        ),
        "observability": ObservabilityConfig(
            require_trace_id=True,
            min_span_coverage=0.90,
        ),
    }
)
```

### TaskType과 Group 자동 활성화 관계

`create_taskresult(task_type=...)` 호출 시 아래 Group의 Tracker가 자동으로 활성화된다:

| TaskType | 자동 활성 Group | 수동 활성 필요 Group |
|---------|--------------|-------------------|
| `"qa"` | A (TCR·Accuracy·Quality) | C (Reproducibility), D (Latency) |
| `"tool_use"` | A, B (ToolCall·ToolSelection) | D (SLA), F (Coordination) |
| `"information_retrieval"` | A, E (Hallucination·context 있을 때) | G (LLMJudge faithfulness) |
| `"code_generation"` / `"coding"` | A (AST 비교), B (Scope) | E (Compliance) |
| `"reasoning"` / `"planning"` | A, B (Workflow) | C (Retry), F (멀티스텝) |

### 점진적 확장 로드맵

```
Week 1 — 최소 세트로 시작
  PerformanceMonitor + 2개 Config + @agent_eval
  → TCR, Accuracy, Harness Gate 기본 판정 확인

Week 2~4 — 운영 데이터 분석 후 확장
  지속 낮은 지표 → 해당 Group Config 추가
  (예: P95 지연 높음 → Group D SLAConfig 추가)

Month 2 — HarnessEvaluationGate 종합 판정 도입
  모든 필요 Group Config → HarnessEvaluationGate에 통합
  CI/CD pipeline에 gate() 연결

Month 3+ — 전체 Group 커버리지 달성
  agent-eval trend로 회귀 모니터링
  GoldenSetBuilder로 데이터셋 자동 확장
```

---

## 이 챕터의 핵심

- **`TaskResult`는 불변(frozen=True) 데이터 클래스**다. 24개 필드 중 11개는 필수이며, `create_taskresult()` 헬퍼를 사용하면 accuracy_score와 timestamp를 자동 계산해준다.
- **`TaskType`은 평가 전략을 결정**한다. `"code_generation"`은 AST 비교를, `"tool_use"`는 Tool Selection F1을, `"information_retrieval"`은 Hallucination 탐지를 자동 활성화한다.
- **골든 데이터셋은 `GoldenSetBuilder`로 자동 마이닝**한다. 프로덕션 트래픽에서 `accuracy_score >= 0.85` 케이스를 추출하고, `push_to_phoenix()`로 Phoenix UI와 연동하면 시각적으로 관리할 수 있다.
- **샘플링 전략은 환경별로 달라진다**: 개발(1.0) → CI(골든셋 전수) → 프로덕션(0.1). `sample_condition`으로 오류 케이스만 전수 기록하는 조건부 샘플링도 가능하다.
- **한국어 평가는 토큰 비용이 1.5~2배** 높다는 점을 고려해 비용 예측을 조정해야 하며, `KoreanRAGDatasetGenerator`로 PDF에서 한국어 QA 쌍을 자동 생성하고 `QuickEval.for_rag()`로 바로 평가할 수 있다.

---

## 실전 예제

평가 데이터 설계와 골든 데이터셋 운영은 두 예제 파일에서 실제로 확인할 수 있다. `01_layer1_all_metrics.py`는 `create_taskresult()` 헬퍼와 TaskType 활용법을, `06_operational.py`는 `GoldenSetBuilder`를 통한 프로덕션 데이터 마이닝을 보여준다.

**파일**: `Evaluator_Examples/01_layer1_all_metrics.py`, `Evaluator_Examples/06_operational.py`

**핵심 코드**

**`create_taskresult()` 헬퍼 vs 직접 생성 비교 (출처: `01_layer1_all_metrics.py`, 섹션 1)**

```python
# 출처: Evaluator_Examples/01_layer1_all_metrics.py, 섹션 1
from agent_evaluator import create_taskresult, TaskResult
from datetime import datetime

# ✅ 권장: create_taskresult() 헬퍼 — accuracy_score, completion_score, timestamp 자동 계산
result = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=1.23,
    task_type="qa",
    tokens_used={"input": 80, "output": 20, "total": 100},
)
print(f"accuracy_score={result.accuracy_score:.2f}")    # 자동 계산
print(f"completion_score={result.completion_score:.2f}") # 자동 계산

# ❌ 비권장: TaskResult 직접 생성 — 11개 필수 필드를 모두 직접 채워야 함
direct = TaskResult(
    task_id="task_002",
    task_type="qa",
    success=True,
    completion_score=0.9,        # 직접 계산
    accuracy_score=0.87,         # 직접 계산
    execution_time=1.23,
    tokens_used={"input": 80, "output": 20, "total": 100},
    tool_calls=[],
    attempts=1,
    errors=[],
    timestamp=datetime.now(),
    # 선택 필드 13개는 기본값으로 채워짐
)
```

- `create_taskresult()`는 `question`, `response`, `ground_truth`에서 TokenF1·Jaccard·LCS·Char Levenshtein 가중 합산으로 accuracy_score를 자동 계산한다
- `TaskResult`는 `@dataclass(frozen=True)` — 생성 후 불변(immutable)이다. `to_dict()` / `from_dict()` / `from_json()`으로 직렬화·역직렬화를 지원한다
- `context` 필드에 검색된 문서를 넣으면 HallucinationDetector가 자동으로 활성화된다 (`task_type="information_retrieval"`일 때)

**GoldenSetBuilder — 자동 마이닝 (출처: `06_operational.py`, 섹션 3)**

```python
# 출처: Evaluator_Examples/06_operational.py, 섹션 3
from agent_evaluator.datasets.builder import GoldenSetBuilder
from datetime import datetime

builder = GoldenSetBuilder(
    source_dir="results/",           # 평가 결과 JSON이 저장된 디렉토리
    output_dir="data/golden_datasets/",  # 골든 데이터 저장 위치
)

# 고가치 QA 케이스 추출 (accuracy_score >= 0.7)
def _to_golden_dict(r, strategy: str = "high_value") -> dict:
    return {
        "task_id":        r.task_id,
        "question":       getattr(r, "question", r.task_id) or r.task_id,
        "response":       getattr(r, "response", "") or "",
        "ground_truth":   getattr(r, "ground_truth", "") or "",
        "accuracy_score": r.accuracy_score,
        "task_type":      str(r.task_type),
        "_requires_review": True,    # 대시보드 케이스 검토 탭에서 검토 대기 상태
        "_strategy":      strategy,
        "_extracted_at":  datetime.now().isoformat(),
    }

# 정확도 기준으로 케이스 분류
high_value = [_to_golden_dict(r, "high_value")    for r in tasks if r.accuracy_score >= 0.7]
fail_cases = [_to_golden_dict(r, "failure_cases") for r in tasks if r.accuracy_score < 0.2]
edge_cases = [_to_golden_dict(r, "edge_cases")    for r in tasks if r.execution_time > 8.0]

# 후보 파일 저장 → 대시보드 '케이스 검토' 탭에서 승인/거부 가능
builder.save_candidates(high_value, filename="qa_candidates.json")

# 승인된 케이스를 마스터 골든셋으로 병합
builder.merge_to_golden(high_value, version="v1", output_name="master_golden")
```

- `_requires_review=True`가 포함된 JSON을 `data/golden_datasets/` 디렉토리에 저장하면 대시보드 '케이스 검토' 탭에 검토 대기 항목으로 표시된다
- `save_candidates()`는 후보 파일을, `merge_to_golden()`은 최종 골든셋 파일을 생성한다. 버전(`version="v1"`)으로 이력을 관리한다
- 실패 케이스(`failure_cases`)와 엣지 케이스(`edge_cases`)를 포함해야 회귀 테스트 커버리지가 높아진다

```bash
python Evaluator_Examples/01_layer1_all_metrics.py
python Evaluator_Examples/06_operational.py
```

**예제 구성**

| 파일 | 섹션 | 내용 | 연관 기능 |
|------|------|------|-----------|
| 01_layer1 | 섹션 1~2 | `create_taskresult()` 헬퍼 사용법 | `task_type`, `accuracy_score` 자동 계산 |
| 01_layer1 | 섹션 3 | `TaskType.CODE_GENERATION` 평가 | AST 비교 자동 활성화 |
| 01_layer1 | 섹션 5 | `information_retrieval` 태스크 | `HallucinationDetector` 자동 연동 |
| 06_operational | 섹션 5 | `GoldenSetBuilder` 마이닝 | `accuracy_score >= 0.85` 케이스 자동 추출 |
| 06_operational | 섹션 5 | `push_to_phoenix()` | Phoenix Datasets 탭에 골든셋 업로드 |

**실행 결과 (v0.8.2 기준)**

```
# 01_layer1_all_metrics.py
총 54개 태스크 | TCR=43.1% | 평균 정확도=59.82%
  code_generation 태스크: AST 비교 적용, accuracy=0.756
  information_retrieval: HallucinationDetector 활성화

# 06_operational.py (GoldenSetBuilder 섹션)
GoldenSetBuilder: 28개 결과 중 12개 골든 케이스 추출
  기준: accuracy_score >= 0.85 AND completion_score >= 0.9
  저장: data/golden_datasets/golden_YYYYMMDD_HHMMSS.json
  Phoenix push: 비활성 (API 키 없음) — ANTHROPIC_API_KEY 설정 시 자동 업로드
```

> **핵심**: `create_taskresult()`는 `question`과 `response`, `ground_truth`만 넣으면 TokenF1·Jaccard·LCS 가중 합산으로 `accuracy_score`를 자동 계산한다. 직접 `TaskResult()`를 생성할 때는 11개 필수 필드를 모두 채워야 하므로 헬퍼 사용을 강력히 권장한다.
