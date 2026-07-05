# Appendix E. 에러 코드 & 트러블슈팅

Agent Evaluator 사용 중 자주 발생하는 오류 23가지와 FAQ 10가지를 정리한다.

> **Harness Engineering 관점**: 평가 중 발생하는 오류는 단순한 버그가 아니다. Gate A–G 중 어느 게이트에서 신호가 차단되는지를 먼저 파악하면 원인을 빠르게 좁힐 수 있다. **Gate 오류 = 배포 기준 미달 신호**다 — 오류를 고치는 동시에 해당 Gate가 왜 실패했는지 원인을 분석하자.

---

## 자주 발생하는 오류 23가지

---

### 1. Phoenix 스팬이 Tracing 탭에 안 보임

**증상**: `agent-eval monitor`로 Phoenix를 기동했는데 코드 실행 후에도 Tracing 탭이 비어있다.

**원인 A**: `setup_otel()`이 `PerformanceMonitor` 생성 이후에 호출됨

```python
# 잘못된 순서
monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)
setup_otel(endpoint="http://localhost:6006")  # 이미 늦음

# 올바른 순서
setup_otel(endpoint="http://localhost:6006")  # 먼저 호출
monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)
```

**원인 B**: endpoint URL에 `/v1/traces` 경로가 포함됨

```python
# 잘못됨
setup_otel(endpoint="http://localhost:6006/v1/traces")

# 올바름
setup_otel(endpoint="http://localhost:6006")
```

**원인 C**: `agent-eval monitor`가 실행되지 않음. 별도 터미널에서 먼저 기동할 것.

```bash
# 터미널 1
agent-eval monitor          # Phoenix 기본 포트: 6006, OTEL gRPC 수신: 4317

# 터미널 2
python my_agent.py
```

> **팁**: `agent-eval monitor --check`로 OTEL 패키지 설치 여부, 포트 4317(gRPC) 및 포트 6006 점유 상태를 한 번에 확인할 수 있다.

---

### 2. agent-eval dashboard에 데이터가 없음

**증상**: 대시보드를 열었는데 모든 탭이 빈 상태.

**원인 A**: `save_to_file()`을 한 번도 호출하지 않음

```python
monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)
# ... 평가 실행 후
monitor.save_to_file("evaluation")  # 반드시 호출
```

**원인 B**: 대시보드 실행 디렉토리와 결과 파일 경로 불일치

```bash
# results/ 안에 파일이 있어야 함
agent-eval dashboard results/

# 파일 확인
ls results/*.json
```

**원인 C**: `auto_save=True` 설정 후 충분한 태스크가 누적되지 않음 (기본 10건마다 저장)

> **포트 참고**: 대시보드 기본 포트는 **8765**다 (8000이나 8080이 아님). 브라우저에서 `http://localhost:8765`로 접속한다.

---

### 3. agent-eval gate 항상 실패

**증상**: CI/CD에서 `gate` 명령이 항상 exit code 1로 종료.

**원인**: 임계값이 현재 데이터 수준보다 높게 설정됨.

**해결책**: `generate_gate_config()`로 현재 지표 기반 적정 임계값을 확인한 후, CLI에 직접 지정한다.

```python
from agent_evaluator import QuickEval

eval_q = QuickEval("results/")
# ... 평가 실행 후
eval_q.generate_gate_config("gate_config.json")
# gate_config.json에 현재 지표의 95% 수준 임계값이 저장됨 — 값을 확인 후 CLI에 직접 지정
```

```bash
# 현재 성능 기반으로 임계값 직접 지정
agent-eval gate result.json --tcr 85 --accuracy 70
```

> **Harness 관점**: `agent-eval gate` exit code 1은 단순 실패가 아니라 **Gate A(목표 달성) 또는 Gate C(신뢰성) 기준 미달 신호**다. 임계값을 낮추기 전에 어떤 지표가 부족한지 먼저 분석하자.

---

### 4. accuracy_score가 항상 0.0

**증상**: 모든 태스크의 `accuracy_score`가 0.0으로 기록됨.

**원인 A**: `ground_truth`를 빈 문자열(`""`) 또는 `None`으로 전달

```python
# 잘못됨 — ground_truth가 없으면 정확도를 계산할 수 없음
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str: ...

agent("질문", ground_truth="")  # 빈 문자열 전달

# 올바름
agent("질문", ground_truth="정답 텍스트")
```

**원인 B**: `task_type`이 실제 수행 내용과 다름 (예: 코드 생성인데 `"qa"`로 설정)

---

### 5. 환각 지표가 항상 0.0 또는 None

**증상**: `report.hallucination_rate`가 항상 `None` 또는 0.0.

**원인**: `enable_hallucination_detection=False` (기본값). opt-in 필요.

```python
# 방법 1: PerformanceMonitor에서 활성화
monitor = PerformanceMonitor(enable_hallucination_detection=True, use_korean_tokenizer=True)

# 방법 2: 팩토리 메서드 사용
monitor = PerformanceMonitor.for_rag_evaluation()

# 방법 3: 데코레이터에서 임시 활성 (해당 함수 호출에만 적용)
@agent_eval(monitor, task_type="information_retrieval", enable_hallucination_detection=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str: ...

# 방법 4: rag_mode 사용
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True, context_arg="context")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str: ...
```

> **주의**: `enable_hallucination=True`는 잘못된 파라미터명이다. 반드시 `enable_hallucination_detection=True`로 써야 한다.

---

### 6. 보안 지표가 수집되지 않음

**증상**: 보안 관련 모든 지표(`input_security`, `output_leakage` 등)가 보고서에 없음.

**원인**: `enable_security_metrics=False` (기본값). opt-in 필요.

```python
# 방법 1: PerformanceMonitor에서 활성화
monitor = PerformanceMonitor(enable_security_metrics=True, use_korean_tokenizer=True)

# 방법 2: 팩토리 메서드 사용
monitor = PerformanceMonitor.for_secure_agents()

# 방법 3: 데코레이터에서 임시 활성
@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def agent(question: str, ground_truth: str = "") -> str: ...
```

> **주의**: `enable_security=True`는 잘못된 파라미터명이다. 반드시 `enable_security_metrics=True`로 써야 한다.
>
> **Harness 관점**: 보안 지표는 **Gate E(Security Boundary)** 판정의 핵심이다. 프로덕션 배포 전 `enable_security_metrics=True`로 한 번은 반드시 평가해야 한다.

---

### 7. ImportError: No module named 'openai'

**증상**: `from agent_evaluator import LLMJudge` 또는 LLM Judge 기능 사용 시 ImportError.

**해결책**:

```bash
# openai/anthropic는 기본 설치에 포함 — 재설치로 해결
pip install --upgrade agent-evaluator
```

`openai`와 `anthropic` 패키지는 기본 설치에 포함되어 있다. ImportError가 발생하면 기본 설치가 올바르게 완료되지 않은 것이다.

---

### 8. ImportError: No module named 'langchain'

**증상**: `framework="langchain"` 사용 또는 LangChain 예제 실행 시 ImportError.

**해결책**:

```bash
pip install "agent-evaluator[langchain]"
```

LangGraph도 동일한 extras에 포함된다 (`langgraph>=1.0.0`).

---

### 9. ragas 설치 후 datasets 버전 충돌

**증상**: `pip install "agent-evaluator[eval]"` 후 `ImportError` 또는 ragas API 오류.

**원인**: `datasets` 패키지 버전 불일치.

**해결책**:

```bash
pip install "datasets>=4.0.0,<6.0.0"
```

ragas 0.4.x는 `EvaluationDataset`, `SingleTurnSample` API를 사용한다. 구버전 `datasets`와 호환되지 않는다.

> **참고**: `AnswerRelevancy` 지표는 OpenAI API 키가 있을 때만 임베딩이 자동 설정된다. Anthropic 전용 환경에서는 `AnswerRelevancy`를 지표 목록에서 제외해야 한다.

---

### 10. batch_eval DataFrame이 비어있음

**증상**: `return_format="dataframe"` 설정 후 빈 DataFrame 반환.

**원인**: 함수 서명에서 첫 번째 인자가 `questions` 리스트여야 한다.

```python
# 잘못됨
@batch_eval(monitor, task_type="qa")
def batch_agent(question: str, ground_truth: str = "") -> str:  # 단일 항목
    return llm.invoke(question)

# 올바름
@batch_eval(monitor, task_type="qa", return_format="dataframe")
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

df = batch_agent(questions, ground_truths=gts)
```

---

### 11. conversation_eval 세션 데이터 중복

**증상**: 대화 세션 지표에 중복 턴이 기록되거나 세션이 섞임.

**원인**: 같은 `session_id`를 여러 세션에서 재사용.

**해결책**: 세션마다 고유한 `session_id`를 사용한다.

```python
import uuid

@conversation_eval(monitor, session_id_arg="session_id")
def chat_agent(message: str, session_id: str = "s1") -> str:
    return chatbot.chat(message)

# 각 사용자별 고유 ID
chat_agent("안녕하세요", session_id=str(uuid.uuid4()))
```

---

### 12. QuickEval.__repr__ AttributeError

**증상**: `print(eval)` 또는 REPL에서 `QuickEval` 객체 출력 시 `AttributeError: 'QuickEval' object has no attribute 'tcr_tracker'`.

**원인**: 구버전의 버그다. 최신 버전으로 업그레이드한다.

```bash
pip install --upgrade agent-evaluator
```

현재 버전에서는 태스크가 없을 때 `tasks=0`을 안전하게 반환한다.

---

### 13. LLM Judge가 동작하지 않음

**증상**: LLM Judge 지표(`completeness`, `relevance` 등)가 보고서에 없음.

**원인 A**: `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` 미설정.

```bash
export OPENAI_API_KEY=sk-proj-...
# 또는
export ANTHROPIC_API_KEY=sk-ant-...
```

**원인 B**: 데코레이터에 `llm_judge=LLMJudgeConfig()` 파라미터가 누락됨.

```python
# ❌ LLM Judge 비활성 — llm_judge 파라미터 없음
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str: ...

# ✅ LLM Judge 활성 (기본 5차원: completeness, relevance, factual_consistency, toxicity, bias)
from agent_evaluator import LLMJudgeConfig
@agent_eval(monitor, task_type="qa", llm_judge=LLMJudgeConfig())
def agent(question: str, ground_truth: str = "") -> str: ...

# ✅ Anthropic 모델 명시
@agent_eval(monitor, task_type="qa", llm_judge=LLMJudgeConfig(model="gpt-5-nano"))
def agent(question: str, ground_truth: str = "") -> str: ...

# ✅ RAG faithfulness 추가 — rag_mode=True 시 faithfulness 차원이 자동으로 추가됨
@agent_eval(monitor, task_type="information_retrieval",
            rag_mode=True, context_arg="context",
            llm_judge=LLMJudgeConfig())
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str: ...
```

**원인 C**: `PerformanceMonitor`에서 `judge_sample_rate=0`으로 설정됨.

```python
# ❌ sample_rate=0 → 모든 태스크 스킵
monitor = PerformanceMonitor(output_dir="results/", judge_sample_rate=0, use_korean_tokenizer=True)

# ✅ 기본 10% 샘플링
monitor = PerformanceMonitor(output_dir="results/", judge_sample_rate=0.1, use_korean_tokenizer=True)
```

**원인 D**: LLM Judge가 연속 오류로 자동 비활성화됨.

LLM Judge는 API 오류가 3회 연속 발생하면 `_disabled_reason`이 설정되어 자동으로 비활성화된다. 이 경우 보고서에서 LLM Judge 지표가 조용히 사라진다.

```python
judge = LLMJudge(model="gpt-5-nano")

# 비활성화 여부 확인
if judge._disabled_reason:
    print(f"LLM Judge 비활성화 이유: {judge._disabled_reason}")

# 오류 초기화 및 재활성화
judge.reset_errors()
```

API 키, 모델명, 네트워크 연결을 확인한 뒤 `reset_errors()`를 호출하면 Judge가 복구된다.

---

### 14. flush_every 저장이 안 됨

**증상**: `flush_every=10` 설정 후 파일이 생성되지 않음.

**원인 A**: `output_dir`이 `None`이거나 존재하지 않는 경로.

```python
# output_dir 반드시 지정
monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

@agent_eval(monitor, task_type="qa", flush_every=10)
def agent(question: str, ground_truth: str = "") -> str: ...
```

**원인 B**: 디렉토리 쓰기 권한 없음. `ls -la results/`로 권한을 확인한다.

---

### 15. TaskResult frozen=True 오류

**증상**: `result.accuracy_score = 0.9` 등 TaskResult 필드를 직접 수정하려 할 때 `FrozenInstanceError`.

**원인**: `TaskResult`는 `@dataclass(frozen=True)` — 불변 객체.

**해결책**: `to_dict()`로 복사한 후 수정하거나 `create_taskresult()`로 새로 생성한다.

```python
# to_dict()로 변환 후 수정
d = result.to_dict()
d["accuracy_score"] = 0.9
new_result = TaskResult.from_dict(d)

# 또는 create_taskresult()로 새로 생성
from agent_evaluator import create_taskresult
new_result = create_taskresult(
    task_id="task_001",
    question="질문",
    response="답변",
    ground_truth="정답",
    execution_time=1.0,
    task_type="qa",
)
```

---

### 16. evaluation_session 컨텍스트에서 예외 후 데이터 손실

**증상**: `with evaluation_session(...)` 블록 내에서 예외 발생 후 결과 파일이 없음.

**원인**: `PerformanceMonitor`를 직접 사용하고 `finally`에서 `save_to_file()`을 호출하지 않음.

**해결책 A**: `evaluation_session` 컨텍스트 매니저를 사용한다 — 예외 발생 시에도 자동 저장된다.

```python
from agent_evaluator import evaluation_session

with evaluation_session("output_filename") as monitor:
    result = agent.run(task)
    monitor.record_task(result)
# 세션 종료 시 자동 저장 (예외 발생 시에도 안전)
```

**해결책 B**: `PerformanceMonitor` 직접 사용 시 `finally` 블록에서 저장한다.

```python
monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)
try:
    monitor.record_task(result)
finally:
    monitor.save_to_file("evaluation")
```

---

### 17. Pydantic 버전 충돌 (crewai + autogen 동시)

**증상**: crewai와 autogen을 동시에 설치하면 pydantic 2.11.x로 silent downgrade.

**원인**: crewai는 `pydantic<2.12`를 요구하고, autogen은 `pydantic>=2.12`를 선호한다.

**영향**: 기능 동작은 정상이지만 autogen 최신 기능 일부가 제한될 수 있다.

**권장 방법**: crewai와 autogen을 별도 가상환경에서 격리하여 사용한다.

```bash
# crewai 환경
python -m venv venv-crewai
pip install "agent-evaluator[crewai]"

# autogen 환경
python -m venv venv-autogen
pip install "agent-evaluator[autogen]"
```

---

### 18. auto_detect_framework가 잘못 감지됨

**증상**: `auto_detect_framework=True` 활성 시 잘못된 프레임워크로 감지되어 메타데이터 추출 오류.

**해결책**: `framework=` 파라미터로 명시적으로 지정한다.

```python
# 자동 감지 — 오감지 가능
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str: ...

# 명시적 지정 — 안전
@agent_eval(monitor, task_type="qa", framework="openai")
def agent(question: str, ground_truth: str = "") -> str: ...
```

지원 프레임워크 목록: `langchain`, `langgraph`, `crewai`, `autogen`, `dspy`, `pydanticai`, `anthropic`, `openai`, `gemini`, `llamaindex`, `haystack`, `groq`, `mistral`, `cohere`, `bedrock`, `ollama`, `vllm`, `huggingface`, `smolagents`, `semantic_kernel`, `vertexai`

---

### 19. agent-eval monitor --check 실패

**증상**: `agent-eval monitor --check` 실행 시 오류 또는 미설치 표시.

**원인 A**: 기본 설치가 완료되지 않음 (OTEL은 기본 설치에 포함)

```bash
pip install --upgrade agent-evaluator
```

**원인 B**: 포트가 이미 사용 중

`agent-eval monitor --check`는 다음 두 포트를 확인한다:
- **포트 4317**: OTEL gRPC 수신 포트 (스팬 전송에 사용)
- **포트 6006**: Phoenix UI 포트 (브라우저 접속)

```bash
# 포트 사용 확인
lsof -i :6006
lsof -i :4317

# Phoenix를 다른 포트로 기동 (UI 포트만 변경)
agent-eval monitor --port 6007
```

---

### 20. evaluation HTML 보고서가 깨짐

**증상**: `monitor.save_to_file("evaluation")` 후 생성된 `.html` 파일이 깨지거나 `TemplateNotFound` 오류.

**원인**: `jinja2` 미설치. 기본 설치에 포함되어 있어야 한다.

**해결책**:

```bash
# jinja2는 기본 설치에 포함 — 재설치로 해결
pip install --upgrade agent-evaluator
# 또는 단독 설치
pip install jinja2>=3.1.0
```

---

### 21. 대시보드 Parquet/Excel 내보내기 HTTP 409

**증상**: 대시보드에서 "Export Excel" 또는 "Export Parquet" 버튼 클릭 시 HTTP 409 오류.

**원인**: `[export]` extras가 설치되지 않음. Parquet 내보내기는 `pyarrow`, Excel 내보내기는 `openpyxl`이 필요하며, 미설치 시 서버가 HTTP 409로 응답한다.

**해결책**:

```bash
pip install "agent-evaluator[export]"
# 또는 개별 설치
pip install pyarrow openpyxl
```

설치 후 대시보드 서버를 재시작해야 한다.

```bash
agent-eval dashboard results/
```

---

### 22. Gate 결과가 JSON에서 조회되지 않음

**증상**: `result.json` 파일에서 `result["harness_gates"]` 키를 찾을 수 없음. `KeyError` 발생.

**원인**: Gate A–G 결과는 `harness_gates` 키가 아닌 `extra_metrics.harness_groups` 키에 저장된다. 내부 구현 명칭과 직관적 이름이 다르다.

**해결책**:

```python
import json

with open("results/evaluation.json") as f:
    data = json.load(f)

# ❌ 잘못된 키
gates = data["harness_gates"]           # KeyError

# ✅ 올바른 키
gates = data["extra_metrics"]["harness_groups"]

# 예: Gate A 결과 확인
gate_a = gates.get("A", {})
print(gate_a)
```

> **Harness 관점**: `extra_metrics.harness_groups` 아래에는 Gate A–G 각각의 점수, 통과/경고/실패 판정, 개별 Config 지표가 담겨 있다. CI/CD 스크립트에서 특정 Gate를 직접 파싱할 때 이 경로를 사용한다.

---

### 23. agent-eval trend --fail-on-regression exit code 혼동

**증상**: CI/CD에서 `agent-eval trend --fail-on-regression`의 종료 코드 의미를 혼동함.

**원인**: `agent-eval gate`는 임계값 미달 시 exit code 1, `--fail-on-regression` 회귀 초과 시 exit code 2를 반환한다. `agent-eval trend --fail-on-regression`은 회귀 감지 시 exit code 1을 반환한다. 두 명령어의 실패 코드가 달라 혼동하기 쉽다.

| 명령어 | exit 0 | exit 1 | exit 2 |
|--------|--------|--------|--------|
| `agent-eval gate` | 임계값 통과 | 임계값 미달 | `--fail-on-regression` 회귀 초과 |
| `agent-eval trend --fail-on-regression` | 회귀 없음 | 회귀 감지 | — |

```yaml
# GitHub Actions 예시 — 종료 코드별 처리
- name: 품질 게이팅
  run: agent-eval gate results/evaluation.json --tcr 85 --accuracy 70
  # exit 1: 임계값 미달, exit 2: --fail-on-regression 회귀 초과 → 파이프라인 자동 차단

- name: 회귀 탐지
  run: agent-eval trend results/ --fail-on-regression
  # exit 1 → 회귀 감지, exit 0 → 정상
```

> **Harness 관점**: exit 1(회귀)는 **Gate C(Reliability)** 또는 **Gate D(Performance Contract)** 기준이 이전 배포 대비 하락했다는 신호다. 단순히 재시도하지 말고 어떤 지표가 떨어졌는지 추세 보고서를 분석하자.

---

## 자주 묻는 질문 (FAQ) 10가지

---

### Q1. ground_truth 없이 평가가 가능한가?

가능하다. `ground_truth`가 없는 경우:
- `accuracy_score`는 0.0으로 기록됨 (무의미)
- `hallucination_rate`는 계산되지 않음
- `LLMJudge`는 기본 5차원(`completeness`, `relevance`, `factual_consistency`, `toxicity`, `bias`)을 ground_truth 없이 채점 가능

```python
@agent_eval(monitor, task_type="qa", llm_judge=LLMJudgeConfig())
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

agent("질문")  # ground_truth 없이 호출 — LLM Judge만 동작
```

---

### Q2. 비동기(async) 에이전트를 평가할 수 있나?

가능하다. `@agent_eval` 데코레이터는 `async def` 함수를 자동으로 감지한다.

```python
@agent_eval(monitor, task_type="qa", framework="autogen")
async def async_agent(question: str, ground_truth: str = "") -> str:
    return await agent.run(question)

# 비동기 컨텍스트 매니저
async with async_evaluation_session("output") as monitor:
    result = await agent.run(task)
    monitor.record_task(result)
```

---

### Q3. 한 번의 평가 세션에 여러 에이전트를 포함할 수 있나?

가능하다. 하나의 `PerformanceMonitor`에 여러 에이전트의 `TaskResult`를 기록할 수 있다.

```python
monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

@agent_eval(monitor, task_type="qa", framework="openai")
def agent_a(question: str, ground_truth: str = "") -> str: ...

@agent_eval(monitor, task_type="tool_use", framework="langchain")
def agent_b(question: str, ground_truth: str = "") -> str: ...

# 두 에이전트 모두 같은 monitor에 기록됨
```

---

### Q4. 결과를 pandas DataFrame으로 추출하는 방법은?

```python
df = monitor.export_to_dataframe()
# 컬럼: task_id, task_type, success, completion_score, accuracy_score,
#        execution_time, tokens_total, tokens_input, tokens_output,
#        framework, tool_call_count, has_error, attempts, timestamp, ...
```

`QuickEval`에서도 동일하게 사용 가능하다.

---

### Q5. 골든 데이터셋이란 무엇인가?

높은 점수를 받은 우수 평가 케이스를 모아둔 참조 데이터셋이다. 회귀 테스트, 새 모델 비교, 파인튜닝 데이터로 활용한다. `agent-eval dataset build` 명령어로 자동 추출하거나 `GoldenSetBuilder`를 코드에서 직접 사용할 수 있다.

---

### Q6. 평가 데코레이터를 적용해도 에이전트 성능에 영향이 있나?

Gate A–G 네이티브 지표는 순수 Python 알고리즘으로 계산되므로 오버헤드가 매우 작다 (태스크당 < 5ms). 단, 보안 지표(`enable_security_metrics=True`) 활성화 시 5~15ms 추가 오버헤드가 발생한다. LLM Judge(`llm_judge=LLMJudgeConfig()`)는 외부 API 호출을 수반하므로 수 초의 추가 시간이 필요하다.

---

### Q7. 멀티턴 대화에서 문맥 유지율을 측정하는 방법은?

`ConversationSession` 또는 `@conversation_eval` 데코레이터를 사용한다.

```python
from agent_evaluator import conversation_eval

@conversation_eval(monitor, session_id_arg="session_id")
def chat_agent(message: str, session_id: str = "s1") -> str:
    return chatbot.chat(message)

chat_agent("안녕하세요", session_id="u1")
chat_agent("오늘 날씨는?", session_id="u1")
```

`ConversationMetrics.context_retention` 지표로 문맥 유지율을 확인한다.

---

### Q8. CI/CD에서 평가를 자동화하는 방법은?

```yaml
# GitHub Actions 예시
- name: 에이전트 평가
  run: python evaluate.py

- name: 품질 게이팅
  run: agent-eval gate results/evaluation.json --tcr 85 --accuracy 70
  # exit 0: 통과, exit 1: 임계값 미달, exit 2: --fail-on-regression 회귀 초과 → 파이프라인 차단

- name: 회귀 탐지 (선택)
  run: agent-eval trend results/ --fail-on-regression
  # exit 0: 정상, exit 1: 회귀 감지 → 파이프라인 차단
```

`agent-eval gate`는 임계값 미달 시 exit code 1, `--fail-on-regression` 회귀 초과 시 exit code 2를 반환한다. `agent-eval trend --fail-on-regression`은 회귀 감지 시 exit code 1을 반환한다. 두 명령어 모두 파이프라인을 자동 차단한다.

---

### Q9. 평가 결과를 외부 시스템으로 내보내는 방법은?

```python
# Weights & Biases
monitor.export_to_wandb()

# MLflow
monitor.export_to_mlflow()

# pandas DataFrame → CSV, Excel
df = monitor.export_to_dataframe()
df.to_csv("results.csv")
```

대시보드 API에서 `/export/excel` 엔드포인트로 Excel 파일 다운로드도 가능하다. 단, 이 기능은 `[export]` extras(`pyarrow` + `openpyxl`) 설치가 필요하다. 미설치 시 HTTP 409가 반환된다.

---

### Q10. 이미 기록된 평가 결과를 재분석하는 방법은?

```python
from agent_evaluator import QuickEval

eval_q = QuickEval("results/")
eval_q.replay("results/evaluation.json")  # 기존 JSON 파일 재로딩

# 재분석 후 gate 적용
eval_q.gate(tcr=85, accuracy=70)

# DataFrame으로 추출
df = eval_q.export_to_dataframe()
```
