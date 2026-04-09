# Chapter 8. 평가 데이터 설계

이 챕터에서 배우는 것: SDK의 핵심 데이터 구조인 `TaskResult`의 24개 필드를 이해하고, 안전하게 생성하는 방법을 익힌다. 10종 `TaskType`별로 자동 활성화되는 지표가 무엇인지 파악하고, 프로덕션 트래픽에서 골든 데이터셋을 자동으로 마이닝하는 전략을 배운다. 마지막으로 개발 환경부터 프로덕션까지 상황별 샘플링 전략과 A/B 테스트 설계 방법을 습득한다.

---

## 8.1 TaskResult — SDK의 핵심 데이터 구조

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
- `accuracy_score`: Token Overlap(40%) + Jaccard Similarity(30%) + LCS Ratio(20%) + 문자 유사도(10%)
- `completion_score`: success 여부 기반
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

## 8.2 TaskType 10종 완전 가이드

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

## 8.3 골든 데이터셋 구축 전략

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

## 8.4 샘플링 전략 — 언제 전수 평가, 언제 샘플링

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

## 8.5 A/B 테스트 설계

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

## 8.6 evaluation_session — 컨텍스트 매니저 패턴

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

## 8.7 한국어 평가 특화 전략

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

## 이 챕터의 핵심

- **`TaskResult`는 불변(frozen=True) 데이터 클래스**다. 24개 필드 중 11개는 필수이며, `create_taskresult()` 헬퍼를 사용하면 accuracy_score와 timestamp를 자동 계산해준다.
- **`TaskType`은 평가 전략을 결정**한다. `"code_generation"`은 AST 비교를, `"tool_use"`는 Tool Selection F1을, `"information_retrieval"`은 Hallucination 탐지를 자동 활성화한다.
- **골든 데이터셋은 `GoldenSetBuilder`로 자동 마이닝**한다. 프로덕션 트래픽에서 `accuracy_score >= 0.85` 케이스를 추출하고, `push_to_phoenix()`로 Phoenix UI와 연동하면 시각적으로 관리할 수 있다.
- **샘플링 전략은 환경별로 달라진다**: 개발(1.0) → CI(골든셋 전수) → 프로덕션(0.1). `sample_condition`으로 오류 케이스만 전수 기록하는 조건부 샘플링도 가능하다.
- **한국어 평가는 토큰 비용이 1.5~2배** 높다는 점을 고려해 비용 예측을 조정해야 하며, `KoreanRAGDatasetGenerator`로 PDF에서 한국어 QA 쌍을 자동 생성하고 `QuickEval.for_rag()`로 바로 평가할 수 있다.
