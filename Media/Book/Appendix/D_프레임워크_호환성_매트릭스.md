# Appendix D. 프레임워크 호환성 매트릭스

Agent Evaluator v0.9.1 기준. 21개 통합 프레임워크와 8개 평가 플랫폼 비교를 정리한다.

---

## Harness 관점: 프레임워크가 달라도 Gate 기준은 동일하다

Agent Evaluator의 핵심 설계 원칙 중 하나는 **프레임워크 독립성**이다. LangChain을 쓰든 CrewAI를 쓰든 AutoGen을 쓰든, Gate A~G의 **7개 Harness Gate와 33개 Config는 완전히 동일하게 작동**한다.

```
프레임워크 종류  →  @agent_eval(framework="...")  →  메타데이터 자동 추출
                                                          ↓
                                              Gate A–G 동일 기준으로 판정
                                              (InstructionConfig, SLAConfig 등
                                               33개 Config 모두 프레임워크 무관)
```

즉, LangChain 팀과 AutoGen 팀이 동일한 Gate 기준으로 에이전트 품질을 비교할 수 있다. 프레임워크 전환 시에도 평가 설정을 다시 작성할 필요가 없다.

**프레임워크별로 달라지는 것**은 `@agent_eval` 데코레이터가 응답 객체에서 자동 추출하는 **메타데이터의 종류와 정밀도**뿐이다. 아래 매트릭스가 그 차이를 정리한다.

---

## 21개 통합 프레임워크 메타데이터 추출 지원 현황

`@agent_eval(monitor, framework="...")` 파라미터를 지정하면 에이전트 응답 객체에서 아래 메타데이터를 자동으로 추출한다.

| 프레임워크 | extras | tool_calls | chain_steps | tokens_used | state_transitions | agent_interactions |
|-----------|--------|:----------:|:-----------:|:-----------:|:----------------:|:-----------------:|
| `langchain` | `[langchain]` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `langgraph` | `[langchain]` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `crewai` | `[crewai]` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `autogen` | `[autogen]` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `dspy` | `[dspy]` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `pydanticai` | `[pydanticai]` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `anthropic` | 기본 설치에 포함 | ✅ | ❌ | ✅ | ❌ | ❌ |
| `openai` | 기본 설치에 포함 | ✅ | ❌ | ✅ | ❌ | ❌ |
| `gemini` | 별도 설치 | ✅ | ❌ | ✅ | ❌ | ❌ |
| `llamaindex` | 별도 설치 | ✅ | ✅ | ✅ | ❌ | ❌ |
| `haystack` | 별도 설치 | ✅ | ✅ | ❌ | ❌ | ❌ |
| `groq` | 별도 설치 | ✅ | ❌ | ✅ | ❌ | ❌ |
| `mistral` | 별도 설치 | ✅ | ❌ | ✅ | ❌ | ❌ |
| `cohere` | 별도 설치 | ✅ | ❌ | ✅ | ❌ | ❌ |
| `bedrock` | 별도 설치 | ✅ | ❌ | ✅ | ❌ | ❌ |
| `ollama` | 별도 설치 | ✅ | ❌ | ✅ | ❌ | ❌ |
| `vllm` | 별도 설치 | ✅ | ❌ | ✅ | ❌ | ❌ |
| `huggingface` | 별도 설치 | ❌ | ❌ | ✅ | ❌ | ❌ |
| `smolagents` | 별도 설치 | ✅ | ✅ | ✅ | ❌ | ❌ |
| `semantic_kernel` | 별도 설치 | ✅ | ❌ | ✅ | ❌ | ❌ |
| `vertexai` | 별도 설치 | ✅ | ❌ | ✅ | ❌ | ❌ |

**메타데이터 항목 설명**

| 항목 | 설명 |
|------|------|
| `tool_calls` | 도구 호출 목록 (ToolCallAnalyzer, ToolSelectionTracker에 공급) |
| `chain_steps` | 체인/파이프라인 실행 단계 목록 (WorkflowExecutionTracker에 공급) |
| `tokens_used` | 토큰 사용량 `{"total": int, "input": int, "output": int}` |
| `state_transitions` | 상태 전이 시퀀스 (LangGraph, CrewAI, AutoGen 전용) |
| `agent_interactions` | 에이전트 간 교환 목록 (멀티에이전트 전용) |

> **중요: SDK 자체는 extras 없이도 동작한다.** SDK는 duck typing과 `try/except`로 프레임워크를 감지하므로, `[langchain]`이나 `[crewai]`를 설치하지 않아도 SDK 자체 기능은 전혀 제한되지 않는다. extras가 필요한 것은 **사용자의 에이전트 코드**가 해당 프레임워크를 import할 때뿐이다. (자세한 설명은 아래 "왜 extras를 설치하는가?" 참고)

**자동 감지**: `auto_detect_framework=True` (기본 활성) 설정 시 12개 속성 기반으로 프레임워크를 자동 감지한다. 오감지가 의심될 경우 `framework=` 파라미터로 명시적으로 지정한다.

---

## 4대 프레임워크 지표 커버리지

| 프레임워크 | 아키텍처 | 토큰 정확도 | 멀티에이전트 | 지표 커버리지 |
|-----------|---------|:----------:|:----------:|:-----------:|
| LangChain | 체인 + 에이전트 | ✅ 실제값 | ❌ 단일 | ~82% (~21개) |
| LangGraph | 상태 머신 / DAG | 부분 | 부분 (노드 전환) | ~82% (~21개) |
| CrewAI | 역할 기반 멀티에이전트 | ❌ 0 고정 | ✅ | ~78% (~20개) |
| AutoGen | 대화형 멀티에이전트 | 부분 (tiktoken) | ✅ | ~80% (~20개) |

> **지표 커버리지 기준**: Gate A-G의 **25개 Tracker** 기준으로 산출 (분모 = 25).  
> 33개 Harness Config는 모든 프레임워크에서 동일하게 설정 가능하므로 커버리지에 포함하지 않음.  
> **토큰 정확도**: ✅ 실제값 = LLM API 응답에서 실제 토큰 수 획득 | ❌ 0 고정 = 프레임워크에서 토큰 정보 미제공, 추정값 사용 | 부분 = 일부 호출 경로에서만 가능

### AI Native 속성별 프레임워크 지원 현황

에이전트의 AI Native 속성을 평가하는 데 프레임워크별로 제공하는 메타데이터가 다르다.

| AI Native 속성 | LangChain | LangGraph | CrewAI | AutoGen |
|--------------|-----------|-----------|--------|---------|
| 비결정론적 출력 추적 | △ (체인 단계 기록) | ✅ (상태 전이 추적) | △ | ✅ (대화 로그) |
| 다단계 추론 추적 | ✅ chain_steps | ✅ chain_steps | ✅ chain_steps | ✅ chain_steps |
| 도구 활용 메타데이터 | ✅ tool_calls | ✅ tool_calls | ✅ tool_calls | ✅ tool_calls |
| 자율 목표 추구 범위 탐지 | ❌ | ✅ state_transitions | ✅ state_transitions | ✅ agent_interactions |
| 멀티에이전트 협업 추적 | ❌ | △ (노드 전환만) | ✅ agent_interactions | ✅ agent_interactions |

△ = 부분 지원 (Tracker 자동 추출은 가능하나 데이터 완결성 제한)

> **선택 가이드**: 비결정론적 출력 분석이 중요하면 LangGraph/AutoGen, 멀티에이전트 협업 완전 추적이 필요하면 CrewAI/AutoGen을 선택한다.

---

## 8개 평가 플랫폼 기능 비교

Agent Evaluator와 주요 경쟁 평가 플랫폼을 비교한다.

### OTEL 지원 수준

| 플랫폼 | OTEL 지원 | 역할 |
|--------|----------|------|
| Ragas | 간접 지원 | 없음 (외부 플랫폼 연동) |
| DeepEval | 완전 지원 | OTLP 엔드포인트 |
| Arize Phoenix | 핵심 아키텍처 | Collector + UI (OpenInference) |
| Evidently AI | Tracely 경유 지원 | 별도 패키지 필요 |
| Braintrust | 호환 모드 | 환경변수 2개로 설정 |
| Helicone | 부분 지원 | 프록시가 주력 |
| W&B Weave | 완전 인제스트 | Collector |
| **Agent Evaluator** | OTLP Exporter | `setup_otel()` + 자동 스팬 발행 |

### LLM API 비용 (1,000 태스크 기준)

| 플랫폼 | LLM API 비용 | 오프라인 실행 | 계산 지연 |
|--------|:-----------:|:-----------:|:--------:|
| Ragas | $5~20 | ❌ | 수 초~분 |
| DeepEval | $3~15 | 부분 | 수 초 |
| Arize Phoenix | $3~10 | ✅ 로컬 | 수 초 |
| Evidently AI | $0 | ✅ | 밀리초~초 |
| Braintrust | 선택적 | 부분 | 선택적 |
| Helicone | $0 | ❌ | 없음 (집계만) |
| W&B Weave | 선택적 | 부분 | 선택적 |
| **Agent Evaluator** | **$0** (네이티브 16개) | **✅** | **밀리초** |

### 대시보드 및 UI

| 플랫폼 | UI 유형 | 셀프호스트 | 비용 |
|--------|--------|:---------:|------|
| Ragas | 없음 | — | Ragas.io 별도 |
| DeepEval | SaaS (Confident AI) | ❌ | 무료(500 runs) / $49/월~ |
| Arize Phoenix | OSS UI | ✅ | 무료 / Cloud 유료 |
| Evidently AI | OSS + Cloud | ✅ | $99/월~ |
| Braintrust | SaaS | ❌ | 무료(1,000 로그) / $100/월~ |
| Helicone | SaaS + OSS | ✅ | 무료(10,000 요청) / $20/월~ |
| W&B Weave | SaaS | ❌ | 무료(개인) / $50/월/좌석~ |
| **Agent Evaluator** | **OSS 로컬 9탭** | **✅ 완전 로컬** | **무료** |

Agent Evaluator 대시보드 9개 탭: 품질 / 멀티턴 대화 / 성능 / 에이전틱 / 보안 / 이상 감지 / 평가 비용 / 골든 데이터셋 / 투명성

### 에이전틱 AI 전용 지표 비교

| 지표 | Ragas | DeepEval | Phoenix | Agent Evaluator |
|------|:-----:|:--------:|:-------:|:---------------:|
| Tool 선택 정확도 (F1) | ✅ | ✅ | ❌ | ✅ `ToolSelectionTracker` |
| Tool 효율성 / 불필요 호출 | ❌ | ❌ | ❌ | ✅ `ToolCallAnalyzer` |
| 재시도 / 자기수정 패턴 | ❌ | ❌ | ❌ | ✅ `RetryCorrectionTracker` |
| 멀티에이전트 협업 품질 | ❌ | ❌ | ❌ | ✅ `AgentCoordinationTracker` |
| 워크플로우 실행 추적 | ❌ | ❌ | 부분 | ✅ `WorkflowExecutionTracker` |
| 프롬프트 인젝션 탐지 | ❌ | 부분 (Red-team) | ❌ | ✅ `InputSanitizationTracker` |
| 출력 정보 유출 탐지 | ❌ | ❌ | ❌ | ✅ `OutputLeakageDetector` |
| 권한 상승 탐지 | ❌ | ❌ | ❌ | ✅ `PrivilegeEscalationDetector` |
| Tool 체인 공격 탐지 | ❌ | ❌ | ❌ | ✅ `ToolChainAttackDetector` |
| 허가되지 않은 Tool 사용 | ❌ | ❌ | ❌ | ✅ `ToolAuthorizationTracker` |

---

## extras 설치 가이드

### 왜 extras를 설치하는가? (초보자 안내)

처음 Agent Evaluator를 접하는 독자가 가장 많이 혼동하는 부분이 "extras를 왜 따로 설치해야 하나?"이다. 핵심을 한 문장으로 정리하면 다음과 같다.

> **SDK 자체는 extras 없이도 완전히 동작한다. extras는 '내 에이전트 코드'가 해당 프레임워크를 필요로 할 때만 설치한다.**

구체적인 예시로 생각해 보자.

```python
# 이 코드는 extras 없이도 동작한다 — SDK가 프레임워크 감지를 try/except로 처리
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa", framework="langchain")
def my_agent(question: str, ground_truth: str = "") -> str:
    # 이 안에서 LangChain을 import하고 사용한다면 [langchain]이 필요하다
    from langchain.chains import LLMChain   # ← 이 줄 때문에 [langchain] 필요
    ...
```

SDK(`@agent_eval`, `PerformanceMonitor` 등)는 `[langchain]` 없이도 import되고 실행된다. LangChain 관련 import가 **내 에이전트 코드 안에** 있을 때만 `[langchain]`이 필요하다.

### 기본 설치 포함 기능 (별도 설치 불필요)

v0.7.8부터 아래 기능들은 `pip install agent-evaluator` 기본 설치에 포함됩니다.

| 기능 | 포함 패키지 |
|------|-----------|
| LLM Judge 엔진 | openai, anthropic |
| FastAPI 대시보드 | fastapi, uvicorn, jinja2, python-multipart |
| OTEL 모니터링 | opentelemetry-sdk, arize-phoenix |
| PDF 처리 | pdfplumber |

### 별도 설치가 필요한 extras

| extras | 설치 명령어 | 주요 포함 패키지 (버전 범위) | 설치 시간 |
|--------|-----------|--------------------------|--------|
| `[langchain]` | `pip install "agent-evaluator[langchain]"` | langchain>=1.0.0,<3.0.0 · langchain-core · langchain-openai · langchain-anthropic · langgraph>=1.0.0 | 중간 |
| `[crewai]` | `pip install "agent-evaluator[crewai]"` | crewai>=1.0.0,<2.0.0 (전이 의존성 100개+) | 느림 |
| `[autogen]` | `pip install "agent-evaluator[autogen]"` | pyautogen>=0.3.0,<1.0.0 · autogen-agentchat>=0.4.0 · autogen-core>=0.4.0 | 느림 |
| `[eval]` | `pip install "agent-evaluator[eval]"` | deepeval>=3.0.0,<4.0.0 · ragas>=0.4.0,<2.0.0 · datasets>=4.0.0,<6.0.0 · langchain>=1.0.0 · langchain-openai>=0.1.0 | 중간 |
| `[dspy]` | `pip install "agent-evaluator[dspy]"` | dspy-ai>=2.0.0 | 중간 |
| `[pydanticai]` | `pip install "agent-evaluator[pydanticai]"` | pydantic-ai>=1.0.0,<2.0.0 | 빠름 |
| `[examples]` | `pip install "agent-evaluator[examples]"` | 기본 + eval 묶음 | 중간 |
| `[full]` | `pip install "agent-evaluator[full]"` | 위 전체 (crewai, autogen 포함) | 10분+ |

**용도별 최적 조합**

| 용도 | 권장 | 이유 |
|------|------|------|
| 빠른 시작 | `pip install agent-evaluator` | LLM Judge · 대시보드 · OTEL 기본 포함 |
| LangChain/LangGraph | `pip install "agent-evaluator[langchain]"` | 에이전트 코드가 langchain을 사용할 때 |
| RAG 외부 평가 | `pip install "agent-evaluator[eval]"` | Ragas + DeepEval 어댑터 사용 시 |
| 모든 예제 실행 | `pip install "agent-evaluator[examples]"` | 예제 의존성 포함 |
| CrewAI 전용 | `pip install "agent-evaluator[crewai]"` | 단독 격리 설치 권장 |
| AutoGen 전용 | `pip install "agent-evaluator[autogen]"` | 단독 격리 설치 권장 |
| 전체 설치 | `pip install "agent-evaluator[full]"` | ⚠️ 10분+, CI 호환성 검증용 |

### 알려진 의존성 충돌

| 상황 | 증상 | 원인 | 해결책 |
|------|------|------|--------|
| crewai + autogen 동시 설치 | pydantic 2.11.x로 silent downgrade | crewai는 `pydantic<2.12`를 요구하고 pyautogen은 `pydantic>=2.12`를 선호해 충돌 발생 | 기능은 정상 동작. autogen 최신 기능 일부 제한 가능. 격리가 필요하면 별도 가상환경 사용 |
| ragas 설치 후 datasets 충돌 | `ImportError` 또는 `EvaluationDataset` / `SingleTurnSample` API 불일치 | ragas>=0.4.0은 새 API(`EvaluationDataset`, `SingleTurnSample`)를 사용하므로 구버전 datasets와 충돌 | `pip install "datasets>=4.0.0,<6.0.0"` 명시 설치 |
| AutoGen 0.4+ async API | sync 함수에서 `await` 없이 호출 시 오류 | autogen-agentchat 0.4+는 async 기반 API로 전환됨 | `@agent_eval(framework="autogen")`으로 **async 함수**를 래핑. `async def` + `await agent.run(...)` 패턴 사용 |
| DeepEval AnswerRelevancy 오류 | embeddings 초기화 실패 | `AnswerRelevancy` 지표는 OpenAI API 키로 임베딩 모델을 호출함 | `OPENAI_API_KEY` 환경변수 설정. Anthropic-only 환경에서는 AnswerRelevancy 지표 제외 |

---

## 프레임워크별 전용 데코레이터

```python
from agent_evaluator.integrations import (
    langchain_eval,
    langgraph_eval,
    crewai_eval,
    autogen_eval,
    dspy_eval,
    pydanticai_eval,
)

# LangChain 전용 — usage_metadata 자동 추출
@langchain_eval(monitor, task_type="qa")
def lc_agent(question: str, ground_truth: str = "") -> str:
    return chain.invoke({"input": question})

# AutoGen 전용 (비동기) — autogen-agentchat 0.4+는 async API 필수
from agent_evaluator.integrations import autogen_eval_async

@autogen_eval_async(monitor, task_type="qa")
async def autogen_agent(question: str, ground_truth: str = "") -> str:
    return await agent.run(question)
```

`@agent_eval(monitor, framework="langchain")` 방식과 동일하게 동작하지만, 전용 데코레이터는 프레임워크별 추가 검증 로직을 포함한다.

> **Harness Gate 관점 요약**: 어떤 데코레이터 방식을 선택하더라도 Gate A–G의 판정 기준은 달라지지 않는다. `InstructionConfig`, `SLAConfig`, `ThreatSeverityConfig` 등 33개 Config는 모든 프레임워크에서 동일하게 `@agent_eval` 파라미터로 전달할 수 있다.
