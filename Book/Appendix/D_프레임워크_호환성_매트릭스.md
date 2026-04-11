# Appendix D. 프레임워크 호환성 매트릭스

Agent Evaluator v0.7.7 기준. 21개 통합 프레임워크와 8개 평가 플랫폼 비교를 정리한다.

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
| `anthropic` | `[llm]` | ✅ | ❌ | ✅ | ❌ | ❌ |
| `openai` | `[llm]` | ✅ | ❌ | ✅ | ❌ | ❌ |
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

**자동 감지**: `auto_detect_framework=True` (기본 활성) 설정 시 12개 속성 기반으로 프레임워크를 자동 감지한다. 오감지가 의심될 경우 `framework=` 파라미터로 명시적으로 지정한다.

---

## 4대 프레임워크 지표 커버리지

| 프레임워크 | 아키텍처 | 토큰 정확도 | 멀티에이전트 | 지표 커버리지 |
|-----------|---------|:----------:|:----------:|:-----------:|
| LangChain | 체인 + 에이전트 | ✅ 실제값 | ❌ 단일 | ~82% (~21개) |
| LangGraph | 상태 머신 / DAG | 부분 | 부분 (노드 전환) | ~82% (~21개) |
| CrewAI | 역할 기반 멀티에이전트 | ❌ 0 고정 | ✅ | ~78% (~20개) |
| AutoGen | 대화형 멀티에이전트 | 부분 (tiktoken) | ✅ | ~80% (~20개) |

---

## 9개 평가 플랫폼 기능 비교

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

### 단독 extras

| extras | 설치 명령어 | 포함 패키지 | 설치 시간 |
|--------|-----------|-----------|--------|
| `[llm]` | `pip install "agent-evaluator[llm]"` | openai, anthropic | 빠름 |
| `[langchain]` | `pip install "agent-evaluator[langchain]"` | langchain, langchain-core, langgraph | 중간 |
| `[crewai]` | `pip install "agent-evaluator[crewai]"` | crewai (전이 의존성 100개+) | 느림 |
| `[autogen]` | `pip install "agent-evaluator[autogen]"` | pyautogen, autogen-agentchat | 느림 |
| `[eval]` | `pip install "agent-evaluator[eval]"` | deepeval, ragas, datasets | 중간 |
| `[dspy]` | `pip install "agent-evaluator[dspy]"` | dspy-ai | 중간 |
| `[pydanticai]` | `pip install "agent-evaluator[pydanticai]"` | pydantic-ai | 빠름 |
| `[serve]` | `pip install "agent-evaluator[serve]"` | fastapi, uvicorn, jinja2 | 빠름 |
| `[otel]` | `pip install "agent-evaluator[otel]"` | opentelemetry-sdk, arize-phoenix | 중간 |

### 조합 extras (권장)

| extras | 설명 | 설치 시간 |
|--------|------|--------|
| `[all]` | crewai / autogen / otel 제외 전체 | 합리적 |
| `[full]` | 모든 패키지 포함 (crewai, autogen, otel 포함) | 10분+ |

**용도별 최적 조합**

| 용도 | 권장 extras | 이유 |
|------|-----------|------|
| 빠른 시작 | `[llm,serve]` | LLM Judge + 대시보드 |
| LangChain/LangGraph | `[langchain,serve]` | 프레임워크 통합 + 대시보드 |
| RAG 평가 | `[eval,serve]` | Ragas + DeepEval + 대시보드 |
| 운영 모니터링 | `[llm,serve,otel]` | Phoenix 연동 포함 |
| CrewAI 전용 | `[crewai]` | 단독 격리 설치 |
| AutoGen 전용 | `[autogen]` | 단독 격리 설치 |
| 범용 (권장) | `[all]` | 대부분 기능 포함 |

### 알려진 의존성 충돌

| 상황 | 증상 | 해결책 |
|------|------|--------|
| crewai + autogen 동시 설치 | pydantic 2.11.x로 downgrade | 기능은 정상 동작. autogen 최신 기능 일부 제한 가능 |
| ragas 설치 후 datasets 충돌 | ImportError 또는 API 불일치 | `pip install "datasets>=4.0.0,<6.0.0"` |
| autogen 0.4+ async API | sync 함수 래핑 시 오류 | `@agent_eval(framework="autogen")`으로 async 함수 래핑 |

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

# AutoGen 전용 (비동기)
from agent_evaluator.integrations import autogen_eval_async

@autogen_eval_async(monitor, task_type="qa")
async def autogen_agent(question: str, ground_truth: str = "") -> str:
    return await agent.run(question)
```

`@agent_eval(monitor, framework="langchain")` 방식과 동일하게 동작하지만, 전용 데코레이터는 프레임워크별 추가 검증 로직을 포함한다.
