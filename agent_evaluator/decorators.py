"""
@agent_eval / @batch_eval / @conversation_eval / eval_context
=============================================================
Opik ``@track`` 스타일로 agent-evaluator를 적용할 수 있는 데코레이터 모음.

데코레이터 목록
---------------
``agent_eval``
    동기·비동기 에이전트 함수에 Layer 1+2 평가를 자동 적용.
    retry(``max_retries``), 프레임워크 어댑터(``framework``), async 자동 감지 내장.
``batch_eval``
    List 입력 → List 처리 배치 함수용 (실행 모델이 다름, 별도 유지).
``conversation_eval``
    멀티턴 대화 함수에 ``ConversationSession`` 기반 세션 평가를 자동 적용.

추가 유틸
---------
``EvalMetadata``
    함수가 ``(response, EvalMetadata(...))`` 튜플을 반환할 때 사용하는 메타데이터
    컨테이너. 데코레이터가 자동 계산할 수 없는 필드를 함수 내부에서 주입한다.
``get_eval_ctx``
    함수 본문에서 현재 평가 컨텍스트(스레드 로컬)에 접근해 메타데이터를 동적으로
    주입한다.  반환값 타입을 바꾸고 싶지 않을 때 ``EvalMetadata`` 튜플 대신 사용.
``flush_conversation``
    ``conversation_eval`` 세션을 명시적으로 종료하고 지표를 기록한다.

파라미터 탐지 우선순위
----------------------
1. ``question_arg`` 에 지정한 이름의 파라미터
2. 함수의 첫 번째 positional 인자
3. 빈 문자열

메타데이터 병합 우선순위 (높은 순)
-------------------------------------
``EvalMetadata`` 튜플 반환  >  ``get_eval_ctx()`` 스레드 로컬  >  데코레이터 파라미터  >  자동 계산

반환값 변환 규칙
-----------------
- OpenAI ``ChatCompletion`` → ``choices[0].message.content``
- Anthropic ``Message`` → ``content[0].text`` + 토큰 자동 추출 (input + output)
- Google Gemini ``GenerateContentResponse`` → ``candidates[0].content.parts[0].text`` + 토큰 자동 추출 (prompt + candidates)
- LangChain ``BaseMessage`` (``content`` 속성) → ``.content``
- ``dict`` → ``"answer"`` / ``"output"`` / ``"result"`` / ``"text"`` 순으로 탐색
- 그 외 → ``str(raw)``

스트리밍 generator 함수(sync ``yield`` / async ``async for``)도 chunk passthrough 방식으로 지원

비동기 안전성
--------------
``get_eval_ctx()`` 는 ``contextvars.ContextVar`` 기반으로 구현되어 있어
``asyncio.create_task()`` / ``asyncio.gather()`` 등 동시 코루틴 환경에서도
각 태스크가 독립된 컨텍스트를 가진다. (threading.local 의 충돌 문제 없음)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import dataclasses
import functools
import inspect
import logging
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal, Union, cast

if TYPE_CHECKING:
    from agent_evaluator import PerformanceMonitor, TaskResult

# M1: 프레임워크 식별자 Literal — IDE 자동완성 지원 (Python 3.8+ 지원, from __future__ import annotations)
FrameworkLiteral = Literal[
    "native", "langchain", "langgraph", "crewai", "autogen",
    "dspy", "pydanticai", "anthropic", "openai", "gemini", "vertexai",
    "llamaindex", "haystack", "cohere", "groq", "mistral",
    "bedrock", "smolagents", "semantic_kernel", "ollama", "vllm", "huggingface",
    "openai_agents", "google_adk", "claude_agent_sdk",
]

logger = logging.getLogger(__name__)

__all__ = [
    "agent_eval",
    "agent_eval_async",
    "agent_eval_with_retry",
    "batch_eval",
    "conversation_eval",
    "flush_conversation",
    "flush_all_conversations",  # Gap S
    "eval_context",
    "EvalDecorator",   # Gap N
    "EvalMetadata",
    "TurnMetadata",
    "get_eval_ctx",
    # Task 1: 프레임워크 어댑터
    "_FRAMEWORK_ADAPTERS",
    "_extract_langchain_metadata",
    "_extract_langgraph_metadata",
    "_extract_crewai_metadata",
    "_extract_autogen_metadata",
    "_extract_dspy_metadata",
    "_extract_pydanticai_metadata",
    "_extract_anthropic_metadata",
    "_extract_openai_metadata",
    "_extract_gemini_metadata",
    "_extract_llamaindex_metadata",
    "_extract_haystack_metadata",
    # C6: 어댑터 메타데이터 레지스트리
    "_FRAMEWORK_ADAPTER_META",
    "get_framework_info",
    # Task 4: TaskType 정규화
    "_normalize_task_type",
    # Task 5: SimpleTaskAlertRule
    "SimpleTaskAlertRule",
    # M1: 프레임워크 타입 힌트
    "FrameworkLiteral",
    # H1-H4
    "AGENT_EVAL_PRESETS",
    # 항목 W: preset 런타임 등록
    "register_preset",
    # v0.8.1+: 파라미터 묶음 데이터클래스
    "RetryConfig",
    "LLMJudgeConfig",
    "SecurityConfig",
]


# ---------------------------------------------------------------------------
# RetryConfig — 재시도 파라미터 묶음 (v0.8.1+)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class RetryConfig:
    """agent_eval / batch_eval / conversation_eval 재시도 설정.

    Example::

        @agent_eval(monitor, task_type="qa", retry=RetryConfig(max=3, delay=1.0, backoff=2.0))
        def agent(question, ground_truth=""): ...
    """
    max: int = 1
    on: tuple = dataclasses.field(default_factory=lambda: (Exception,))
    delay: float = 0.0
    backoff: float = 1.0
    jitter_type: str = "full"
    max_delay: float = 60.0
    should_retry: Callable | None = None
    on_retry: Callable | None = None


# ---------------------------------------------------------------------------
# LLMJudgeConfig — LLM-as-Judge 설정 묶음 (v0.8.2+)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class LLMJudgeConfig:
    """LLM-as-Judge 설정 묶음.

    Example::

        @agent_eval(monitor, llm_judge=LLMJudgeConfig(model="claude-haiku-4-5-20251001", criteria=["accuracy"]))
        def agent(question, ground_truth=""): ...
    """
    model: str | None = None
    criteria: list[str] | None = None
    sample_rate: float = 0.1
    escalation_model: str | None = None
    escalation_threshold: float = 2.5
    budget_per_day: float | None = None
    budget_storage_path: str | None = None
    max_context_chars: int = 4000
    seed: int | None = None


# ---------------------------------------------------------------------------
# SecurityConfig — 보안 메트릭 설정 묶음 (v0.8.3+)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class SecurityConfig:
    """보안 메트릭 설정 묶음.

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    security=SecurityConfig(allowed_tools=["search"], restricted_tools=["shell_exec"],
                                            sample_rate=0.2))
        def agent(question, ground_truth=""): ...
    """
    allowed_tools: list[str] | None = None
    restricted_tools: list[str] | None = None
    sample_rate: float = 1.0  # InputSanitizationTracker·OutputLeakageDetector 샘플링 비율 (0.0–1.0)


# ---------------------------------------------------------------------------
# v0.9.0+: Phase 1 Harness Config 데이터클래스 6개 (A/B/C/G 그룹 보조)
# ---------------------------------------------------------------------------


# SPEC-000: Gate A 패키지로 이관됨 — 원본 구현은 gates/gate_a_goal/configs.py 참조
from .gates.gate_a_goal.configs import (
    ContextRetentionConfig,  # noqa: F401,E402
    GoalAlignmentConfig,  # noqa: F401,E402
    InstructionConfig,  # noqa: F401,E402
    KnowledgeRetentionConfig,  # noqa: F401,E402
    PlanConfig,  # noqa: F401,E402
    SubtaskConfig,  # noqa: F401,E402
)

# ---------------------------------------------------------------------------
# v0.9.2+: Phase 3 Harness Config 데이터클래스
# ---------------------------------------------------------------------------
# SPEC-000: Gate B 패키지로 이관됨 — 원본 구현은 gates/gate_b_behavioral/configs.py 참조
from .gates.gate_b_behavioral.configs import (
    ContextWindowConfig,  # noqa: F401,E402
    DeadlockConfig,  # noqa: F401,E402
    LoopDetectionConfig,  # noqa: F401,E402
    ScopeConfig,  # noqa: F401,E402
    StateConsistencyConfig,  # noqa: F401,E402
    ToolParameterSafetyConfig,  # noqa: F401,E402
)

# v0.9.3+: Phase 6 Harness Config 데이터클래스
# SPEC-000: Gate C 패키지로 이관됨 — 원본 구현은 gates/gate_c_reliability/configs.py 참조
from .gates.gate_c_reliability.configs import (
    FaultToleranceConfig,  # noqa: F401,E402
    GracefulDegradationConfig,  # noqa: F401,E402
    IdempotencyConfig,  # noqa: F401,E402
    ReproducibilityConfig,  # noqa: F401,E402
    RetryConsistencyConfig,  # noqa: F401,E402
)

# ---------------------------------------------------------------------------
# v0.9.1+: 신규 Harness Config 데이터클래스 7개
# ---------------------------------------------------------------------------
# SPEC-000: Gate D 패키지로 이관됨 — 원본 구현은 gates/gate_d_performance/configs.py 참조
from .gates.gate_d_performance.configs import (
    CostPredictabilityConfig,  # noqa: F401,E402
    EfficiencyConfig,  # noqa: F401,E402
    ResourceBudgetConfig,  # noqa: F401,E402
    SLAConfig,  # noqa: F401,E402
    TTFTVariabilityConfig,  # noqa: F401,E402
)

# SPEC-000: Gate E 패키지로 이관됨 — 원본 구현은 gates/gate_e_security/configs.py 참조
from .gates.gate_e_security.configs import (
    ComplianceConfig,  # noqa: F401,E402
    ThreatResponseConfig,  # noqa: F401,E402
    ThreatSeverityConfig,  # noqa: F401,E402
)

# v0.9.3+: Phase 4 Harness Config 데이터클래스
# SPEC-000 Commit 1: Gate F 패키지로 이관됨 — 원본 구현은 gates/gate_f_multiagent/configs.py 참조
from .gates.gate_f_multiagent.configs import (
    AgentRoleConfig,  # noqa: F401,E402
    ConflictResolutionConfig,  # noqa: F401,E402
    ConsensusConfig,  # noqa: F401,E402
    PropagationConfig,  # noqa: F401,E402
)

# SPEC-000: Gate G 패키지로 이관됨 — 원본 구현은 gates/gate_g_observability/configs.py 참조
from .gates.gate_g_observability.configs import (
    ErrorDiagnosisConfig,  # noqa: F401,E402
    ExplainabilityConfig,  # noqa: F401,E402
    LatencyAttributionConfig,  # noqa: F401,E402
    ObservabilityConfig,  # noqa: F401,E402
)

# PEP 484 명시적 재노출 — 위 33개 Harness Config는 gates/gate_x/configs.py가 원본 정의처이고
# 여기서는 재노출만 하지만(__all__ 정의 시점엔 아직 import되지 않아 위 목록에 못 실림),
# `from agent_evaluator.decorators import InstructionConfig, ...`가 문서화된 공개 API이므로
# __all__에 추가해 정적 분석기가 "private import"로 오판하지 않도록 한다.
__all__.extend([
    # Gate A
    "ContextRetentionConfig", "GoalAlignmentConfig", "InstructionConfig",
    "KnowledgeRetentionConfig", "PlanConfig", "SubtaskConfig",
    # Gate B
    "ContextWindowConfig", "DeadlockConfig", "LoopDetectionConfig",
    "ScopeConfig", "StateConsistencyConfig", "ToolParameterSafetyConfig",
    # Gate C
    "FaultToleranceConfig", "GracefulDegradationConfig", "IdempotencyConfig",
    "ReproducibilityConfig", "RetryConsistencyConfig",
    # Gate D
    "CostPredictabilityConfig", "EfficiencyConfig", "ResourceBudgetConfig",
    "SLAConfig", "TTFTVariabilityConfig",
    # Gate E
    "ComplianceConfig", "ThreatResponseConfig", "ThreatSeverityConfig",
    # Gate F
    "AgentRoleConfig", "ConflictResolutionConfig", "ConsensusConfig", "PropagationConfig",
    # Gate G
    "ErrorDiagnosisConfig", "ExplainabilityConfig", "LatencyAttributionConfig", "ObservabilityConfig",
])

# ---------------------------------------------------------------------------
# EvalMetadata — 튜플 반환 프로토콜
# ---------------------------------------------------------------------------

@dataclass
class EvalMetadata:
    """데코레이터가 자동 계산할 수 없는 필드를 함수 내부에서 주입하는 컨테이너.

    함수가 ``(response_or_raw, EvalMetadata(...))`` 튜플을 반환하면
    데코레이터가 메타데이터를 분리한 뒤, ``response_or_raw`` 만 호출자에게 반환한다.

    ``None`` 으로 남긴 필드는 자동 계산값을 유지한다.

    Example::

        @agent_eval(monitor, task_type="tool_use")
        def lc_agent(question, ground_truth=""):
            result = executor.invoke({"input": question})
            return result["output"], EvalMetadata(
                attempts=3,
                framework="langchain",
                expected_tools=["search", "calculator"],
                chain_steps=[
                    {"name": s[0].tool, "success": True, "execution_time": 0.0}
                    for s in result.get("intermediate_steps", [])
                ],
            )
    """

    attempts: int | None = None                             # None = 자동 계산 유지 (기본 1)
    framework: str | None = None                            # None = decorator 파라미터 유지
    expected_tools: list[str] | None = None
    tool_calls: list[dict[str, Any]] | None = None         # None = 자동 추출 유지
    agent_interactions: list[dict[str, Any]] | None = None # CrewAI 멀티에이전트
    chain_steps: list[dict[str, Any]] | None = None        # LangChain 체인 단계
    graph_traversal: dict[str, Any] | None = None          # LangGraph 그래프 경로
    state_transitions: list[dict[str, Any]] | None = None  # LangGraph 상태 전이
    completion_score: float | None = None                   # None = 자동 계산 유지
    accuracy_score: float | None = None                     # None = 자동 계산 유지
    partial_reason: str | None = None
    # Gap J: 비표준 LLM (Mistral 이외) 토큰 수 직접 주입 + 동적 모델명
    tokens_used: dict[str, int] | None = None               # {"input": n, "output": n, "total": n}
    model_name: str | None = None                           # None = decorator 파라미터 유지
    # Gap P: 평가 시점에 context / ground_truth 를 동적으로 재정의
    context: str | None = None                              # None = _resolve_args 값 유지
    ground_truth: str | None = None                         # None = _resolve_args 값 유지
    # Gap AB: AutoGen conversation_turns 주입
    conversation_turns: list[dict[str, Any]] | None = None
    # Gap AC: 사전 계산된 LLM Judge 결과 주입
    llm_judge: dict[str, Any] | None = None
    # Gap AE: 사용자 정의 자유 형식 메타데이터 — TaskResult.extra 에 저장
    extra: dict[str, Any] | None = None                     # {"intent": "search", "source": "api", ...}
    # Gap AN: 오류 목록 직접 주입
    errors: list[str] | None = None
    # Gap AO: 실행 시간 직접 주입 (자동 측정값 재정의)
    execution_time: float | None = None


# ---------------------------------------------------------------------------
# TurnMetadata — conversation_eval turn별 메타데이터 주입 프로토콜
# ---------------------------------------------------------------------------

@dataclass
class TurnMetadata:
    """``@conversation_eval`` 로 감싼 함수가 turn별 메타데이터를 주입하는 컨테이너.

    함수가 ``(response_str, TurnMetadata(...))`` 튜플을 반환하면 데코레이터가
    메타데이터를 분리해 ``ConversationSession.turn()`` 의 ``metadata`` 에 전달한다.
    호출자에게는 ``response_str`` 만 반환된다.

    ``None`` 으로 남긴 필드는 자동 측정값(latency)을 유지하거나 저장하지 않는다.

    Example::

        @conversation_eval(monitor, session_id_arg="sid")
        def chat(question: str, sid: str = "default") -> str:
            result = llm.predict_with_metadata(question)
            return result["text"], TurnMetadata(
                model="gpt-5-nano",
                tokens={"input": result["input_tokens"], "output": result["output_tokens"]},
                tool_calls=result.get("tool_calls"),
            )
    """

    model: str | None = None
    tokens: dict[str, int] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    latency: float | None = None      # None = perf_counter 자동 측정값 사용
    ground_truth: str | None = None   # Gap AP: turn별 ground_truth 직접 주입
    extra: dict[str, Any] | None = None
    participant_id: str | None = None  # A3: 참여자 ID 직접 주입


def _split_turn_raw(raw: Any) -> tuple[Any, TurnMetadata | None]:
    """(raw_response, TurnMetadata | None) 으로 분리."""
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], TurnMetadata):
        return raw[0], raw[1]
    return raw, None


# ---------------------------------------------------------------------------
# ContextVar eval_context — 반환값 타입 변경 없이 메타데이터 주입
# ---------------------------------------------------------------------------

@dataclass
class _EvalContext:
    """스레드 로컬 평가 컨텍스트. ``get_eval_ctx()`` 로 접근.

    ``EvalMetadata`` 와 동일한 필드를 가지나, 반환값 타입을 바꾸고 싶지 않을 때
    함수 본문에서 직접 속성을 수정하는 방식으로 사용한다.

    Example::

        @agent_eval(monitor, task_type="tool_use")
        def my_agent(question, ground_truth=""):
            result = executor.invoke({"input": question})
            ctx = get_eval_ctx()
            if ctx:
                ctx.framework = "langchain"
                ctx.attempts = retry_counter
            return result["output"]   # 반환값 타입 변경 없음
    """

    attempts: int | None = None                             # None = 자동 계산 유지
    framework: str | None = None                            # None = decorator 파라미터 유지
    expected_tools: list[str] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    agent_interactions: list[dict[str, Any]] | None = None
    chain_steps: list[dict[str, Any]] | None = None
    graph_traversal: dict[str, Any] | None = None
    state_transitions: list[dict[str, Any]] | None = None
    completion_score: float | None = None
    accuracy_score: float | None = None
    partial_reason: str | None = None
    tokens_used: dict[str, int] | None = None               # Gap J: 비표준 LLM 토큰 주입
    model_name: str | None = None                           # Gap J: 동적 모델명 주입
    context: str | None = None                              # Gap P: RAG context 동적 재정의
    ground_truth: str | None = None                         # Gap P: 정답 동적 재정의
    conversation_turns: list[dict[str, Any]] | None = None  # Gap AB: AutoGen turns 주입
    llm_judge: dict[str, Any] | None = None                 # Gap AC: LLM Judge 결과 주입
    extra: dict[str, Any] | None = None                     # Gap AE: 사용자 정의 메타데이터
    errors: list[str] | None = None                         # Gap AN: 오류 목록 직접 주입
    execution_time: float | None = None                     # Gap AO: 실행 시간 직접 주입
    _active: bool = field(default=False, repr=False)


# Python 3.7+ contextvars.ContextVar — asyncio.create_task() 등 동시 코루틴에서
# 각 태스크가 독립된 컨텍스트 복사본을 가지므로 threading.local 의 ctx 충돌이 없다.
_eval_ctx_var: contextvars.ContextVar[_EvalContext | None] = contextvars.ContextVar(
    "_eval_ctx", default=None
)

# A4: eval_context 중첩 깊이 추적 — contextvars.Token 기반으로 nested 지원
_NEST_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar("_nest_depth", default=0)
MAX_NESTING_DEPTH: int = 10  # G2: 데코레이터 중첩 경고 임계값

# 항목 F: 이중 데코레이터 스택 감지 — agent_eval wrapper 진입 여부 추적
_eval_active: contextvars.ContextVar[bool] = contextvars.ContextVar("_eval_active", default=False)


# 메서드에 적용 시 self/cls 를 question 으로 오탐하지 않도록 제외
_SKIP_PARAMS: frozenset = frozenset({"self", "cls"})


def get_eval_ctx() -> _EvalContext | None:
    """현재 실행 컨텍스트의 평가 컨텍스트를 반환.

    ``@agent_eval`` 데코레이터로 감싼 함수 본문 내에서만 non-None 값을 반환한다.
    데코레이터 외부에서 호출하면 ``None`` 을 반환한다.
    asyncio 환경에서 동시 코루틴이 실행되어도 각 태스크가 독립된 컨텍스트를 갖는다.

    Returns:
        :class:`_EvalContext` 인스턴스 (데코레이터 실행 중) 또는 ``None``.

    Example::

        @agent_eval(monitor, task_type="tool_use")
        def my_agent(question, ground_truth=""):
            result = executor.invoke({"input": question})
            ctx = get_eval_ctx()
            if ctx:
                ctx.framework = "langchain"
                ctx.chain_steps = parse_steps(result)
            return result["output"]
    """
    ctx = _eval_ctx_var.get(None)
    return ctx if (ctx is not None and ctx._active) else None


def _push_ctx() -> tuple[_EvalContext, contextvars.Token[_EvalContext | None]]:
    """새 컨텍스트를 현재 실행 컨텍스트에 설치하고 (ctx, token) 을 반환.

    반환된 token 을 ``_pop_ctx(token)`` 에 전달해야 컨텍스트가 정확히 복원된다.
    """
    ctx = _EvalContext(_active=True)
    token = _eval_ctx_var.set(ctx)
    return ctx, token


def _pop_ctx(token: contextvars.Token) -> None:
    """``_push_ctx`` 가 반환한 token 으로 컨텍스트 변수를 이전 값으로 복원."""
    _eval_ctx_var.reset(token)


# ---------------------------------------------------------------------------
# 내부 헬퍼 — 반환값 처리
# ---------------------------------------------------------------------------

def _extract_response(raw: Any) -> str:
    """반환값을 response 문자열로 변환."""
    if raw is None:
        return ""

    # (response, EvalMetadata) 튜플이면 첫 번째 요소 기준
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], EvalMetadata):
        return _extract_response(raw[0])
    # 위 isinstance 체인이 아래 raw 사용처에도 tuple[...] 잔여 타입을 좁혀버리는
    # Pylance narrowing 오탐을 방지 (raw는 실제로는 여전히 임의의 응답 객체)
    raw = cast(Any, raw)

    # OpenAI ChatCompletion (openai>=1.0)
    if hasattr(raw, "choices"):
        try:
            content = raw.choices[0].message.content
            return content if content is not None else ""
        except (AttributeError, IndexError):
            pass

    # Anthropic Message (anthropic>=0.20)
    if _is_anthropic_response(raw):
        try:
            content = raw.content
            if content:
                # TextBlock: .text 속성 / 기타 블록: str 변환
                first = content[0]
                return str(getattr(first, "text", first))
        except (AttributeError, IndexError):
            pass

    # Cohere (cohere>=5.0) — text 속성 직접 추출
    if _is_cohere_response(raw):
        try:
            text = getattr(raw, "text", None)
            if text is not None:
                return str(text)
            # Cohere v5 message 구조 (fallback)
            message = getattr(raw, "message", None)
            if message is not None:
                content = getattr(message, "content", None)
                if content and hasattr(content[0], "text"):
                    return str(content[0].text)
        except (AttributeError, IndexError):
            pass

    # Google Gemini (google-generativeai / google-genai)
    if _is_gemini_response(raw):
        try:
            candidates = raw.candidates
            if candidates:
                parts = candidates[0].content.parts
                if parts:
                    return str(getattr(parts[0], "text", parts[0]))
        except (AttributeError, IndexError):
            pass

    # LangChain BaseMessage
    if hasattr(raw, "content") and not isinstance(raw, type):
        content = raw.content
        return str(content) if content is not None else ""

    # dict 기반 응답 (LangChain invoke / agent executor 결과)
    if isinstance(raw, dict):
        for key in ("answer", "output", "result", "text", "response", "content"):
            if key in raw and raw[key] is not None:
                return str(raw[key])
        return str(raw)

    return str(raw)


def _is_openai_response(raw: Any) -> bool:
    """OpenAI API 응답 객체 여부 판별."""
    return (
        raw is not None
        and hasattr(raw, "choices")
        and hasattr(raw, "usage")
    )


def _is_anthropic_response(raw: Any) -> bool:
    """Anthropic SDK ``anthropic.types.Message`` 응답 객체 여부 판별.

    OpenAI 응답과 구별하기 위해 ``stop_reason`` 속성을 추가로 확인한다.
    (OpenAI 에는 없는 필드)
    """
    return (
        raw is not None
        and hasattr(raw, "content")
        and hasattr(raw, "usage")
        and hasattr(raw, "stop_reason")
        and not hasattr(raw, "choices")  # OpenAI 와 구별
    )


def _extract_anthropic_tokens(raw: Any) -> dict[str, int] | None:
    """Anthropic SDK 응답에서 토큰 수를 ``{"input": n, "output": n, "total": n}`` 형식으로 추출.

    추출 실패 시 ``None`` 을 반환한다.
    """
    try:
        usage = raw.usage
        inp = int(getattr(usage, "input_tokens", 0) or 0)
        out = int(getattr(usage, "output_tokens", 0) or 0)
        if inp == 0 and out == 0:
            return None
        return {"input": inp, "output": out, "total": inp + out}
    except Exception:
        return None


def _is_gemini_response(raw: Any) -> bool:
    """Google Gemini SDK (``google-generativeai`` / ``google-genai``) 응답 객체 여부 판별.

    ``candidates`` + ``usage_metadata`` 속성 조합으로 식별한다.
    """
    return (
        raw is not None
        and hasattr(raw, "candidates")
        and hasattr(raw, "usage_metadata")
    )


def _extract_gemini_tokens(raw: Any) -> dict[str, int] | None:
    """Gemini SDK 응답에서 토큰 수를 ``{"input": n, "output": n, "total": n}`` 형식으로 추출.

    ``usage_metadata.prompt_token_count`` / ``candidates_token_count`` 를 사용한다.
    추출 실패 시 ``None`` 을 반환한다.
    """
    try:
        meta = raw.usage_metadata
        inp = int(getattr(meta, "prompt_token_count", 0) or 0)
        out = int(getattr(meta, "candidates_token_count", 0) or 0)
        if inp == 0 and out == 0:
            return None
        return {"input": inp, "output": out, "total": inp + out}
    except Exception:
        return None


def _is_cohere_response(raw: Any) -> bool:
    """Cohere SDK v5+ (``cohere>=5.0``) 응답 객체 여부 판별.

    ``meta.tokens`` 속성 조합으로 식별한다. OpenAI/Mistral 응답과 구별하기 위해
    ``choices`` 속성이 없음을 추가로 확인한다.
    C1: streaming response도 포함 — ``finish_reason`` 속성으로 감지.
    """
    if raw is None:
        return False
    # 비스트리밍: meta.tokens 속성
    if (
        hasattr(raw, "meta")
        and hasattr(getattr(raw, "meta", None), "tokens")
        and not hasattr(raw, "choices")
    ):
        return True
    # C1: 스트리밍 응답 — finish_reason 속성으로 감지 (choices는 없음)
    if hasattr(raw, "finish_reason") and not hasattr(raw, "choices"):
        return True
    return False


def _extract_cohere_tokens(raw: Any) -> dict[str, int] | None:
    """Cohere SDK v5+ 응답에서 토큰 수를 ``{"input": n, "output": n, "total": n}`` 형식으로 추출.

    ``meta.tokens.input_tokens`` / ``output_tokens`` 를 사용한다.
    추출 실패 시 ``None`` 을 반환한다.
    """
    try:
        tokens = raw.meta.tokens
        inp = int(getattr(tokens, "input_tokens", 0) or 0)
        out = int(getattr(tokens, "output_tokens", 0) or 0)
        if inp == 0 and out == 0:
            return None
        return {"input": inp, "output": out, "total": inp + out}
    except Exception:
        return None


def _is_langchain_response(raw: Any) -> bool:
    """LangChain Agent Executor 결과 딕셔너리 여부 판별."""
    return isinstance(raw, dict) and "intermediate_steps" in raw


def _split_raw(raw: Any) -> tuple[Any, EvalMetadata | None]:
    """(raw_result, EvalMetadata | None) 으로 분리."""
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], EvalMetadata):
        return raw[0], raw[1]
    return raw, None


# ---------------------------------------------------------------------------
# Task 4: TaskType Enum 정규화 헬퍼
# ---------------------------------------------------------------------------

def _normalize_task_type(task_type: Any) -> str:
    """TaskType Enum 또는 문자열을 문자열로 정규화.

    ``TaskType.QA`` → ``"qa"``, ``"qa"`` → ``"qa"``
    IDE 자동완성을 지원하며 런타임에서도 안전하게 동작한다.
    """
    if hasattr(task_type, "value"):  # Enum 인스턴스
        return str(task_type.value)
    return str(task_type) if task_type is not None else "qa"


# ---------------------------------------------------------------------------
# Task 1: 프레임워크 어댑터 — 반환값에서 메타데이터 자동 추출
# ---------------------------------------------------------------------------

def _extract_langchain_metadata(raw: Any) -> EvalMetadata | None:
    """LangChain 결과에서 메타데이터 자동 추출 — 두 가지 반환 형태를 지원한다.

    1. ``AgentExecutor.invoke()`` 결과 dict — ``intermediate_steps`` → ``tool_calls`` + ``chain_steps``.
    2. LCEL 툴콜링 직접 반환 ``AIMessage`` (``model.bind_tools(...).invoke(...)``) —
       ``AgentExecutor`` 래핑도 ``LangGraph``의 ``{"messages": [...]}`` 딕셔너리도
       거치지 않는, 현재 LangChain이 권장하는 가장 흔한 패턴. ``.tool_calls`` 속성에서
       직접 추출한다.

    두 경우 모두 ``usage_metadata`` / ``response_metadata.token_usage`` 에서
    토큰 사용량을 추출한다.
    """
    if isinstance(raw, dict) and "intermediate_steps" in raw:
        return _extract_langchain_agent_executor_metadata(raw)
    if not isinstance(raw, dict) and hasattr(raw, "tool_calls"):
        return _extract_langchain_ai_message_metadata(raw)
    return None


def _extract_langchain_agent_executor_metadata(raw: dict[str, Any]) -> EvalMetadata | None:
    """``AgentExecutor.invoke()`` 결과 dict (``intermediate_steps`` 포함) 전용 추출 경로."""
    steps = raw.get("intermediate_steps") or []
    tool_calls: list[dict[str, Any]] = []
    chain_steps: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, (list, tuple)) or len(step) < 2:
            continue
        action, observation = step[0], step[1]
        tool_name = (
            getattr(action, "tool", None)
            or getattr(action, "tool_name", None)
            or "unknown"
        )
        tool_input = getattr(action, "tool_input", {})
        if not isinstance(tool_input, dict):
            tool_input = {"input": str(tool_input)}
        tool_calls.append({
            "tool_name": str(tool_name),
            "input": tool_input,
            "output": str(observation)[:500],
            "success": True,
        })
        chain_steps.append({
            "name": str(tool_name),
            "input": tool_input,
            "output": str(observation)[:500],
            "success": True,
            "execution_time": 0.0,
        })
    if not tool_calls:
        return None

    # LangChain 0.2+: usage_metadata 또는 response_metadata.token_usage 에서 토큰 추출
    tokens_used: dict[str, int] | None = None
    try:
        usage_meta = raw.get("usage_metadata")
        if usage_meta is None:
            usage_meta = (raw.get("response_metadata") or {}).get("token_usage")
        if isinstance(usage_meta, dict):
            inp = int(usage_meta.get("input_tokens") or usage_meta.get("prompt_tokens") or 0)
            out = int(usage_meta.get("output_tokens") or usage_meta.get("completion_tokens") or 0)
            if inp or out:
                tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass

    return EvalMetadata(
        tool_calls=tool_calls,
        chain_steps=chain_steps,
        tokens_used=tokens_used,
        framework="langchain",
    )


def _extract_langchain_ai_message_metadata(raw: Any) -> EvalMetadata | None:
    """LCEL 툴콜링(``model.bind_tools(...).invoke(...)``)이 직접 반환하는 ``AIMessage``
    전용 추출 경로 — ``AgentExecutor``도 ``LangGraph``의 메시지 리스트 dict도 아닌,
    도구 바인딩 모델을 직접 호출해서 나오는 가장 흔한 최신 패턴이다.

    ``AIMessage.tool_calls``는 ``ToolCall`` TypedDict(``{"name", "args", "id"}``)의
    리스트이므로 dict 접근을 우선하고, 커스텀 객체 형태를 대비해 getattr로 폴백한다.
    """
    raw_tool_calls = getattr(raw, "tool_calls", None) or []
    if not raw_tool_calls:
        return None

    tool_calls: list[dict[str, Any]] = []
    for tc in raw_tool_calls:
        if isinstance(tc, dict):
            name = tc.get("name", "unknown")
            args = tc.get("args", {})
            tc_id = tc.get("id", "")
        else:
            name = getattr(tc, "name", "unknown")
            args = getattr(tc, "args", {})
            tc_id = getattr(tc, "id", "")
        tool_calls.append({
            "tool_name": str(name),
            "input": args if isinstance(args, dict) else {"input": str(args)},
            "tool_call_id": str(tc_id or ""),
            "success": True,
        })
    if not tool_calls:
        return None

    # LangChain 0.2+: AIMessage.usage_metadata 속성(dict) 우선, 없으면
    # response_metadata.token_usage 로 폴백 (AgentExecutor 경로와 동일한 필드명 규칙)
    tokens_used: dict[str, int] | None = None
    try:
        usage_meta = getattr(raw, "usage_metadata", None)
        if usage_meta is None:
            usage_meta = (getattr(raw, "response_metadata", None) or {}).get("token_usage")
        if isinstance(usage_meta, dict):
            inp = int(usage_meta.get("input_tokens") or usage_meta.get("prompt_tokens") or 0)
            out = int(usage_meta.get("output_tokens") or usage_meta.get("completion_tokens") or 0)
            if inp or out:
                tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass

    return EvalMetadata(
        tool_calls=tool_calls,
        tokens_used=tokens_used,
        framework="langchain",
    )


def _step_time(msg: Any, idx: int, messages: list[Any]) -> float:
    """메시지 타임스탬프에서 인접 메시지 간 경과 시간(초)을 추정한다 (F1).

    LangGraph 메시지 객체에 ``response_metadata["created_at"]`` 또는
    ``additional_kwargs["created_at"]`` ISO-8601 타임스탬프가 있으면
    앞 메시지와의 차이를 반환한다. 없으면 0.0 반환.
    """
    import re as _re
    _ISO_RE = _re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")

    def _extract_ts(m: Any) -> float | None:
        for attr in ("response_metadata", "additional_kwargs"):
            meta = getattr(m, attr, None) or {}
            if isinstance(meta, dict):
                raw = meta.get("created_at") or meta.get("timestamp")
                if raw and isinstance(raw, str) and _ISO_RE.search(raw):
                    try:
                        from datetime import datetime as _dt
                        return _dt.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        pass
        return None

    if idx == 0:
        return 0.0
    ts_curr = _extract_ts(msg)
    ts_prev = _extract_ts(messages[idx - 1])
    if ts_curr is not None and ts_prev is not None and ts_curr > ts_prev:
        return round(ts_curr - ts_prev, 4)
    return 0.0


def _extract_langgraph_metadata(raw: Any) -> EvalMetadata | None:
    """LangGraph invoke 결과 dict에서 메타데이터 자동 추출.

    C2: ToolMessage/AIMessage → chain_steps, ``__metadata__`` → state_transitions 지원.
    ``messages`` 리스트 → ``state_transitions`` + ``graph_traversal`` + ``tool_calls`` 변환.
    """
    if not isinstance(raw, dict):
        return None
    messages = raw.get("messages") or []

    # C2: __metadata__ 에서 노드 실행 정보를 state_transitions 로 추출
    raw_metadata = raw.get("__metadata__") or {}

    if not messages and not raw_metadata:
        return None

    state_transitions: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    chain_steps: list[dict[str, Any]] = []
    nodes_visited: list[str] = []

    # C2: __metadata__ 처리 (LangGraph checkpoint metadata)
    if isinstance(raw_metadata, dict):
        for key, val in raw_metadata.items():
            entry: dict[str, Any] = {"node": key, "source": "__metadata__"}
            if isinstance(val, dict):
                entry["metadata"] = {k: str(v)[:200] for k, v in val.items()}
            else:
                entry["value"] = str(val)[:200]
            state_transitions.append(entry)

    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content", "")
        nodes_visited.append(msg_type)
        state_transitions.append({
            "step": i,
            "node": msg_type,
            "content": str(content)[:300] if content else "",
        })

        # C2: ToolMessage → chain_steps (도구 실행 결과)
        if "ToolMessage" in msg_type:
            chain_steps.append({
                "name": getattr(msg, "name", "tool_result"),
                "output": str(content)[:500] if content else "",
                "success": True,
                "execution_time": _step_time(msg, i, messages),
                "tool_call_id": str(getattr(msg, "tool_call_id", "")),
                "type": "tool_result",
            })
        # C2: AIMessage → chain_steps (모델 추론 단계)
        elif "AIMessage" in msg_type and content:
            chain_steps.append({
                "name": "ai_response",
                "output": str(content)[:500],
                "success": True,
                "execution_time": _step_time(msg, i, messages),
                "type": "ai_message",
            })

        # AIMessage의 tool_calls 추출
        raw_tcs = getattr(msg, "tool_calls", None)
        if raw_tcs:
            for tc in raw_tcs:
                name = tc.get("name", "unknown") if isinstance(tc, dict) else getattr(tc, "name", "unknown")
                args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                tool_calls.append({"tool_name": str(name), "input": args, "success": True})

    graph_traversal = {
        "nodes_visited": list(dict.fromkeys(nodes_visited)),  # 순서 유지 중복 제거
        "total_steps": len(messages),
    }

    # F1: 토큰 추출 — AIMessage의 usage_metadata(LangChain 0.2+) 또는 response_metadata
    _tokens_used: dict[str, Any] | None = None
    _total_input = 0
    _total_output = 0
    for _msg in messages:
        _um = getattr(_msg, "usage_metadata", None)
        if _um and isinstance(_um, dict):
            _total_input += int(_um.get("input_tokens", 0) or _um.get("prompt_tokens", 0))
            _total_output += int(_um.get("output_tokens", 0) or _um.get("completion_tokens", 0))
        else:
            # response_metadata.token_usage (구버전 LangChain)
            _rm = getattr(_msg, "response_metadata", None) or {}
            _tu = (_rm.get("token_usage") if isinstance(_rm, dict) else None) or {}
            if _tu and isinstance(_tu, dict):
                _total_input += int(_tu.get("prompt_tokens", 0))
                _total_output += int(_tu.get("completion_tokens", 0))
    if _total_input > 0 or _total_output > 0:
        _tokens_used = {
            "input": _total_input,
            "output": _total_output,
            "total": _total_input + _total_output,
        }

    return EvalMetadata(
        state_transitions=state_transitions,
        graph_traversal=graph_traversal,
        tool_calls=tool_calls if tool_calls else None,
        chain_steps=chain_steps if chain_steps else None,
        framework="langgraph",
        tokens_used=_tokens_used,
    )


def _extract_crewai_metadata(raw: Any) -> EvalMetadata | None:
    """CrewAI kickoff 결과에서 메타데이터 자동 추출.

    ``CrewOutput.tasks_output`` → ``agent_interactions`` 변환.
    CrewAI 2.0+: ``output_pydantic`` / ``output_format`` / ``pydantic`` 필드 지원 (C3, E1).
    """
    tasks_output = getattr(raw, "tasks_output", None)
    if tasks_output is None and isinstance(raw, dict):
        tasks_output = raw.get("tasks_output")

    # C3/E1: CrewAI 2.0+ — output_pydantic / pydantic (Pydantic 모델) 또는 output_format 필드 지원
    output_pydantic = getattr(raw, "output_pydantic", None) or getattr(raw, "pydantic", None)
    pydantic_result: str | None = None
    if output_pydantic is not None:
        try:
            pydantic_result = output_pydantic.model_dump_json() if hasattr(output_pydantic, "model_dump_json") else str(output_pydantic)
        except Exception:
            pydantic_result = str(output_pydantic)

    # C3: output_format 필드 (CrewAI v2.x 구조화 출력)
    output_format = getattr(raw, "output_format", None)
    output_format_str: str | None = None
    if output_format is not None:
        try:
            output_format_str = str(output_format)
        except Exception:
            pass

    if not tasks_output:
        fallback_interactions: list[dict[str, Any]] = []
        if pydantic_result is not None:
            fallback_interactions.append({
                "from_agent": "crew",
                "to_agent": "coordinator",
                "type": "task_completion",
                "success": True,
                "context": "output_pydantic",
                "result": pydantic_result[:300],
            })
        if output_format_str is not None:
            fallback_interactions.append({
                "from_agent": "crew",
                "to_agent": "coordinator",
                "type": "output_format",
                "success": True,
                "context": "output_format",
                "result": output_format_str[:300],
            })
        if fallback_interactions:
            return EvalMetadata(agent_interactions=fallback_interactions, framework="crewai")
        return None

    agent_interactions: list[dict[str, Any]] = []
    for task_out in tasks_output:
        agent_name = getattr(task_out, "agent", "unknown")
        description = getattr(task_out, "description", "")
        result_raw = getattr(task_out, "raw", None) or str(task_out)
        # C3: output_format per-task (CrewAI v2.x)
        task_format = getattr(task_out, "output_format", None)
        interaction: dict[str, Any] = {
            "from_agent": str(agent_name),
            "to_agent": "coordinator",
            "type": "task_completion",
            "success": True,
            "context": str(description)[:300],
            "result": str(result_raw)[:300],
        }
        if task_format is not None:
            interaction["output_format"] = str(task_format)[:100]
        agent_interactions.append(interaction)
    if pydantic_result is not None:
        agent_interactions.append({
            "from_agent": "crew",
            "to_agent": "coordinator",
            "type": "pydantic_output",
            "success": True,
            "context": "output_pydantic",
            "result": pydantic_result[:300],
        })
    if output_format_str is not None:
        agent_interactions.append({
            "from_agent": "crew",
            "to_agent": "coordinator",
            "type": "output_format",
            "success": True,
            "context": "output_format",
            "result": output_format_str[:300],
        })
    if not agent_interactions:
        return None

    # C1: CrewAI 토큰 사용량 추출 (token_usage / usage_metrics 속성)
    tokens_used: dict[str, int] | None = None
    try:
        _token_src = (
            getattr(raw, "token_usage", None)
            or getattr(raw, "usage_metrics", None)
            or (raw.get("token_usage") if isinstance(raw, dict) else None)
            or (raw.get("usage_metrics") if isinstance(raw, dict) else None)
        )
        if isinstance(_token_src, dict):
            inp = int(_token_src.get("prompt_tokens", 0) or _token_src.get("input_tokens", 0) or 0)
            out = int(_token_src.get("completion_tokens", 0) or _token_src.get("output_tokens", 0) or 0)
            if inp or out:
                tokens_used = {"input": inp, "output": out, "total": inp + out}
        elif _token_src is not None and hasattr(_token_src, "prompt_tokens"):
            inp = int(getattr(_token_src, "prompt_tokens", 0) or 0)
            out = int(getattr(_token_src, "completion_tokens", 0) or 0)
            if inp or out:
                tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass

    # CrewAI tool_calls — tasks_output 의 used_tools / tool_usage 필드에서 추출
    tool_calls: list[dict[str, Any]] = []
    for _task_out in tasks_output:
        # CrewAI TaskOutput.used_tools (list of tool names or dicts)
        _used = getattr(_task_out, "used_tools", None) or []
        for _ut in _used:
            if isinstance(_ut, str):
                tool_calls.append({"tool_name": _ut, "success": True})
            elif isinstance(_ut, dict):
                tool_calls.append({
                    "tool_name": str(_ut.get("name", "unknown")),
                    "input": _ut.get("input", {}),
                    "success": not bool(_ut.get("error")),
                })
            elif hasattr(_ut, "name"):
                tool_calls.append({"tool_name": str(getattr(_ut, "name", "unknown")), "success": True})
        # CrewAI 2.x: tool_usage 필드
        _tool_usage = getattr(_task_out, "tool_usage", None)
        if isinstance(_tool_usage, list):
            for _tu in _tool_usage:
                if isinstance(_tu, str):
                    tool_calls.append({"tool_name": _tu, "success": True})
                elif hasattr(_tu, "tool_name") or hasattr(_tu, "name"):
                    tool_calls.append({
                        "tool_name": str(getattr(_tu, "tool_name", getattr(_tu, "name", "unknown"))),
                        "success": True,
                    })

    # CrewAI state_transitions — 태스크 실행 순서를 상태 전이 시퀀스로 변환
    state_transitions: list[dict[str, Any]] = []
    for i, _task_out in enumerate(tasks_output):
        _agent = str(getattr(_task_out, "agent", "unknown"))
        _desc = str(getattr(_task_out, "description", ""))[:200]
        _raw = str(getattr(_task_out, "raw", "") or "")[:100]
        state_transitions.append({
            "step": i,
            "node": _agent,
            "type": "task_completion",
            "description": _desc,
            "output_summary": _raw,
            "success": True,
        })

    return EvalMetadata(
        agent_interactions=agent_interactions,
        tool_calls=tool_calls if tool_calls else None,
        state_transitions=state_transitions if state_transitions else None,
        tokens_used=tokens_used,
        framework="crewai",
    )


def _extract_autogen_metadata(raw: Any) -> EvalMetadata | None:
    """AutoGen 결과에서 메타데이터 자동 추출.

    ``messages`` / ``chat_history`` → ``conversation_turns`` 변환.
    AutoGen 0.4+ ``TaskResult.messages`` 도 지원한다.
    ``cost`` / ``usage_summary`` 에서 토큰 사용량 추출 시도.
    """
    messages = None
    if hasattr(raw, "messages"):
        messages = raw.messages
    elif isinstance(raw, dict):
        messages = raw.get("messages") or raw.get("chat_history")
    # isinstance(raw, dict) 분기가 아래 raw 사용처에도 dict[...] 잔여 타입을
    # 좁혀버리는 Pylance narrowing 오탐을 방지 (raw는 임의의 응답 객체일 수 있음)
    raw = cast(Any, raw)
    # autogen-agentchat 0.4+ TaskResult
    if messages is None and hasattr(raw, "chat_result"):
        cr = raw.chat_result
        messages = getattr(cr, "chat_history", None)
    if not messages:
        return None
    conversation_turns: list[dict[str, Any]] = []
    _prev_ts: float | None = None
    for msg in messages:
        if isinstance(msg, dict):
            _ts_raw = msg.get("timestamp") or msg.get("created_at")
            _turn_time = 0.0
            if _ts_raw is not None:
                try:
                    import datetime as _dt
                    if isinstance(_ts_raw, (int, float)):
                        _ts_float = float(_ts_raw)
                    else:
                        _ts_float = _dt.datetime.fromisoformat(str(_ts_raw)).timestamp()
                    if _prev_ts is not None:
                        _turn_time = max(0.0, _ts_float - _prev_ts)
                    _prev_ts = _ts_float
                except Exception:
                    pass
            conversation_turns.append({
                "role": msg.get("role", "unknown"),
                "content": str(msg.get("content", ""))[:500],
                "name": msg.get("name", ""),
                "execution_time": _turn_time,
            })
        else:
            _ts_attr = getattr(msg, "timestamp", None) or getattr(msg, "created_at", None)
            _turn_time = 0.0
            if _ts_attr is not None:
                try:
                    import datetime as _dt
                    if isinstance(_ts_attr, (int, float)):
                        _ts_float = float(_ts_attr)
                    elif hasattr(_ts_attr, "timestamp"):
                        _ts_float = _ts_attr.timestamp()
                    else:
                        _ts_float = _dt.datetime.fromisoformat(str(_ts_attr)).timestamp()
                    if _prev_ts is not None:
                        _turn_time = max(0.0, _ts_float - _prev_ts)
                    _prev_ts = _ts_float
                except Exception:
                    pass
            conversation_turns.append({
                "role": getattr(msg, "role", type(msg).__name__),
                "content": str(getattr(msg, "content", ""))[:500],
                "name": getattr(msg, "source", getattr(msg, "name", "")),
                "execution_time": _turn_time,
            })
    if not conversation_turns:
        return None

    # AutoGen 토큰 사용량 추출 — cost 또는 usage_summary
    tokens_used: dict[str, int] | None = None
    try:
        # autogen ConversableAgent: chat_result.cost["usage_including_cached_inference"]
        cost_src = getattr(raw, "cost", None) or (
            getattr(raw, "chat_result", None) and getattr(raw.chat_result, "cost", None)
        )
        if isinstance(cost_src, dict):
            usage_block = cost_src.get("usage_including_cached_inference") or {}
            # usage_block: {"gpt-5-nano": {"prompt_tokens": N, "completion_tokens": M, ...}, "total_cost": ...}
            for _key, val in usage_block.items():
                if isinstance(val, dict) and "prompt_tokens" in val:
                    inp = int(val.get("prompt_tokens", 0))
                    out = int(val.get("completion_tokens", 0))
                    if inp or out:
                        tokens_used = {"input": inp, "output": out, "total": inp + out}
                    break
        # AutoGen 0.4+ TaskResult.usage_summary
        if tokens_used is None:
            usage_summary = getattr(raw, "usage_summary", None)
            if isinstance(usage_summary, dict):
                inp = int(usage_summary.get("prompt_tokens", 0))
                out = int(usage_summary.get("completion_tokens", 0))
                if inp or out:
                    tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass

    # Multi-agent: 서로 다른 에이전트 간 메시지 교환을 agent_interactions 로 변환
    agent_interactions: list[dict[str, Any]] = []
    for i, turn in enumerate(conversation_turns):
        _agent_name = turn.get("name", "").strip()
        _agent_role = turn.get("role", "")
        # 이름이 있고 user/system이 아닌 경우 = 에이전트 발화
        if _agent_name and _agent_name.lower() not in ("user", "system", ""):
            if i > 0:
                _prev = conversation_turns[i - 1]
                _prev_name = (_prev.get("name") or _prev.get("role") or "user").strip()
                if _prev_name != _agent_name:
                    agent_interactions.append({
                        "from_agent": str(_prev_name),
                        "to_agent": str(_agent_name),
                        "type": "message",
                        "success": True,
                        "context": str(turn.get("content", ""))[:200],
                        "execution_time": turn.get("execution_time", 0.0),
                    })

    # AutoGen state_transitions — 메시지 순서를 상태 전이 시퀀스로 변환
    state_transitions: list[dict[str, Any]] = []
    for i, turn in enumerate(conversation_turns):
        _role = turn.get("role", "unknown")
        _name = turn.get("name", "") or _role
        state_transitions.append({
            "step": i,
            "node": str(_name),
            "role": _role,
            "content": str(turn.get("content", ""))[:200],
            "execution_time": turn.get("execution_time", 0.0),
        })

    return EvalMetadata(
        conversation_turns=conversation_turns,
        agent_interactions=agent_interactions if agent_interactions else None,
        state_transitions=state_transitions if state_transitions else None,
        tokens_used=tokens_used,
        framework="autogen",
    )


def _extract_dspy_metadata(raw: Any) -> EvalMetadata | None:
    """DSPy Prediction 결과에서 메타데이터 자동 추출.

    C1: LM `.history` 전체를 순회해 multi-step chain_steps 추출 지원.
    """
    # DSPy Prediction 객체: _completions, rationale, answer, reasoning 등
    has_completions = hasattr(raw, "_completions") or hasattr(raw, "completions")
    has_dspy_fields = hasattr(raw, "answer") or hasattr(raw, "rationale") or hasattr(raw, "reasoning")
    if not (has_completions or has_dspy_fields):
        return None

    chain_steps: list[dict[str, Any]] = []
    completions = getattr(raw, "_completions", None) or getattr(raw, "completions", None)
    if completions:
        for i, comp in enumerate(completions if isinstance(completions, list) else [completions]):
            chain_steps.append({
                "name": f"completion_{i}",
                "output": str(comp)[:500],
                "success": True,
                "execution_time": 0.0,
            })

    # C1: Try to extract token usage and chain steps from DSPy LM history
    tokens_used: dict[str, int] | None = None
    try:
        import dspy  # type: ignore[import-not-found]
        lm = getattr(dspy.settings, "lm", None)
        if lm is None:
            lm = getattr(dspy.settings, "_lm", None)
        if lm and hasattr(lm, "history") and lm.history:
            history = lm.history
            # C1: Multi-step chain extraction from full history
            if len(history) > 1:
                for j, hist_entry in enumerate(history):
                    if not isinstance(hist_entry, dict):
                        continue
                    response_obj = hist_entry.get("response", {})
                    step_out = ""
                    if isinstance(response_obj, dict):
                        choices = response_obj.get("choices", [])
                        if choices and isinstance(choices, list):
                            msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                            step_out = str(msg.get("content", ""))
                    if not any(s.get("name") == f"history_{j}" for s in chain_steps):
                        chain_steps.append({
                            "name": f"history_{j}",
                            "output": step_out[:500],
                            "success": True,
                            "execution_time": 0.0,
                        })
            # Token usage from last history entry
            last = history[-1]
            usage = last.get("usage") or {}
            inp = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
            out = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
            if inp or out:
                tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass
    # F3: DSPy tool_calls — Prediction의 tool_calls 또는 actions 필드에서 추출
    tool_calls: list[dict[str, Any]] = []
    try:
        _dspy_tc = getattr(raw, "tool_calls", None) or getattr(raw, "actions", None)
        if _dspy_tc and isinstance(_dspy_tc, (list, tuple)):
            for _tc in _dspy_tc:
                if isinstance(_tc, dict):
                    tool_calls.append({
                        "tool_name": str(_tc.get("name", _tc.get("tool", "unknown"))),
                        "input": _tc.get("args", _tc.get("input", {})),
                        "success": not bool(_tc.get("error")),
                    })
                else:
                    tool_calls.append({
                        "tool_name": str(getattr(_tc, "name", getattr(_tc, "tool", "unknown"))),
                        "input": getattr(_tc, "args", getattr(_tc, "input", {})),
                        "success": True,
                    })
        # Also check history entries for tool_calls
        if not tool_calls:
            try:
                import dspy  # type: ignore[import-not-found]
                lm = getattr(dspy.settings, "lm", None) or getattr(dspy.settings, "_lm", None)
                if lm and hasattr(lm, "history") and lm.history:
                    for _h in lm.history:
                        if isinstance(_h, dict):
                            for _msg in (_h.get("messages") or []):
                                if isinstance(_msg, dict):
                                    for _tc in (_msg.get("tool_calls") or []):
                                        if isinstance(_tc, dict):
                                            fn = _tc.get("function", {})
                                            tool_calls.append({
                                                "tool_name": str(fn.get("name", "unknown")),
                                                "input": fn.get("arguments", {}),
                                                "success": True,
                                            })
            except Exception:
                pass
    except Exception:
        pass

    return EvalMetadata(
        chain_steps=chain_steps if chain_steps else None,
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="dspy",
    )


def _extract_pydanticai_metadata(raw: Any) -> EvalMetadata | None:
    """PydanticAI RunResult에서 메타데이터 자동 추출.

    C1: `.all_messages()` 기반 전체 메시지 히스토리 추출 지원.
    ToolCallPart / ToolReturnPart 세분화 chain_steps 추출.
    """
    # PydanticAI RunResult: .output(2.x)/.data(구버전), .usage(2.x property/구버전 callable),
    # .messages, .all_messages()
    if not hasattr(raw, "usage") or not (hasattr(raw, "output") or hasattr(raw, "data")):
        return None
    tokens_used: dict[str, int] | None = None
    try:
        usage = getattr(raw, "usage", None)
        if (
            callable(usage)
            and not hasattr(usage, "input_tokens")
            and not hasattr(usage, "request_tokens")
        ):
            usage = usage()
        if usage:
            inp = getattr(usage, "request_tokens", 0) or getattr(usage, "input_tokens", 0) or 0
            out = getattr(usage, "response_tokens", 0) or getattr(usage, "output_tokens", 0) or 0
            if inp or out:
                tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass
    chain_steps: list[dict[str, Any]] = []
    try:
        # C1: .all_messages() 우선 시도 — 전체 요청/응답 히스토리 포함
        msgs = None
        if hasattr(raw, "all_messages") and callable(raw.all_messages):
            try:
                msgs = raw.all_messages()
            except Exception:
                pass
        if msgs is None:
            msgs = getattr(raw, "messages", []) or []
        # hasattr()로 좁혀진 raw.all_messages()의 반환형이 object로 추론돼
        # 아래 for가 오탐되는 것을 방지 (msgs는 실제로 메시지 리스트)
        msgs = cast(Any, msgs)

        for msg in msgs:
            parts = getattr(msg, "parts", None)
            if parts:
                # C1: ToolCallPart / ToolReturnPart 세분화 처리
                for part in parts:
                    part_type = type(part).__name__
                    if "ToolCall" in part_type:
                        chain_steps.append({
                            "name": getattr(part, "tool_name", "tool_call"),
                            "content": str(getattr(part, "args", ""))[:300],
                            "success": True,
                            "execution_time": 0.0,
                            "type": "tool_call",
                        })
                    elif "ToolReturn" in part_type:
                        chain_steps.append({
                            "name": getattr(part, "tool_name", "tool_return"),
                            "content": str(getattr(part, "content", ""))[:300],
                            "success": True,
                            "execution_time": 0.0,
                            "type": "tool_return",
                        })
                    elif "Text" in part_type:
                        content_str = str(getattr(part, "content", ""))
                        if content_str.strip():
                            chain_steps.append({
                                "name": type(msg).__name__,
                                "content": content_str[:300],
                                "success": True,
                                "execution_time": 0.0,
                                "type": "text",
                            })
            else:
                chain_steps.append({
                    "name": type(msg).__name__,
                    "content": str(getattr(msg, "content", msg))[:300],
                    "success": True,
                    "execution_time": 0.0,
                })
    except Exception:
        pass
    # PydanticAI tool_calls — ToolCallPart chain_steps 에서 tool_calls 재구성
    tool_calls: list[dict[str, Any]] = []
    for _cs in chain_steps:
        if _cs.get("type") == "tool_call":
            _tc_name = _cs.get("name", "unknown")
            _tc_input = _cs.get("content", "")
            tool_calls.append({
                "tool_name": str(_tc_name),
                "input": _tc_input if isinstance(_tc_input, dict) else str(_tc_input),
                "success": _cs.get("success", True),
            })

    return EvalMetadata(
        tokens_used=tokens_used,
        chain_steps=chain_steps if chain_steps else None,
        tool_calls=tool_calls if tool_calls else None,
        framework="pydanticai",
    )


def _extract_anthropic_metadata(raw: Any) -> EvalMetadata | None:
    """Anthropic Claude Messages API 결과에서 메타데이터 자동 추출.

    ``client.messages.create(tools=[...])`` 결과의 ``content`` 블록에서
    ``tool_use`` 타입 블록을 ``tool_calls`` 로 변환하고 토큰 사용량을 추출한다.
    """
    # Anthropic Message 객체: .content (list[Block]), .usage, .model
    if not hasattr(raw, "content") or not hasattr(raw, "usage"):
        return None
    tool_calls: list[dict[str, Any]] = []
    try:
        for block in (raw.content or []):
            btype = getattr(block, "type", None)
            if btype == "tool_use":
                tool_calls.append({
                    "tool_name": getattr(block, "name", "unknown"),
                    "input": getattr(block, "input", {}),
                    "tool_use_id": getattr(block, "id", ""),
                    "success": True,
                })
    except Exception:
        pass
    tokens_used: dict[str, int] | None = None
    try:
        usage = raw.usage
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        # G1: Anthropic SDK ≥0.29 캐시 토큰 필드 추출
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        total_inp = inp + cache_creation + cache_read
        if total_inp or out:
            tokens_used = {
                "input": int(inp),
                "output": int(out),
                "total": int(total_inp + out),
                "cache_creation": int(cache_creation),
                "cache_read": int(cache_read),
            }
    except Exception:
        pass
    model_name = getattr(raw, "model", "") or ""
    if not tool_calls and not tokens_used:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="anthropic",
        extra={"model": model_name} if model_name else None,
    )


def _extract_openai_metadata(raw: Any) -> EvalMetadata | None:
    """OpenAI Chat Completions / Responses API 결과에서 메타데이터 자동 추출.

    ``client.chat.completions.create(tools=[...])`` 결과의
    ``choices[0].message.tool_calls`` 에서 도구 호출을 추출하고 토큰 사용량을 수집한다.
    Assistants API ``Run`` 객체, 그리고 2025년 3월 도입된 Responses API
    (``client.responses.create(...)``, ``response.output`` 리스트 안의
    ``function_call`` 타입 아이템 + ``response.usage.input_tokens``/``output_tokens``)
    도 지원한다 — Chat Completions와는 구조가 다른 별도 객체 타입이다.
    """
    # OpenAI ChatCompletion 객체: .choices, .usage, .model
    # Responses API Response 객체: .output (list), .usage, .model — .choices는 없음
    if (
        not hasattr(raw, "choices")
        and not hasattr(raw, "required_action")
        and not hasattr(raw, "output")
    ):
        return None
    tool_calls: list[dict[str, Any]] = []
    tokens_used: dict[str, int] | None = None

    try:
        # Chat Completions + C3: Streaming ChatCompletionChunk (choice.delta 지원)
        choices = getattr(raw, "choices", None) or []
        for choice in choices:
            # 비스트리밍: choice.message / 스트리밍: choice.delta
            msg = getattr(choice, "message", None) or getattr(choice, "delta", None)
            if msg is None:
                continue
            for tc in (getattr(msg, "tool_calls", None) or []):
                fn = getattr(tc, "function", None)
                tool_calls.append({
                    "tool_name": getattr(fn, "name", "unknown") if fn else "unknown",
                    "input": getattr(fn, "arguments", "") if fn else "",
                    "tool_call_id": getattr(tc, "id", ""),
                    "success": True,
                })
    except Exception:
        pass

    try:
        # Assistants API Run required_action
        req = getattr(raw, "required_action", None)
        if req:
            submit = getattr(req, "submit_tool_outputs", None)
            for tc in (getattr(submit, "tool_calls", None) or []) if submit else []:
                fn = getattr(tc, "function", None)
                tool_calls.append({
                    "tool_name": getattr(fn, "name", "unknown") if fn else "unknown",
                    "input": getattr(fn, "arguments", "") if fn else "",
                    "tool_call_id": getattr(tc, "id", ""),
                    "success": True,
                })
    except Exception:
        pass

    try:
        # Responses API: response.output 리스트의 type="function_call" 아이템.
        # (Chat Completions/Assistants와 달리 tool_calls가 message 안이 아니라
        # 최상위 output 배열에 message 아이템과 나란히 들어있다)
        for item in (getattr(raw, "output", None) or []):
            if getattr(item, "type", None) != "function_call":
                continue
            tool_calls.append({
                "tool_name": getattr(item, "name", "unknown"),
                "input": getattr(item, "arguments", ""),
                "tool_call_id": getattr(item, "call_id", "") or getattr(item, "id", ""),
                "success": True,
            })
    except Exception:
        pass

    try:
        usage = getattr(raw, "usage", None)
        if usage:
            # Chat Completions/Assistants: prompt_tokens/completion_tokens
            # Responses API: input_tokens/output_tokens
            inp = getattr(usage, "prompt_tokens", None)
            if inp is None:
                inp = getattr(usage, "input_tokens", 0)
            out = getattr(usage, "completion_tokens", None)
            if out is None:
                out = getattr(usage, "output_tokens", 0)
            inp = inp or 0
            out = out or 0
            if inp or out:
                tokens_used = {"input": int(inp), "output": int(out), "total": int(inp + out)}
    except Exception:
        pass

    model_name = getattr(raw, "model", "") or ""
    if not tool_calls and not tokens_used:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="openai",
        extra={"model": model_name} if model_name else None,
    )


def _extract_gemini_metadata(raw: Any) -> EvalMetadata | None:
    """Google Gemini API 결과에서 메타데이터 자동 추출.

    ``model.generate_content(tools=[...])`` 결과의 ``candidates[0].content.parts``
    에서 ``function_call`` 타입 파트를 ``tool_calls`` 로 변환하고 토큰 사용량을 추출한다.
    """
    # Gemini GenerateContentResponse: .candidates, .usage_metadata
    if not hasattr(raw, "candidates") and not hasattr(raw, "usage_metadata"):
        return None
    tool_calls: list[dict[str, Any]] = []
    try:
        for cand in (getattr(raw, "candidates", None) or []):
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    tool_calls.append({
                        "tool_name": getattr(fc, "name", "unknown"),
                        "input": dict(getattr(fc, "args", {}) or {}),
                        "success": True,
                    })
    except Exception:
        pass
    tokens_used: dict[str, int] | None = None
    try:
        um = getattr(raw, "usage_metadata", None)
        if um:
            inp = getattr(um, "prompt_token_count", 0) or 0
            out = getattr(um, "candidates_token_count", 0) or 0
            if inp or out:
                tokens_used = {"input": int(inp), "output": int(out), "total": int(inp + out)}
    except Exception:
        pass
    if not tool_calls and not tokens_used:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="gemini",
    )


def _extract_llamaindex_metadata(raw: Any) -> EvalMetadata | None:
    """Llama Index QueryEngine / Response 결과에서 메타데이터 자동 추출.

    ``query_engine.query()`` 결과의 ``source_nodes`` 에서 검색 소스를
    ``chain_steps`` 로 변환한다.
    """
    # LlamaIndex Response: .response, .source_nodes, .metadata
    if not hasattr(raw, "source_nodes") and not hasattr(raw, "response"):
        return None
    chain_steps: list[dict[str, Any]] = []
    try:
        for i, node in enumerate(getattr(raw, "source_nodes", None) or []):
            score = getattr(node, "score", None)
            text = getattr(getattr(node, "node", node), "text", "") or ""
            chain_steps.append({
                "name": f"source_node_{i}",
                "output": str(text)[:300],
                "score": float(score) if score is not None else None,
                "success": True,
                "execution_time": 0.0,
            })
    except Exception:
        pass
    # metadata에서 토큰 사용량 추출 시도
    tokens_used: dict[str, int] | None = None
    try:
        meta = getattr(raw, "metadata", {}) or {}
        token_meta = meta.get("token_usage") or meta.get("usage")
        if isinstance(token_meta, dict):
            inp = token_meta.get("prompt_tokens", 0) or token_meta.get("input_tokens", 0) or 0
            out = token_meta.get("completion_tokens", 0) or token_meta.get("output_tokens", 0) or 0
            if inp or out:
                tokens_used = {"input": int(inp), "output": int(out), "total": int(inp + out)}
    except Exception:
        pass
    # LlamaIndex tool_calls — AgentChatResponse.sources 또는 step tool_calls에서 추출
    tool_calls: list[dict[str, Any]] = []
    try:
        # AgentChatResponse: .sources 는 ToolOutput 리스트
        sources = getattr(raw, "sources", None) or []
        for src in sources:
            _tool_name = getattr(src, "tool_name", getattr(src, "tool", None))
            if _tool_name:
                tool_calls.append({
                    "tool_name": str(_tool_name),
                    "input": str(getattr(src, "raw_input", getattr(src, "input", "")))[:200],
                    "success": not bool(getattr(src, "is_error", False)),
                    "output": str(getattr(src, "raw_output", getattr(src, "content", "")))[:200],
                })
    except Exception:
        pass
    if not chain_steps and not tokens_used and not tool_calls:
        return None
    return EvalMetadata(
        chain_steps=chain_steps if chain_steps else None,
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="llamaindex",
    )


def _extract_haystack_metadata(raw: Any) -> EvalMetadata | None:
    """Haystack Pipeline 결과에서 메타데이터 자동 추출 (P3-A 강화).

    ``pipeline.run(...)`` 결과 dict의 컴포넌트 출력을 ``chain_steps`` 로 변환한다.
    컴포넌트 유형을 이름/출력 키 기반으로 추론하고, ``meta.usage`` 토큰 정보를 추출한다.
    """
    # Haystack pipeline.run() 결과: dict 형태 {"component_name": {"key": value}}
    if not isinstance(raw, dict):
        return None
    # Haystack 결과인지 판단: 값이 dict of dicts 구조인지 확인
    first_val = next(iter(raw.values()), None) if raw else None
    if not isinstance(first_val, dict):
        return None

    # P3-A: 컴포넌트 유형 추론 헬퍼
    def _infer_component_type(name: str, outputs: dict) -> str:
        name_lower = name.lower()
        out_keys = set(outputs.keys())
        if any(k in name_lower for k in ("retriever", "retrieve", "search")):
            return "retriever"
        if any(k in name_lower for k in ("generator", "llm", "chat", "prompt")):
            return "generator"
        if any(k in name_lower for k in ("reader", "extract", "qa")):
            return "reader"
        if any(k in name_lower for k in ("embed", "encoder")):
            return "embedder"
        if any(k in name_lower for k in ("ranker", "rerank")):
            return "ranker"
        if "documents" in out_keys:
            return "retriever"
        if "replies" in out_keys or "answers" in out_keys:
            return "generator"
        return "component"

    chain_steps: list[dict[str, Any]] = []
    tokens_used: dict[str, int] | None = None

    for component_name, outputs in raw.items():
        if not isinstance(outputs, dict):
            continue
        # P3-A: meta.usage 에서 토큰 정보 추출
        for v in outputs.values():
            if isinstance(v, list):
                for item in v:
                    usage = None
                    if hasattr(item, "meta") and isinstance(item.meta, dict):
                        usage = item.meta.get("usage")
                    elif isinstance(item, dict):
                        usage = item.get("meta", {}).get("usage")
                    if isinstance(usage, dict):
                        total = usage.get("total_tokens") or usage.get("total", 0)
                        prompt = usage.get("prompt_tokens") or usage.get("input", 0)
                        completion = usage.get("completion_tokens") or usage.get("output", 0)
                        if total:
                            tokens_used = {
                                "total": total,
                                "input": prompt,
                                "output": completion,
                            }
                            break
                if tokens_used:
                    break

        # 출력 값 요약 (긴 텍스트 truncate)
        output_summary = {
            k: str(v)[:200] if isinstance(v, str) else repr(v)[:200]
            for k, v in outputs.items()
        }
        component_type = _infer_component_type(component_name, outputs)
        chain_steps.append({
            "name": str(component_name),
            "type": component_type,
            "output": output_summary,
            "success": True,
            "execution_time": 0.0,
        })
    # Haystack tool_calls — retriever/generator/reader 컴포넌트를 tool_calls 로 변환
    tool_calls: list[dict[str, Any]] = []
    _TOOL_COMPONENT_TYPES = {"retriever", "generator", "reader", "embedder", "ranker"}
    for _step in chain_steps:
        if _step.get("type") in _TOOL_COMPONENT_TYPES:
            tool_calls.append({
                "tool_name": str(_step.get("name", "unknown")),
                "input": {},
                "success": _step.get("success", True),
                "output": str(_step.get("output", ""))[:200] if isinstance(_step.get("output"), str) else str(_step.get("output", ""))[:200],
            })
    if not chain_steps:
        return None
    return EvalMetadata(
        chain_steps=chain_steps,
        tool_calls=tool_calls if tool_calls else None,
        framework="haystack",
        tokens_used=tokens_used,
    )


# 프레임워크 식별자 → 자동 메타데이터 추출 어댑터 레지스트리
# framework= 파라미터에 지정된 값에 따라 자동으로 호출된다.
# EvalMetadata 튜플 반환이나 get_eval_ctx()가 이미 있으면 어댑터는 건너뛴다.
def _extract_vertexai_metadata(raw: Any) -> EvalMetadata | None:
    """Google Vertex AI SDK 응답에서 메타데이터 자동 추출 (E2).

    ``GenerateContentResponse`` 의 ``candidates[0].content.parts`` 에서
    ``function_call`` 파트와 ``usage_metadata`` 토큰을 자동 추출한다.
    ``google.cloud.aiplatform`` / ``vertexai.generative_models`` 응답 구조와 호환된다.
    """
    # VertexAI GenerateContentResponse — Gemini API 응답과 동일 구조
    tool_calls: list[dict[str, Any]] = []
    tokens_used: dict[str, int] | None = None
    try:
        candidates = getattr(raw, "candidates", None)
        if candidates:
            parts = getattr(candidates[0].content, "parts", []) if candidates else []
            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    tool_calls.append({
                        "name": getattr(fc, "name", "unknown"),
                        "args": dict(getattr(fc, "args", {}) or {}),
                        "result": None,
                    })
        usage = getattr(raw, "usage_metadata", None)
        if usage is not None:
            inp = getattr(usage, "prompt_token_count", 0) or 0
            out = getattr(usage, "candidates_token_count", 0) or 0
            total = getattr(usage, "total_token_count", 0) or (inp + out)
            tokens_used = {"input": int(inp), "output": int(out), "total": int(total)}
    except Exception:
        pass
    if not tool_calls and tokens_used is None:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="vertexai",
    )


def _extract_ollama_metadata(raw: Any) -> EvalMetadata | None:
    """Ollama API 응답에서 메타데이터 자동 추출 (E3).

    ``ollama.chat()`` / ``ollama.generate()`` 응답 객체 및 ``{"message": ..., "prompt_eval_count": ...}``
    형태의 dict 응답을 지원한다.
    """
    tool_calls: list[dict[str, Any]] = []
    tokens_used: dict[str, int] | None = None
    try:
        # ollama-python ChatResponse / GenerateResponse
        if hasattr(raw, "message"):
            msg = raw.message
            tc_list = getattr(msg, "tool_calls", None)
            if tc_list:
                for tc in tc_list:
                    func = getattr(tc, "function", None) or tc
                    tool_calls.append({
                        "name": getattr(func, "name", "unknown"),
                        "args": dict(getattr(func, "arguments", {}) or {}),
                        "result": None,
                    })
        elif isinstance(raw, dict):
            msg = raw.get("message", {})
            tc_list = msg.get("tool_calls") if isinstance(msg, dict) else None
            if tc_list:
                for tc in tc_list:
                    func = tc.get("function", {}) if isinstance(tc, dict) else {}
                    tool_calls.append({
                        "name": func.get("name", "unknown"),
                        "args": func.get("arguments", {}),
                        "result": None,
                    })
        # Token counts: prompt_eval_count / eval_count
        def _get(obj, *keys):
            for k in keys:
                v = obj.get(k) if isinstance(obj, dict) else getattr(obj, k, None)
                if v is not None:
                    return v
            return 0
        inp = int(_get(raw, "prompt_eval_count") or 0)
        out = int(_get(raw, "eval_count") or 0)
        if inp or out:
            tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass
    if not tool_calls and tokens_used is None:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="ollama",
    )


def _extract_cohere_metadata(raw: Any) -> EvalMetadata | None:
    """C1: Cohere SDK ``NonStreamedChatResponse`` / ``StreamedChatResponse`` / ``ChatResponse`` 메타데이터 추출.

    cohere-python v5+ 응답에서 tool_calls 와 token 사용량을 추출한다.
    C1: ``StreamedChatResponse`` 감지 시 최선 파싱 시도.
    ``pip install cohere`` 필요.
    """
    tool_calls: list[dict[str, Any]] = []
    tokens_used: dict[str, int] | None = None

    # C1: 스트리밍 응답 감지
    cls_name = type(raw).__name__
    is_streaming = "Stream" in cls_name or (
        hasattr(raw, "text") and hasattr(raw, "finish_reason") and not hasattr(raw, "meta")
    )

    try:
        if is_streaming:
            logger.debug("Cohere streaming response requires real-time aggregation. Attempting basic token extraction only.")
            # 스트리밍 응답에서 meta.tokens 추출 시도
            meta = getattr(raw, "meta", None)
            if meta is not None:
                tokens_obj = getattr(meta, "tokens", None)
                if tokens_obj is not None:
                    inp = int(getattr(tokens_obj, "input_tokens", 0) or 0)
                    out = int(getattr(tokens_obj, "output_tokens", 0) or 0)
                    if inp or out:
                        tokens_used = {"input": inp, "output": out, "total": inp + out}
        else:
            # cohere v5+: NonStreamedChatResponse
            raw_tool_calls = getattr(raw, "tool_calls", None)
            if raw_tool_calls:
                for tc in raw_tool_calls:
                    tool_calls.append({
                        "name": getattr(tc, "name", "unknown"),
                        "args": dict(getattr(tc, "parameters", {}) or {}),
                        "result": None,
                    })
            # Token usage: meta.tokens 또는 meta.billed_units
            meta = getattr(raw, "meta", None)
            if meta is not None:
                billed = getattr(meta, "billed_units", None) or getattr(meta, "tokens", None)
                if billed is not None:
                    inp = int(getattr(billed, "input_tokens", 0) or 0)
                    out = int(getattr(billed, "output_tokens", 0) or 0)
                    if inp or out:
                        tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass
    _raw_text = getattr(raw, "text", None)
    if not tool_calls and tokens_used is None and not _raw_text:
        return None
    # B2: tool_calls를 chain_steps로도 시각화
    chain_steps: list[dict[str, Any]] = []
    for tc in tool_calls:
        chain_steps.append({
            "name": tc.get("name", "unknown"),
            "type": "tool_call",
            "output": str(tc.get("args", {}))[:200],
            "success": True,
        })
    # 텍스트 응답도 chain_step으로 추가
    _text = _raw_text
    if _text:
        chain_steps.append({
            "name": "cohere_response",
            "type": "generation",
            "output": str(_text)[:500],
            "success": True,
        })
    return EvalMetadata(
        chain_steps=chain_steps if chain_steps else None,
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="cohere",
    )


def _extract_groq_metadata(raw: Any) -> EvalMetadata | None:
    """C2: Groq SDK 응답 메타데이터 추출 — OpenAI 호환 형식 재사용.

    Groq v0.9+ 의 ``usage.cache_creation_tokens`` / ``usage.cache_read_tokens`` 필드 추가 지원.
    """
    meta = _extract_openai_metadata(raw)
    tool_calls = meta.tool_calls if meta is not None else None
    tokens_used = meta.tokens_used if meta is not None else None

    # C2: Groq v0.9+ 캐시 토큰 필드 추가 추출
    try:
        usage = getattr(raw, "usage", None)
        if usage is not None:
            # 기본 토큰 (meta가 None인 경우에도 시도)
            if tokens_used is None:
                inp = int(getattr(usage, "prompt_tokens", 0) or 0)
                out = int(getattr(usage, "completion_tokens", 0) or 0)
                if inp or out:
                    tokens_used = {"input": inp, "output": out, "total": int(inp + out)}
            # 캐시 토큰 (Groq v0.9+)
            if tokens_used is not None:
                cache_creation = int(getattr(usage, "cache_creation_tokens", 0) or 0)
                cache_read = int(getattr(usage, "cache_read_tokens", 0) or 0)
                if cache_creation or cache_read:
                    tokens_used = dict(tokens_used)
                    if cache_creation:
                        tokens_used["cache_creation"] = cache_creation
                    if cache_read:
                        tokens_used["cache_read"] = cache_read
    except Exception:
        pass

    if tool_calls is None and tokens_used is None:
        return None
    return EvalMetadata(
        tool_calls=tool_calls,
        tokens_used=tokens_used,
        framework="groq",
    )


def _extract_mistral_metadata(raw: Any) -> EvalMetadata | None:
    """C3: Mistral AI SDK 응답 메타데이터 추출.

    Mistral ``ChatCompletionResponse`` 에서 tool_calls 와 usage 를 추출한다.
    C3: 구버전 ``function_call`` 구조 fallback 지원.
    """
    import json as _json

    tool_calls: list[dict[str, Any]] = []
    tokens_used: dict[str, int] | None = None
    try:
        choices = getattr(raw, "choices", None)
        msg = getattr(choices[0], "message", None) if choices else None

        if msg is not None:
            # 신버전: tool_calls 구조
            raw_tc = getattr(msg, "tool_calls", None)
            if raw_tc:
                for tc in raw_tc:
                    fn = getattr(tc, "function", None) or tc
                    args_raw = getattr(fn, "arguments", {}) or {}
                    try:
                        args_parsed = _json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
                    except Exception:
                        args_parsed = {}
                    tool_calls.append({
                        "name": getattr(fn, "name", "unknown"),
                        "args": args_parsed,
                        "result": None,
                    })

            # C3: 구버전 fallback — function_call 구조
            if not tool_calls:
                fc = getattr(msg, "function_call", None)
                if fc is not None:
                    fc_args = getattr(fc, "arguments", "") or ""
                    try:
                        fc_args_parsed = _json.loads(fc_args) if isinstance(fc_args, str) and fc_args else {}
                    except Exception:
                        fc_args_parsed = {}
                    tool_calls.append({
                        "name": getattr(fc, "name", "unknown"),
                        "args": fc_args_parsed,
                        "result": None,
                    })

        usage = getattr(raw, "usage", None)
        if usage is not None:
            inp = int(getattr(usage, "prompt_tokens", 0) or 0)
            out = int(getattr(usage, "completion_tokens", 0) or 0)
            if inp or out:
                tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass
    if not tool_calls and tokens_used is None:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="mistral",
    )


def _parse_titan_response(
    raw: Any,
    tool_calls_list: list[dict[str, Any]],
    tokens_used_ref: list[dict[str, int] | None],
) -> None:
    """C4: Amazon Titan Bedrock 응답 파싱 (InvokeModel API 형식).

    ``{"results": [{"outputText": ..., "tokenCount": ...}], "inputTextTokenCount": ...}``
    """
    if not isinstance(raw, dict):
        return
    results = raw.get("results", [])
    input_count = int(raw.get("inputTextTokenCount", 0) or 0)
    output_count = int(results[0].get("tokenCount", 0)) if results else 0
    if input_count or output_count:
        tokens_used_ref[0] = {
            "input": input_count,
            "output": output_count,
            "total": input_count + output_count,
        }


def _parse_bedrock_mistral(
    raw: Any,
    tool_calls_list: list[dict[str, Any]],
    tokens_used_ref: list[dict[str, int] | None],
) -> None:
    """C4: Mistral on Bedrock 응답 파싱 (InvokeModel API 형식).

    ``{"outputs": [{"text": ..., "stop_reason": ...}]}``
    """
    if not isinstance(raw, dict):
        return
    # Mistral on Bedrock — InvokeModel API 응답 (토큰 정보 미제공)
    # 필요 시 outputs에서 텍스트만 추출 가능
    # (토큰 정보는 InvokeModel 응답에 미포함)
    pass  # 구조 탐지만, 토큰은 없음


def _extract_bedrock_metadata(raw: Any) -> EvalMetadata | None:
    """C4: AWS Bedrock Converse API / InvokeModel API 응답 메타데이터 추출.

    ``bedrock_runtime.converse()`` 응답 dict 에서 toolUse 와 usage 를 추출한다.
    C4: ``model_id`` 기반 자동 파서 선택 — Amazon Titan, Mistral on Bedrock 지원.
    """
    tool_calls: list[dict[str, Any]] = []
    tokens_used: dict[str, int] | None = None
    try:
        if isinstance(raw, dict):
            # C4: model_id 기반 자동 파서 선택
            model_id = raw.get("model_id", raw.get("modelId", "")) or ""

            if "titan" in model_id.lower():
                # Amazon Titan InvokeModel API 형식
                _ref: list[dict[str, int] | None] = [None]
                _parse_titan_response(raw, tool_calls, _ref)
                tokens_used = _ref[0]
            elif "mistral" in model_id.lower() and "outputs" in raw:
                # Mistral on Bedrock InvokeModel API 형식
                _ref2: list[dict[str, int] | None] = [None]
                _parse_bedrock_mistral(raw, tool_calls, _ref2)
                tokens_used = _ref2[0]
            else:
                # 기본: Claude Converse API 형식
                output = raw.get("output", {})
                msg = output.get("message", {}) if isinstance(output, dict) else {}
                content = msg.get("content", []) if isinstance(msg, dict) else []
                for block in (content if isinstance(content, list) else []):
                    if isinstance(block, dict) and "toolUse" in block:
                        tu = block["toolUse"]
                        tool_calls.append({
                            "name": tu.get("name", "unknown"),
                            "args": tu.get("input", {}),
                            "result": None,
                        })
                usage = raw.get("usage", {})
                if isinstance(usage, dict):
                    inp = int(usage.get("inputTokens", 0) or 0)
                    out = int(usage.get("outputTokens", 0) or 0)
                    if inp or out:
                        tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass
    if not tool_calls and tokens_used is None:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="bedrock",
    )


def _extract_smolagents_metadata(raw: Any) -> EvalMetadata | None:
    """C5: HuggingFace smolagents 응답 메타데이터 추출.

    ``agent.run()`` 결과에서 tool_calls 와 chain_steps 를 추출한다.
    C5: step에서 tool 성공/실패 여부와 입력값 추출 강화.
    """
    chain_steps: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    try:
        # smolagents AgentOutput or dict
        steps = getattr(raw, "steps", None) or (raw.get("steps") if isinstance(raw, dict) else None)
        if steps:
            for step in steps:
                if isinstance(step, dict):
                    # dict 형태 step
                    chain_steps.append({
                        "name": step.get("name", "step"),
                        "success": True,
                        "execution_time": step.get("duration", 0.0),
                        "output": str(step.get("output", ""))[:200],
                    })
                else:
                    # 객체 형태 step — C5 개선: ToolCall 스텝 감지
                    step_type = type(step).__name__
                    error = getattr(step, "error", None)
                    obs = getattr(step, "observation", None)
                    success = error is None

                    if "ToolCall" in step_type or hasattr(step, "tool_name"):
                        # C5: ToolCall 스텝에서 tool_calls 추출
                        tool_name = getattr(step, "tool_name", getattr(step, "name", "unknown"))
                        tool_input = getattr(step, "tool_input", getattr(step, "arguments", {}))
                        tool_calls.append({
                            "tool_name": str(tool_name),
                            "input": tool_input if isinstance(tool_input, dict) else str(tool_input),
                            "success": success,
                            "output": str(obs)[:200] if obs else None,
                            "error": str(error) if error else None,
                        })

                    chain_steps.append({
                        "name": step_type,
                        "success": success,
                        "execution_time": getattr(step, "duration", 0.0),
                        "output": str(obs)[:200] if obs else "",
                    })
    except Exception:
        pass
    if not chain_steps and not tool_calls:
        return None
    # B1: chain_steps의 output 텍스트 합산으로 토큰 추정
    tokens_used: dict[str, int] | None = None
    if chain_steps:
        total_chars = sum(len(str(s.get("output", ""))) for s in chain_steps)
        if total_chars > 0:
            est = max(1, total_chars // 4)
            tokens_used = {"total": est, "output": est, "estimated": True}

    return EvalMetadata(
        chain_steps=chain_steps if chain_steps else None,
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="smolagents",
    )


def _extract_semantic_kernel_metadata(raw: Any) -> EvalMetadata | None:
    """C6: Microsoft Semantic Kernel 응답 메타데이터 추출.

    ``kernel.invoke()`` 결과에서 function_result 및 사용 정보를 추출한다.
    C6: ``inner_content`` 의 추가 정보 추출 — OpenAI/Azure 백엔드 및 Anthropic 백엔드 지원.
    """
    chain_steps: list[dict[str, Any]] | None = None
    tokens_used: dict[str, int] | None = None
    try:
        # FunctionResult or KernelContent
        inner = getattr(raw, "value", None) or getattr(raw, "inner_content", None)
        if inner is not None:
            # B2: 더 구조화된 chain_steps
            chain_steps = [{
                "name": "semantic_kernel_invoke",
                "type": "llm_call",
                "output": str(inner)[:500],
                "success": True,
                "execution_time": 0.0,
            }]
            # plugin/function 이름이 있으면 추가
            fn_name = getattr(raw, "function_name", None) or getattr(raw, "plugin_name", None)
            if fn_name:
                chain_steps[0]["function"] = str(fn_name)

        # C6: inner_content 에서 토큰 추출 시도
        inner_content = getattr(raw, "inner_content", None)
        if inner_content is not None and tokens_used is None:
            # OpenAI/Azure 백엔드: inner_content가 ChatCompletion 또는 usage 객체
            if hasattr(inner_content, "usage"):
                usage = inner_content.usage
                inp = int(getattr(usage, "prompt_tokens", 0) or 0)
                out = int(getattr(usage, "completion_tokens", 0) or 0)
                if inp or out:
                    tokens_used = {"input": inp, "output": out, "total": inp + out}
            # Anthropic 백엔드: inner_content가 stop_reason을 가짐
            elif hasattr(inner_content, "stop_reason") and tokens_used is None:
                tokens_used = _extract_anthropic_tokens(inner_content)

        # usage from metadata
        if tokens_used is None:
            meta = getattr(raw, "metadata", None)
            if meta and isinstance(meta, dict):
                usage = meta.get("usage") or meta.get("token_usage")
                if usage:
                    inp = int(getattr(usage, "prompt_tokens", 0) or (usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0) or 0)
                    out = int(getattr(usage, "completion_tokens", 0) or (usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0) or 0)
                    if inp or out:
                        tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass
    if chain_steps is None and tokens_used is None:
        return None
    # Semantic Kernel tool_calls — plugin/function 호출을 tool_calls 로 추출
    tool_calls: list[dict[str, Any]] = []
    try:
        # FunctionResult: function_name + plugin_name
        _fn_name = getattr(raw, "function_name", None)
        _plugin_name = getattr(raw, "plugin_name", None)
        _tool_name = f"{_plugin_name}.{_fn_name}" if _plugin_name and _fn_name else (_fn_name or _plugin_name)
        if _tool_name:
            _inner_val = getattr(raw, "value", None) or getattr(raw, "inner_content", None)
            tool_calls.append({
                "tool_name": str(_tool_name),
                "input": {},
                "success": True,
                "output": str(_inner_val)[:300] if _inner_val is not None else "",
            })
        # kernel.invoke_stream() or multi-step: check for list of FunctionResult
        if not tool_calls and hasattr(raw, "function_results"):
            for _fr in (getattr(raw, "function_results", []) or []):
                _fn = getattr(_fr, "function_name", None) or getattr(_fr, "name", None)
                if _fn:
                    tool_calls.append({
                        "tool_name": str(_fn),
                        "input": {},
                        "success": True,
                        "output": str(getattr(_fr, "value", ""))[:200],
                    })
    except Exception:
        pass
    return EvalMetadata(
        chain_steps=chain_steps,
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="semantic_kernel",
    )


def _auto_detect_framework(raw: Any) -> str | None:
    """C7: 응답 객체의 타입/속성으로 프레임워크 자동 감지.

    모듈명 기반 감지(높은 신뢰도)를 우선 시도하고, 속성 기반 감지(fallback)를 후순위로 적용한다.

    Args:
        raw: 에이전트 함수가 반환한 원본 결과 객체.

    Returns:
        감지된 프레임워크 식별자 문자열, 또는 감지 실패 시 ``None``.

    Example::

        detected = _auto_detect_framework(response)
        # "anthropic", "openai", "gemini", ... 또는 None
    """
    if raw is None:
        return None
    module_name = type(raw).__module__ or ""

    # 모듈명 기반 감지 (가장 신뢰도 높음)
    if "langchain" in module_name:
        return "langchain"
    if "langgraph" in module_name:
        return "langgraph"
    if "crewai" in module_name:
        return "crewai"
    if "autogen" in module_name:
        return "autogen"
    if "anthropic" in module_name:
        return "anthropic"
    if "openai" in module_name:
        return "openai"
    if "google.generativeai" in module_name or "google.ai.generativelanguage" in module_name:
        return "gemini"
    if "vertexai" in module_name or "google.cloud.aiplatform" in module_name:
        return "vertexai"
    if "cohere" in module_name:
        return "cohere"
    if "groq" in module_name:
        return "groq"
    if "mistralai" in module_name:
        return "mistral"
    if "boto3" in module_name or "botocore" in module_name:
        return "bedrock"
    if "smolagents" in module_name:
        return "smolagents"
    if "semantic_kernel" in module_name:
        return "semantic_kernel"
    if "ollama" in module_name:
        return "ollama"
    if "llama_index" in module_name or "llama-index" in module_name:
        return "llamaindex"
    if "haystack" in module_name:
        return "haystack"
    if "dspy" in module_name:
        return "dspy"
    if "pydantic_ai" in module_name or "pydanticai" in module_name:
        return "pydanticai"

    # 속성 기반 감지 (fallback)
    if _is_anthropic_response(raw):
        return "anthropic"
    if _is_openai_response(raw):
        return "openai"
    # Item I: Vertex AI vs Google Gemini 구분 — 모듈명 기반 정밀 감지
    if _is_gemini_response(raw):
        _module = type(raw).__module__ or ""
        if "vertexai" in _module or "google.cloud" in _module:
            return "vertexai"
        return "gemini"
    if _is_cohere_response(raw):
        return "cohere"

    # H2: 추가 프레임워크 속성 기반 감지
    # Groq — choices + x_groq 속성 (Groq SDK 특유 필드)
    if hasattr(raw, "choices") and hasattr(raw, "x_groq"):
        return "groq"
    # Mistral — choices + model 속성에 "mistral" 포함
    if hasattr(raw, "choices") and hasattr(raw, "model") and "mistral" in str(getattr(raw, "model", "")).lower():
        return "mistral"
    # Bedrock — ResponseMetadata + output (AWS Converse API)
    if hasattr(raw, "ResponseMetadata") and hasattr(raw, "output"):
        return "bedrock"
    # smolagents — logs + task 속성 조합 (HuggingFace smolagents Agent)
    if hasattr(raw, "logs") and hasattr(raw, "task"):
        return "smolagents"
    # vLLM native RequestOutput — outputs + prompt_token_ids
    if hasattr(raw, "outputs") and hasattr(raw, "prompt_token_ids"):
        return "vllm"
    # HuggingFace pipeline — list of dicts with generated_text
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and "generated_text" in raw[0]:
        return "huggingface"

    # C2: DSPy Prediction — _completions 내부 속성 또는 completions (choices와 구별)
    if hasattr(raw, "_completions") or (
        hasattr(raw, "completions") and not hasattr(raw, "choices") and not hasattr(raw, "content")
    ):
        return "dspy"
    # C2: PydanticAI RunResult — data + all_messages() 조합
    if (
        hasattr(raw, "data")
        and hasattr(raw, "all_messages")
        and callable(getattr(raw, "all_messages", None))
    ):
        return "pydanticai"

    return None


def _safe_adapter_call(
    adapter_fn: Callable,
    raw: Any,
    framework_name: str,
) -> tuple[EvalMetadata | None, str | None]:
    """C8: 어댑터 함수를 안전하게 호출하고 ``(result, error_msg)`` 반환.

    Args:
        adapter_fn: 호출할 어댑터 함수.
        raw: 어댑터에 전달할 원본 응답 객체.
        framework_name: 에러 메시지에 포함할 프레임워크 이름.

    Returns:
        ``(EvalMetadata | None, error_message | None)`` 튜플.
        성공 시 ``(result, None)``, 실패 시 ``(None, error_msg)``.
    """
    try:
        result = adapter_fn(raw)
        return result, None
    except Exception as exc:
        err_msg = f"{framework_name}: {type(exc).__name__}: {exc}"
        logger.debug("Framework adapter '%s' failed: %s", framework_name, err_msg)
        return None, err_msg


def _extract_vllm_metadata(raw: Any) -> EvalMetadata | None:
    """F4: vLLM OpenAI-호환 API 응답에서 메타데이터 추출.

    vLLM은 OpenAI 호환 API를 제공하므로 choices[0].message.tool_calls + usage.total_tokens 패턴 사용.
    RequestOutput (native vLLM) 응답도 지원.
    """
    tool_calls: list[dict[str, Any]] = []
    tokens_used: dict[str, int] | None = None
    try:
        # OpenAI-compatible (vllm.entrypoints.openai.api_server)
        choices = getattr(raw, "choices", None)
        if choices and isinstance(choices, (list, tuple)) and len(choices) > 0:
            msg = getattr(choices[0], "message", None) or getattr(choices[0], "delta", None)
            if msg:
                for tc in (getattr(msg, "tool_calls", None) or []):
                    fn = getattr(tc, "function", None)
                    if fn:
                        tool_calls.append({
                            "tool_name": getattr(fn, "name", "unknown"),
                            "input": getattr(fn, "arguments", {}),
                            "success": True,
                        })
        # Native vLLM RequestOutput: outputs[0].text, prompt_token_ids/outputs[0].token_ids
        outputs = getattr(raw, "outputs", None)
        if outputs:
            pass  # Native RequestOutput — no tool_calls; token count via prompt_token_ids
        usage = getattr(raw, "usage", None)
        if usage:
            inp = int(getattr(usage, "prompt_tokens", 0) or 0)
            out = int(getattr(usage, "completion_tokens", 0) or 0)
            total = int(getattr(usage, "total_tokens", 0) or inp + out)
            if inp or out or total:
                tokens_used = {"input": inp, "output": out, "total": total}
    except Exception:
        pass
    if not tool_calls and tokens_used is None:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="vllm",
    )


def _extract_huggingface_metadata(raw: Any) -> EvalMetadata | None:
    """F4: HuggingFace transformers/trl pipeline 응답에서 메타데이터 추출.

    pipeline() 응답 (list of dicts), Agent (transformers.agents) 응답,
    또는 generate() dict 응답을 지원한다.
    """
    chain_steps: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    tokens_used: dict[str, int] | None = None
    try:
        # P3-A: 토큰 수 추정 헬퍼 (HuggingFace는 token count API 없는 경우 많음)
        def _estimate_tokens_from_text(text: str) -> int:
            """문자 수 기반 토큰 수 추정 (4자 ≈ 1 토큰 heuristic)."""
            return max(1, len(text) // 4)

        # transformers pipeline: [{"generated_text": "..."}] 또는 [{"label": ..., "score": ...}]
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            total_output_chars = 0
            generated_text = ""  # raw가 비어있지 않음이 위에서 보장되지만 정적 분석 안전망으로 명시
            for i, item in enumerate(raw):
                step_name = "generation" if "generated_text" in item else f"output_{i}"
                generated_text = str(item.get("generated_text", item.get("text", item)))
                chain_steps.append({
                    "name": step_name,
                    "output": generated_text[:500],
                    "success": True,
                    "execution_time": 0.0,
                })
                total_output_chars += len(generated_text)
            # P3-A: 출력 문자 기반 토큰 추정
            if total_output_chars > 0:
                est_output = _estimate_tokens_from_text(generated_text if len(raw) == 1 else str(raw))
                tokens_used = {"total": est_output, "output": est_output, "estimated": True}
        # transformers.agents Agent final_answer / tool_calls
        elif hasattr(raw, "logs") or hasattr(raw, "tool_calls"):
            _tc_attr = getattr(raw, "tool_calls", None)
            if _tc_attr:
                for tc in (_tc_attr if isinstance(_tc_attr, list) else [_tc_attr]):
                    tool_calls.append({
                        "tool_name": str(getattr(tc, "name", "unknown")),
                        "input": getattr(tc, "arguments", getattr(tc, "args", {})),
                        "success": not bool(getattr(tc, "error", None)),
                    })
            _logs = getattr(raw, "logs", None)
            if _logs and isinstance(_logs, list):
                for j, log in enumerate(_logs):
                    chain_steps.append({
                        "name": f"log_{j}",
                        "output": str(log)[:300],
                        "success": True,
                        "execution_time": 0.0,
                    })
            # P3-A: logs 기반 토큰 추정
            if _logs:
                total_log_chars = sum(len(str(l)) for l in _logs)
                if total_log_chars > 0:
                    est_tokens = _estimate_tokens_from_text(" ".join(str(l) for l in _logs))
                    tokens_used = {"total": est_tokens, "output": est_tokens, "estimated": True}
        # generate() dict: {"input_ids": ..., "sequences": ...}
        elif isinstance(raw, dict):
            seq = raw.get("sequences") or raw.get("outputs")
            if seq:
                chain_steps.append({
                    "name": "generate",
                    "output": str(seq)[:300],
                    "success": True,
                    "execution_time": 0.0,
                })
            # P3-A: input_ids / sequences 길이에서 토큰 수 직접 측정
            input_ids = raw.get("input_ids")
            if input_ids is not None:
                try:
                    # tensor or list
                    inp_len = len(input_ids[0]) if hasattr(input_ids, "__getitem__") else 0
                    out_ids = raw.get("sequences")
                    out_len = (len(out_ids[0]) - inp_len) if out_ids is not None else 0
                    if inp_len > 0:
                        tokens_used = {
                            "input": inp_len,
                            "output": max(0, out_len),
                            "total": inp_len + max(0, out_len),
                        }
                except Exception:
                    pass
    except Exception:
        pass
    if not chain_steps and not tool_calls and tokens_used is None:
        return None
    return EvalMetadata(
        chain_steps=chain_steps if chain_steps else None,
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="huggingface",
    )


def _extract_openai_agents_metadata(raw: Any) -> EvalMetadata | None:
    """OpenAI Agents SDK(``openai-agents`` 패키지, Swarm 후속 공식 SDK) 결과에서
    메타데이터 자동 추출.

    ``Runner.run(...)``가 반환하는 ``RunResult``에서 추출한다 — Chat Completions의
    ``choices[0].message``와는 다른 구조로, ``new_items``(``RunItem`` 리스트) 중
    ``ToolCallItem``에서 도구 호출을, ``raw_responses``(``ModelResponse`` 리스트,
    세션 중 모델 호출마다 1건)의 ``usage``를 합산해 토큰 사용량을 추출한다.
    ``ToolCallItem.tool_name``/``.call_id``는 SDK가 제공하는 편의 프로퍼티이고,
    도구 인자(arguments)는 그 밑의 ``raw_item``(``ResponseFunctionToolCall``,
    Responses API와 동일 타입)에서 가져온다.
    """
    if not hasattr(raw, "new_items") and not hasattr(raw, "raw_responses"):
        return None
    tool_calls: list[dict[str, Any]] = []
    try:
        for item in (getattr(raw, "new_items", None) or []):
            if type(item).__name__ != "ToolCallItem":
                continue
            tool_name = getattr(item, "tool_name", None) or "unknown"
            call_id = getattr(item, "call_id", "") or ""
            raw_item = getattr(item, "raw_item", None)
            arguments = getattr(raw_item, "arguments", "") if raw_item is not None else ""
            tool_calls.append({
                "tool_name": str(tool_name),
                "input": arguments,
                "tool_call_id": str(call_id),
                "success": True,
            })
    except Exception:
        pass

    tokens_used: dict[str, int] | None = None
    try:
        total_inp = 0
        total_out = 0
        for resp in (getattr(raw, "raw_responses", None) or []):
            usage = getattr(resp, "usage", None)
            if usage is None:
                continue
            total_inp += getattr(usage, "input_tokens", 0) or 0
            total_out += getattr(usage, "output_tokens", 0) or 0
        if total_inp or total_out:
            tokens_used = {"input": int(total_inp), "output": int(total_out), "total": int(total_inp + total_out)}
    except Exception:
        pass

    if not tool_calls and not tokens_used:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="openai_agents",
    )


def _extract_google_adk_metadata(raw: Any) -> EvalMetadata | None:
    """Google ADK(Agent Development Kit) 결과에서 메타데이터 자동 추출.

    ``runner.run()``/``run_async()``는 세션 중 여러 ``Event``를 순차 yield하는
    제너레이터이므로(``@agent_eval``은 함수가 단일 값을 반환한다고 가정), 호출자가
    스트림을 직접 순회하며 마지막(또는 도구 호출이 있는) ``Event``를 반환해야 한다.

    ``Event``는 ``LlmResponse``를 상속해 ``get_function_calls()``
    (``google.genai.types.FunctionCall`` 리스트 — 기존 ``gemini`` 어댑터와 동일한
    genai SDK 타입)와 ``usage_metadata``(``GenerateContentResponseUsageMetadata``,
    마찬가지로 ``gemini`` 어댑터와 동일한 필드명 ``prompt_token_count``/
    ``candidates_token_count``)를 그대로 제공한다.
    """
    if not hasattr(raw, "get_function_calls") and not hasattr(raw, "usage_metadata"):
        return None
    tool_calls: list[dict[str, Any]] = []
    try:
        get_fc = getattr(raw, "get_function_calls", None)
        for fc in cast(Any, get_fc() if callable(get_fc) else []):
            tool_calls.append({
                "tool_name": getattr(fc, "name", "unknown"),
                "input": dict(getattr(fc, "args", {}) or {}),
                "tool_call_id": getattr(fc, "id", "") or "",
                "success": True,
            })
    except Exception:
        pass

    tokens_used: dict[str, int] | None = None
    try:
        um = getattr(raw, "usage_metadata", None)
        if um:
            inp = getattr(um, "prompt_token_count", 0) or 0
            out = getattr(um, "candidates_token_count", 0) or 0
            if inp or out:
                tokens_used = {"input": int(inp), "output": int(out), "total": int(inp + out)}
    except Exception:
        pass

    if not tool_calls and not tokens_used:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="google_adk",
    )


def _extract_claude_agent_sdk_metadata(raw: Any) -> EvalMetadata | None:
    """Claude Agent SDK(``claude-agent-sdk`` 패키지, 구 Claude Code SDK) 결과에서
    메타데이터 자동 추출.

    ``query(...)``는 여러 메시지 타입을 순차 yield하는 비동기 스트림이므로
    (``@agent_eval``은 함수가 단일 값을 반환한다고 가정), 호출자가 스트림을 직접
    소비해 다음 중 하나를 반환해야 한다.

    - ``AssistantMessage``: ``content``의 ``ToolUseBlock``에서 도구 호출을 추출한다
      (``usage``는 그 메시지 1건분 — raw Anthropic Messages API와 달리 dict 형태).
    - ``ResultMessage``: 세션 전체 누적 ``usage``/``total_cost_usd``/``num_turns``를
      추출한다 (도구 호출 상세는 없음 — ``ResultMessage`` 자체엔 담기지 않는다).

    도구 호출과 세션 총 토큰을 모두 원한다면, 호출자가 스트림을 순회하며 직접 병합해
    ``EvalMetadata``를 구성해 반환하는 편이 이 어댑터를 거치는 것보다 정확하다.
    """
    is_assistant_msg = hasattr(raw, "content") and hasattr(raw, "model")
    is_result_msg = hasattr(raw, "total_cost_usd") or (hasattr(raw, "num_turns") and hasattr(raw, "usage"))
    if not is_assistant_msg and not is_result_msg:
        return None

    tool_calls: list[dict[str, Any]] = []
    if is_assistant_msg:
        try:
            for block in (getattr(raw, "content", None) or []):
                if type(block).__name__ != "ToolUseBlock":
                    continue
                tool_calls.append({
                    "tool_name": getattr(block, "name", "unknown"),
                    "input": getattr(block, "input", {}) or {},
                    "tool_call_id": getattr(block, "id", "") or "",
                    "success": True,
                })
        except Exception:
            pass

    tokens_used: dict[str, int] | None = None
    try:
        usage = getattr(raw, "usage", None)
        if isinstance(usage, dict):
            inp = int(usage.get("input_tokens") or 0)
            out = int(usage.get("output_tokens") or 0)
            cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
            cache_read = int(usage.get("cache_read_input_tokens") or 0)
            total_inp = inp + cache_creation + cache_read
            if total_inp or out:
                tokens_used = {
                    "input": inp, "output": out, "total": total_inp + out,
                    "cache_creation": cache_creation, "cache_read": cache_read,
                }
    except Exception:
        pass

    extra: dict[str, Any] | None = None
    try:
        if is_result_msg:
            cost = getattr(raw, "total_cost_usd", None)
            num_turns = getattr(raw, "num_turns", None)
            if cost is not None or num_turns is not None:
                extra = {}
                if cost is not None:
                    extra["total_cost_usd"] = cost
                if num_turns is not None:
                    extra["num_turns"] = num_turns
    except Exception:
        pass

    if not tool_calls and not tokens_used:
        return None
    return EvalMetadata(
        tool_calls=tool_calls if tool_calls else None,
        tokens_used=tokens_used,
        framework="claude_agent_sdk",
        extra=extra,
    )


_FRAMEWORK_ADAPTERS: dict[str, Callable[[Any], EvalMetadata | None] | None] = {
    "native": None,  # H: sentinel — 어댑터 없음 (네이티브 Python 반환값)
    "langchain": _extract_langchain_metadata,
    "langgraph": _extract_langgraph_metadata,
    "crewai": _extract_crewai_metadata,
    "autogen": _extract_autogen_metadata,
    "dspy": _extract_dspy_metadata,
    "pydanticai": _extract_pydanticai_metadata,
    "anthropic": _extract_anthropic_metadata,
    "openai": _extract_openai_metadata,
    "gemini": _extract_gemini_metadata,
    "llamaindex": _extract_llamaindex_metadata,
    "haystack": _extract_haystack_metadata,
    "vertexai": _extract_vertexai_metadata,
    "ollama": _extract_ollama_metadata,
    "cohere": _extract_cohere_metadata,
    "groq": _extract_groq_metadata,
    "mistral": _extract_mistral_metadata,
    "bedrock": _extract_bedrock_metadata,
    "smolagents": _extract_smolagents_metadata,
    "semantic_kernel": _extract_semantic_kernel_metadata,
    # F4: 신규 어댑터
    "vllm": _extract_vllm_metadata,
    "huggingface": _extract_huggingface_metadata,
    # 공식 에이전트 프레임워크 3종 추가
    "openai_agents": _extract_openai_agents_metadata,
    "google_adk": _extract_google_adk_metadata,
    "claude_agent_sdk": _extract_claude_agent_sdk_metadata,
}


# C6: 프레임워크 어댑터 메타데이터 레지스트리
_FRAMEWORK_ADAPTER_META: dict[str, dict[str, Any]] = {
    "native": {  # H: sentinel — 어댑터 없음, 네이티브 Python 반환값
        "name": "Native",
        "extras": None,
        "extracts": [],
        "async_supported": True,
        "description": "네이티브 Python 반환값 — 어댑터 없음 (자동 감지 대상)",
    },
    "langchain": {
        "name": "LangChain",
        "extras": "langchain",
        "extracts": ["tool_calls", "chain_steps"],
        "async_supported": True,
        "description": "LangChain AgentExecutor — intermediate_steps → tool_calls + chain_steps",
    },
    "langgraph": {
        "name": "LangGraph",
        "extras": "langchain",
        "extracts": ["state_transitions", "graph_traversal", "tool_calls", "chain_steps"],
        "async_supported": True,
        "description": "LangGraph invoke — messages → state_transitions + graph_traversal; ToolMessage/AIMessage → chain_steps; __metadata__ 지원",
    },
    "crewai": {
        "name": "CrewAI",
        "extras": "crewai",
        "extracts": ["agent_interactions"],
        "async_supported": False,
        "description": "CrewAI kickoff — tasks_output → agent_interactions; output_pydantic/output_format/pydantic 필드 지원",
    },
    "autogen": {
        "name": "AutoGen",
        "extras": "autogen",
        "extracts": ["conversation_turns", "tokens_used"],
        "async_supported": True,
        "description": "AutoGen messages/chat_history → conversation_turns; cost/usage_summary → tokens_used",
    },
    "dspy": {
        "name": "DSPy",
        "extras": "dspy",
        "extracts": ["chain_steps", "tokens_used"],
        "async_supported": False,
        "description": "DSPy Prediction — _completions → chain_steps; LM history 전체 multi-step 추출 지원",
    },
    "pydanticai": {
        "name": "PydanticAI",
        "extras": "pydanticai",
        "extracts": ["chain_steps", "tokens_used"],
        "async_supported": True,
        "description": "PydanticAI RunResult — .all_messages() 우선 → chain_steps; ToolCallPart/ToolReturnPart 세분화",
    },
    "anthropic": {
        "name": "Anthropic",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Anthropic Messages API — content[].tool_use → tool_calls; usage → tokens_used",
    },
    "openai": {
        "name": "OpenAI",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "OpenAI Chat Completions / Assistants API — choices[0].message.tool_calls + usage.total_tokens",
    },
    "gemini": {
        "name": "Google Gemini",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Gemini GenerateContentResponse — candidates[0].content.parts[].function_call + usage_metadata",
    },
    "llamaindex": {
        "name": "LlamaIndex",
        "extras": "llm",
        "extracts": ["chain_steps"],
        "async_supported": True,
        "description": "LlamaIndex Response — source_nodes → chain_steps + metadata 토큰 추출",
    },
    "haystack": {
        "name": "Haystack",
        "extras": "llm",
        "extracts": ["chain_steps"],
        "async_supported": True,
        "description": "Haystack Pipeline — 컴포넌트 출력 dict → chain_steps",
    },
    "vertexai": {
        "name": "Vertex AI",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Vertex AI GenerateContentResponse — function_call + usage_metadata",
    },
    "ollama": {
        "name": "Ollama",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": False,
        "description": "Ollama chat()/generate() — tool_calls + prompt_eval_count/eval_count",
    },
    "cohere": {
        "name": "Cohere",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Cohere SDK — tool_calls + meta.tokens; streaming finish_reason 감지",
    },
    "groq": {
        "name": "Groq",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Groq SDK (OpenAI 호환) — tool_calls + usage; cache_creation/read_tokens (v0.9+)",
    },
    "mistral": {
        "name": "Mistral AI",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Mistral AI SDK — tool_calls + usage; function_call 구버전 호환",
    },
    "bedrock": {
        "name": "AWS Bedrock",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Bedrock Converse API — model_id 기반 분기: Titan/Mistral on Bedrock/Claude",
    },
    "smolagents": {
        "name": "HuggingFace smolagents",
        "extras": "llm",
        "extracts": ["tool_calls", "chain_steps"],
        "async_supported": False,
        "description": "smolagents ToolCall 스텝 — 성공/실패 여부 + 입력값 정규화",
    },
    "semantic_kernel": {
        "name": "Semantic Kernel",
        "extras": "llm",
        "extracts": ["chain_steps", "tokens_used"],
        "async_supported": True,
        "description": "Semantic Kernel — inner_content 에서 OpenAI/Anthropic 백엔드 토큰 자동 추출",
    },
    # F4: 신규 어댑터
    "vllm": {
        "name": "vLLM",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "vLLM OpenAI-호환 API — choices[0].message.tool_calls + usage.total_tokens",
    },
    "huggingface": {
        "name": "HuggingFace",
        "extras": "llm",
        "extracts": ["chain_steps", "tool_calls"],
        "async_supported": False,
        "description": "HuggingFace pipeline()/Agent — generated_text chain_steps; tool_calls/actions 추출",
    },
    "openai_agents": {
        "name": "OpenAI Agents SDK",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "OpenAI Agents SDK (Swarm 후속 공식 SDK) — Runner.run() RunResult.new_items의 ToolCallItem → tool_calls; raw_responses[].usage 합산 → tokens_used",
    },
    "google_adk": {
        "name": "Google ADK",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Google Agent Development Kit — Event.get_function_calls() → tool_calls; Event.usage_metadata(gemini와 동일 필드) → tokens_used. 세션 마지막 Event를 반환해야 함",
    },
    "claude_agent_sdk": {
        "name": "Claude Agent SDK",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Claude Agent SDK (구 Claude Code SDK) — AssistantMessage.content의 ToolUseBlock → tool_calls; ResultMessage.usage/total_cost_usd → tokens_used/extra",
    },
}


# ---------------------------------------------------------------------------
# Item G: chain_steps 지원 여부 프레임워크 집합
# ---------------------------------------------------------------------------
_CHAIN_STEPS_SUPPORTED: frozenset = frozenset({
    "langchain", "langgraph", "dspy", "pydanticai",
    "llamaindex", "haystack", "cohere", "semantic_kernel",
})

# ---------------------------------------------------------------------------
# Item Z: 서브모듈까지 검증하는 설치 여부 확인 헬퍼
# ---------------------------------------------------------------------------
_FRAMEWORK_SUBMODULE_MAP: dict[str, tuple] = {
    "langchain": ("langchain", "langchain.agents"),
    "crewai": ("crewai",),
    "autogen": ("autogen",),
    "dspy": ("dspy",),
    "pydanticai": ("pydantic_ai",),
    "llamaindex": ("llama_index",),
    "haystack": ("haystack",),
}

_FRAMEWORK_PACKAGE_MAP_GLOBAL: dict[str, str] = {
    "langchain": "langchain",
    "langgraph": "langgraph",
    "crewai": "crewai",
    "autogen": "autogen",
    "dspy": "dspy",
    "pydanticai": "pydantic_ai",
    "anthropic": "anthropic",
    "openai": "openai",
    "gemini": "google.generativeai",
    "llamaindex": "llama_index",
    "haystack": "haystack",
    "vertexai": "vertexai",
    "ollama": "ollama",
    "cohere": "cohere",
    "groq": "groq",
    "mistral": "mistralai",
    "bedrock": "boto3",
    "smolagents": "smolagents",
    "semantic_kernel": "semantic_kernel",
    "vllm": "vllm",
    "huggingface": "transformers",
}


def _check_framework_installed(framework: str) -> bool:
    """핵심 서브모듈까지 검증하는 프레임워크 설치 여부 확인 (Item Z).

    ``_FRAMEWORK_SUBMODULE_MAP`` 에 등록된 프레임워크는 모든 서브모듈의
    존재 여부를 확인하고, 미등록 프레임워크는 단순 패키지명으로 확인한다.

    Args:
        framework: 프레임워크 식별자.

    Returns:
        모든 필수 모듈이 설치되어 있으면 ``True``, 그렇지 않으면 ``False``.
    """
    import importlib.util as _ilu

    pkgs: tuple
    if framework in _FRAMEWORK_SUBMODULE_MAP:
        pkgs = _FRAMEWORK_SUBMODULE_MAP[framework]
    else:
        _single = _FRAMEWORK_PACKAGE_MAP_GLOBAL.get(framework, framework)
        pkgs = (_single,) if _single else ()

    if not pkgs:
        return False

    for _p in pkgs:
        try:
            if _ilu.find_spec(_p) is None:
                return False
        except (ValueError, ModuleNotFoundError):
            return False
    return True


def get_framework_info(framework: str) -> dict[str, Any] | None:
    """지원 프레임워크 어댑터 메타데이터를 반환한다.

    C6: ``_FRAMEWORK_ADAPTER_META`` 레지스트리 조회 함수.
    V: ``is_installed`` 필드를 동적으로 계산해 추가한다.
    Item G: ``supports_chain_steps`` 필드 추가.
    Item Z: 서브모듈까지 검증하는 ``_check_framework_installed()`` 사용.

    Args:
        framework: 프레임워크 이름 (예: ``"langchain"``, ``"openai"``).

    Returns:
        메타데이터 dict (``is_installed``, ``supports_chain_steps`` 필드 포함) 또는
        지원하지 않는 경우 ``None``.

    Example::

        from agent_evaluator.decorators import get_framework_info

        info = get_framework_info("langgraph")
        # {"name": "LangGraph", "extras": "langchain", "extracts": [...],
        #  "is_installed": True, "supports_chain_steps": True, ...}
    """
    meta = _FRAMEWORK_ADAPTER_META.get(framework)
    if meta is None:
        return None
    # V + Item Z: is_installed — 서브모듈까지 검증
    _is_installed = _check_framework_installed(framework)
    result = dict(meta)
    result["is_installed"] = _is_installed
    # Item G: chain_steps 추출 지원 여부
    result["supports_chain_steps"] = framework in _CHAIN_STEPS_SUPPORTED
    return result


# ---------------------------------------------------------------------------
# Task 5: SimpleTaskAlertRule — TaskResult 기반 경량 알림 규칙
# ---------------------------------------------------------------------------

@dataclass
class SimpleTaskAlertRule:
    """``@agent_eval(alert_rules=[...])`` 에 전달하는 TaskResult 기반 알림 규칙.

    ``AlertEngine`` 과 달리 ``StreamingEvaluator`` 없이도 동작한다.
    각 ``TaskResult`` 기록 직후 ``condition`` 을 평가해 임계값 위반 시
    ``handler`` 를 호출한다.

    Args:
        name: 규칙 이름.
        condition: ``(TaskResult) -> bool`` — True 반환 시 알림 발생.
        handler: ``(message: str, task_result: TaskResult) -> None`` — 알림 처리 함수.
        severity: ``"warning"`` 또는 ``"critical"``.
        cooldown: 동일 규칙 재발화 방지 쿨다운(초). Default 60.

    Example::

        from agent_evaluator import SimpleTaskAlertRule, agent_eval

        def slack_alert(msg, result):
            requests.post(WEBHOOK, json={"text": msg})

        @agent_eval(
            monitor,
            task_type="qa",
            alert_rules=[
                SimpleTaskAlertRule(
                    name="정확도 급락",
                    condition=lambda r: r.accuracy_score < 0.7,
                    handler=slack_alert,
                    severity="warning",
                ),
                SimpleTaskAlertRule(
                    name="응답 지연",
                    condition=lambda r: r.execution_time > 5.0,
                    handler=slack_alert,
                    severity="critical",
                ),
            ]
        )
        def my_agent(question, ground_truth=""): ...
    """

    name: str
    condition: Callable[..., bool]
    handler: Callable[[str, Any], None]
    severity: str = "warning"
    cooldown: float = 60.0
    class_level_cooldown: bool = False  # D3: True 이면 같은 이름의 모든 인스턴스 공유 쿨다운
    _last_fired: float = field(default=0.0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        # D3: 클래스 수준 공유 쿨다운 dict 는 클래스 변수로 관리
        if not hasattr(SimpleTaskAlertRule, "_SHARED_COOLDOWN"):
            SimpleTaskAlertRule._SHARED_COOLDOWN: dict[str, float] = {}
            SimpleTaskAlertRule._SHARED_COOLDOWN_LOCK: threading.Lock = threading.Lock()
        # E2: alert history 초기화
        self._history: list[dict[str, Any]] = []
        self._history_lock = threading.Lock()

    def evaluate(self, task_result: Any) -> None:
        """TaskResult 를 평가해 조건 충족 시 핸들러 호출."""
        import time as _time
        # D3: class_level_cooldown — 같은 이름의 모든 인스턴스 공유 쿨다운
        if self.class_level_cooldown:
            with SimpleTaskAlertRule._SHARED_COOLDOWN_LOCK:
                _last = SimpleTaskAlertRule._SHARED_COOLDOWN.get(self.name, 0.0)
                if (_time.time() - _last) < self.cooldown:
                    return
        with self._lock:
            if not self.class_level_cooldown and (_time.time() - self._last_fired) < self.cooldown:
                return
        try:
            triggered = self.condition(task_result)
        except Exception as e:
            logger.debug("SimpleTaskAlertRule '%s' condition failed (ignored): %s", self.name, e)
            return
        if not triggered:
            return
        _now = _time.time()
        with self._lock:
            self._last_fired = _now
        if self.class_level_cooldown:
            with SimpleTaskAlertRule._SHARED_COOLDOWN_LOCK:
                SimpleTaskAlertRule._SHARED_COOLDOWN[self.name] = _now
        msg = (
            f"[{self.severity.upper()}] {self.name} | "
            f"task={task_result.task_id} | "
            f"accuracy={getattr(task_result, 'accuracy_score', '?'):.2f} | "
            f"latency={getattr(task_result, 'execution_time', '?'):.2f}s"
        )
        try:
            self.handler(msg, task_result)
        except Exception as e:
            logger.debug("SimpleTaskAlertRule '%s' handler failed (ignored): %s", self.name, e)
        # E2: alert history 기록
        import time as _t_hist
        with self._history_lock:
            self._history.append({
                "timestamp": _t_hist.time(),
                "task_id": getattr(task_result, "task_id", "unknown"),
                "accuracy_score": getattr(task_result, "accuracy_score", None),
                "execution_time": getattr(task_result, "execution_time", None),
                "severity": self.severity,
            })
            # 최대 100개 유지
            if len(self._history) > 100:
                self._history = self._history[-100:]

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """최근 발동 이력 반환 (최신순)."""
        with self._history_lock:
            return list(reversed(self._history[-limit:]))

    def clear_history(self) -> None:
        """발동 이력 초기화."""
        with self._history_lock:
            self._history.clear()

    def dry_run(self, task_result: Any) -> dict[str, Any]:
        """핸들러를 실제로 실행하지 않고 알림 발화 여부를 확인한다 (F2).

        Args:
            task_result: 평가할 :class:`TaskResult` 인스턴스.

        Returns:
            ``{"name": str, "would_fire": bool, "message": str | None, "error": str | None}``

        Example::

            rule = SimpleTaskAlertRule("slow", lambda r: r.execution_time > 5.0, handler)
            result = rule.dry_run(task)
            if result["would_fire"]:
                print(f"Rule would fire: {result['message']}")
        """
        try:
            would_fire = bool(self.condition(task_result))
        except Exception as e:
            return {"name": self.name, "would_fire": False, "message": None, "error": str(e)}

        msg: str | None = None
        if would_fire:
            msg = (
                f"[{self.severity.upper()}] {self.name} | "
                f"task={getattr(task_result, 'task_id', '?')} | "
                f"accuracy={getattr(task_result, 'accuracy_score', 0.0):.2f} | "
                f"latency={getattr(task_result, 'execution_time', 0.0):.2f}s"
            )
        return {"name": self.name, "would_fire": would_fire, "message": msg, "error": None}


class AlertRuleBuilder:
    """E6: ``SimpleTaskAlertRule`` 생성을 위한 빌더 — 자주 쓰이는 조건을 팩토리 메서드로 제공.

    Example::

        rule = AlertRuleBuilder.when_accuracy_below(0.7, handler=my_handler)
        rule2 = AlertRuleBuilder.when_latency_above(5.0)

        @agent_eval(monitor, task_type="qa", alert_rules=[rule, rule2])
        def my_agent(question, ground_truth=""): ...
    """

    @staticmethod
    def when_accuracy_below(
        threshold: float,
        handler: Callable | None = None,
        severity: str = "warning",
        cooldown: float = 0.0,
        name: str | None = None,
    ) -> SimpleTaskAlertRule:
        """accuracy_score < threshold 일 때 발화하는 규칙."""
        _name = name or f"accuracy_below_{threshold}"
        _handler = handler or (lambda msg, tr: logger.warning(msg))
        return SimpleTaskAlertRule(
            name=_name,
            condition=lambda tr: getattr(tr, "accuracy_score", 1.0) < threshold,
            handler=_handler,
            severity=severity,
            cooldown=cooldown,
        )

    @staticmethod
    def when_latency_above(
        threshold_seconds: float,
        handler: Callable | None = None,
        severity: str = "warning",
        cooldown: float = 0.0,
        name: str | None = None,
    ) -> SimpleTaskAlertRule:
        """execution_time > threshold_seconds 일 때 발화하는 규칙."""
        _name = name or f"latency_above_{threshold_seconds}s"
        _handler = handler or (lambda msg, tr: logger.warning(msg))
        return SimpleTaskAlertRule(
            name=_name,
            condition=lambda tr: getattr(tr, "execution_time", 0.0) > threshold_seconds,
            handler=_handler,
            severity=severity,
            cooldown=cooldown,
        )

    @staticmethod
    def when_completion_below(
        threshold: float,
        handler: Callable | None = None,
        severity: str = "warning",
        cooldown: float = 0.0,
        name: str | None = None,
    ) -> SimpleTaskAlertRule:
        """completion_score < threshold 일 때 발화하는 규칙."""
        _name = name or f"completion_below_{threshold}"
        _handler = handler or (lambda msg, tr: logger.warning(msg))
        return SimpleTaskAlertRule(
            name=_name,
            condition=lambda tr: getattr(tr, "completion_score", 1.0) < threshold,
            handler=_handler,
            severity=severity,
            cooldown=cooldown,
        )

    @staticmethod
    def when_error(
        handler: Callable | None = None,
        severity: str = "error",
        cooldown: float = 0.0,
        name: str = "task_error",
    ) -> SimpleTaskAlertRule:
        """태스크 오류 발생 시 발화하는 규칙."""
        _handler = handler or (lambda msg, tr: logger.error(msg))
        return SimpleTaskAlertRule(
            name=name,
            condition=lambda tr: bool(getattr(tr, "errors", [])),
            handler=_handler,
            severity=severity,
            cooldown=cooldown,
        )

    @staticmethod
    def when_tool_calls_exceed(
        max_calls: int,
        handler: Callable | None = None,
        severity: str = "warning",
        cooldown: float = 0.0,
        name: str | None = None,
    ) -> SimpleTaskAlertRule:
        """tool_calls 수 > max_calls 일 때 발화하는 규칙."""
        _name = name or f"tool_calls_exceed_{max_calls}"
        _handler = handler or (lambda msg, tr: logger.warning(msg))
        return SimpleTaskAlertRule(
            name=_name,
            condition=lambda tr: len(getattr(tr, "tool_calls", []) or []) > max_calls,
            handler=_handler,
            severity=severity,
            cooldown=cooldown,
        )


def _make_alert_on_record(
    alert_rules: list[Any],  # duck-typed: only .evaluate(task_result) is ever called
    existing_on_record: Callable | None,
    alert_error_mode: str = "log",
) -> Callable:
    """alert_rules 를 평가하는 on_record 콜백을 생성.

    실행 순서: alert_rules 평가 → on_record 콜백.
    alert_rules가 먼저 실행되고, 그 후 existing_on_record 콜백이 실행된다.

    Args:
        alert_rules: 평가할 SimpleTaskAlertRule 리스트.
        existing_on_record: alert_rules 평가 후 호출할 on_record 콜백.
        alert_error_mode: alert_rules 콜백 예외 처리 방식.
            ``"log"`` (기본): logger.warning으로 기록하고 계속 진행.
            ``"strict"``: 예외를 재발생.
            ``"ignore"``: 예외를 무시.
    """
    def _on_record(task_result: Any) -> None:
        # 실행 순서: alert_rules 평가 → on_record 콜백 (항목 A)
        for rule in alert_rules:
            try:
                rule.evaluate(task_result)
            except Exception as _alert_exc:
                if alert_error_mode == "strict":
                    raise
                elif alert_error_mode == "ignore":
                    pass
                else:  # "log" (기본)
                    logger.warning(
                        "alert_rule '%s' 콜백 예외 (태스크 기록은 계속됨): %s",
                        getattr(rule, "name", repr(rule)),
                        _alert_exc,
                    )
        if existing_on_record is not None:
            try:
                existing_on_record(task_result)
            except Exception as e:
                logger.debug("on_record callback failed (ignored): %s", e)
    return _on_record


# ---------------------------------------------------------------------------
# 내부 헬퍼 — 파라미터 추출
# ---------------------------------------------------------------------------

def _resolve_args(
    sig: inspect.Signature,
    args: tuple,
    kwargs: dict,
    question_arg: str,
    ground_truth_arg: str,
    context_arg: str | None,
    expected_tools_arg: str | None,
    fallback_expected_tools: list[str] | None = None,
) -> tuple[str, str, str | None, list[str] | None]:
    """bound arguments 에서 question / ground_truth / context / expected_tools 를 꺼낸다.

    fallback_expected_tools: 함수 인자에서 expected_tools 를 찾지 못했을 때 사용하는
        데코레이터 수준의 정적 목록 (``@agent_eval(expected_tools=[...])``)。
    """
    try:
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        all_args: dict[str, Any] = dict(bound.arguments)
    except TypeError:
        all_args = {}

    question = all_args.get(question_arg)
    if question is None:
        non_skip = [n for n in sig.parameters if n not in _SKIP_PARAMS]
        question = all_args.get(non_skip[0]) if non_skip else None

    ground_truth = all_args.get(ground_truth_arg, "")
    context = all_args.get(context_arg) if context_arg else None
    expected_tools = all_args.get(expected_tools_arg) if expected_tools_arg else None
    # 함수 인자에 없으면 데코레이터 수준 정적 목록으로 fallback
    if expected_tools is None and fallback_expected_tools is not None:
        expected_tools = fallback_expected_tools

    return (
        str(question) if question is not None else "",
        str(ground_truth) if ground_truth is not None else "",
        str(context) if context is not None else None,
        list(expected_tools) if expected_tools is not None else None,
    )


# ---------------------------------------------------------------------------
# 내부 헬퍼 — 메타데이터 병합 및 TaskResult 생성
# ---------------------------------------------------------------------------

def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _apply_overrides(
    task_result: Any,  # TaskResult (avoid circular import at runtime)
    *,
    decorator_framework: str,
    eval_ctx: _EvalContext | None,
    eval_meta: EvalMetadata | None,
    score_fn: Callable | None,
    completion_fn: Callable | None,
    response: str,
    ground_truth: str,
) -> Any:
    """TaskResult 에 메타데이터를 우선순위 순으로 병합한 새 TaskResult 를 반환.

    우선순위 (높은 순):
      EvalMetadata (tuple return)  >  _EvalContext (thread-local)  >  데코레이터 파라미터  >  자동 계산
    """
    overrides: dict[str, Any] = {}

    # --- 1단계: 데코레이터 파라미터 (가장 낮은 우선순위) ---
    if decorator_framework and decorator_framework != "native":
        overrides["framework"] = decorator_framework

    # --- 2단계: score_fn / completion_fn ---
    if score_fn is not None and response and ground_truth:
        try:
            overrides["accuracy_score"] = _clamp01(float(score_fn(response, ground_truth)))
        except Exception as e:
            logger.debug("score_fn failed (keeping auto-calculated value): %s", e)
    if completion_fn is not None and response and ground_truth:  # B3: score_fn과 동일하게 ground_truth guard 추가
        try:
            overrides["completion_score"] = _clamp01(float(completion_fn(response, ground_truth)))
        except Exception as e:
            logger.debug("completion_fn failed (keeping auto-calculated value): %s", e)

    # --- 3단계: _EvalContext (thread-local) ---
    if eval_ctx is not None:
        for attr in (
            "attempts", "framework", "expected_tools", "tool_calls",
            "agent_interactions", "chain_steps", "graph_traversal",
            "state_transitions", "completion_score", "accuracy_score", "partial_reason",
            "tokens_used",  # Gap J
            "conversation_turns",  # Gap AB
            "llm_judge",           # Gap AC
            "extra",               # Gap AE
            "errors",              # Gap AN
        ):
            val = getattr(eval_ctx, attr, None)
            if val is not None:
                overrides[attr] = val
        # Gap AO: execution_time — None-check separately (0.0 is valid)
        _et_ctx = getattr(eval_ctx, "execution_time", None)
        if _et_ctx is not None:
            overrides["execution_time"] = _et_ctx

    # --- 4단계: EvalMetadata 튜플 (가장 높은 우선순위) ---
    if eval_meta is not None:
        for attr in (
            "attempts", "framework", "expected_tools", "tool_calls",
            "agent_interactions", "chain_steps", "graph_traversal",
            "state_transitions", "completion_score", "accuracy_score", "partial_reason",
            "tokens_used",  # Gap J
            "conversation_turns",  # Gap AB
            "llm_judge",           # Gap AC
            "extra",               # Gap AE
            "errors",              # Gap AN
        ):
            val = getattr(eval_meta, attr, None)
            if val is not None:
                overrides[attr] = val
        # Gap AO: execution_time — None-check separately (0.0 is valid)
        _et_meta = getattr(eval_meta, "execution_time", None)
        if _et_meta is not None:
            overrides["execution_time"] = _et_meta

    # score 범위 보장
    for score_key in ("completion_score", "accuracy_score"):
        if score_key in overrides:
            overrides[score_key] = _clamp01(float(overrides[score_key]))

    if overrides:
        return dataclasses.replace(task_result, **overrides)
    return task_result


def _record_to_monitors(
    monitor_or_list: Union[PerformanceMonitor, list[PerformanceMonitor]],
    task_result: Any,
) -> None:
    """단일 monitor 또는 monitor 리스트 모두에 task_result 를 기록한다 (Gap U)."""
    if isinstance(monitor_or_list, list):
        for m in monitor_or_list:
            try:
                m.record_task(task_result)
            except Exception as exc:
                logger.debug("_record_to_monitors: record_task failed (ignored): %s", exc)
    else:
        monitor_or_list.record_task(task_result)


async def _process_async_judge_targets(targets: list[tuple]) -> None:
    """(SPEC-006 REQ-3/REQ-4) 지연된 judge 대상들을 ``ajudge()``로 처리하고 tracker에 반영한다.

    ``targets`` 의 각 항목은 ``_build_and_record(..., use_async_judge=True, ...)`` 가
    적재한 ``(monitor, llm_judge, task_id, question, response, context)`` 튜플이다.

    ``LLMJudge.ajudge()`` 내부의 ``asyncio.Semaphore``(REQ-1)가 동시 호출 수를 이미
    제한하므로, 여기서는 ``asyncio.gather`` 로 모두 동시에 트리거하기만 하면 된다
    (REQ-4의 옵트인 동시 처리, REQ-3의 단건 처리 모두 이 함수를 공유한다).

    이미 기록된 task를 monitor의 내부 tracker 리스트에서 task_id로 찾아 in-place로
    ``dataclasses.replace(..., llm_judge=result)`` 하는 방식은 이 코드베이스의 기존
    post-record 재평가 패턴(예: BUG-E6 threat_severity/threat_response 재평가)과 동일하다.
    """
    if not targets:
        return

    async def _one(_m: Any, _lj: Any, _tid: str, _q: str, _r: str, _ctx: str | None) -> None:
        try:
            _judge_result = await _lj.ajudge(task_id=_tid, question=_q, response=_r, context=_ctx)
        except Exception as exc:
            logger.debug("SPEC-006: ajudge() 처리 실패 (무시): %s", exc)
            return
        if not _judge_result:
            return
        try:
            _tcr = getattr(_m, "tcr_tracker", None)
            _tlist = getattr(_tcr, "_tasks", None)
            if not _tlist:
                return
            for _idx in range(len(_tlist) - 1, -1, -1):
                if getattr(_tlist[_idx], "task_id", None) == _tid:
                    _tlist[_idx] = dataclasses.replace(_tlist[_idx], llm_judge=_judge_result)
                    # SPEC-014 REQ-4: record_task()와 분리된 await 지점에서 task를 in-place로
                    # 수정하므로, generate_report() 캐시를 명시적으로 무효화해야 한다 — 그렇지
                    # 않으면 이 patch 이전에 캐시된 리포트가 judge 결과 없이 계속 반환될 수 있다.
                    _invalidate_judge = getattr(_m, "invalidate_report_cache", None)
                    if callable(_invalidate_judge):
                        _invalidate_judge()
                    break
        except Exception as exc:
            logger.debug("SPEC-006: ajudge() 결과 반영 실패 (무시): %s", exc)

    await asyncio.gather(*(_one(*t) for t in targets))


def _build_and_record(  # pyright: ignore[reportGeneralTypeIssues]
    # 60+ 파라미터 · 33개 Harness Config 분기를 한 함수에서 처리하는 핵심 경로라
    # pyright가 함수 본문 전체를 "너무 복잡함"으로 분석 포기한다. 서브루틴으로
    # 쪼개는 리팩터링은 이 세션(타입 오탐 수정) 범위 밖 — 동작 변경 없이 억제만 한다.
    monitor: Union[PerformanceMonitor, list[PerformanceMonitor]],
    *,
    task_type: str,
    task_id: str,
    question: str,
    ground_truth: str,
    context: str | None,
    expected_tools_from_arg: list[str] | None,
    elapsed: float,
    raw: Any,
    has_error: bool,
    error_msg: str | None,
    model_name: str,
    framework: str,
    score_fn: Callable | None,
    completion_fn: Callable | None,
    eval_ctx: _EvalContext | None,
    on_record: Callable | None = None,
    on_error: Callable | None = None,   # Gap AK
    custom_parser: Callable[[Any], EvalMetadata | None] | None = None,  # A9
    auto_detect_framework: bool = False,  # C7
    extra_override: dict[str, Any] | None = None,  # A2: chunk-level extras를 TaskResult.extra에 병합
    allow_duplicate_task_ids: bool = True,  # A5: False이면 중복 task_id 감지 시 UserWarning
    enable_hallucination: bool = False,  # G4: 이 호출에서만 hallucination detection 강제 활성화
    enable_llm_judge: bool = False,        # E1: 이 호출에서만 LLM Judge 강제 활성화
    judge_model: str | None = None,     # E1: LLM Judge 모델 임시 지정
    judge_criteria: list[str] | None = None,  # J1: G-Eval 기준 임시 지정 (DeepEval 대체)
    judge_sample_rate: float | None = None,  # J2: sample_rate 임시 지정
    judge_escalation_model: str | None = None,  # E4: 저점수 재채점용 상위 모델
    judge_escalation_threshold: float = 2.5,       # E4: 재채점 트리거 점수 임계값 (0–5)
    judge_budget_per_day: float | None = None,  # E5: 일일 비용 상한 (USD)
    judge_budget_storage_path: str | None = None,  # E5: 예산 누적 파일 경로
    judge_max_context_chars: int = 4000,           # E5: RAG context 잘림 한도
    judge_seed: int | None = None,              # E5: 샘플링 재현성 시드
    security_mode: bool = False,              # E3: 이 호출에서만 security metrics 강제 활성화
    allowed_tools: list[str] | None = None,    # E3: 허용된 도구 목록 임시 주입
    restricted_tools: list[str] | None = None,   # E3: 금지된 도구 목록 임시 주입
    security_sample_rate: float | None = None,   # E3: 보안 트래커 샘플링 비율 임시 주입
    enable_anomaly_detection: bool = False,  # A2: 이 호출에서만 anomaly detection 임시 활성화
    enable_quality_evaluation: bool = False,  # P2-B: 이 호출에서만 품질 평가 강제 활성화
    # v0.9.0+: Phase 1 Harness Config
    instructions: InstructionConfig | None = None,
    loop_detection: LoopDetectionConfig | None = None,
    goal_alignment: GoalAlignmentConfig | None = None,
    reproducibility: ReproducibilityConfig | None = None,
    reproducibility_responses: list[str] | None = None,
    fault_tolerance: FaultToleranceConfig | None = None,
    plan_tracking: PlanConfig | None = None,
    # v0.9.1+: 신규 Harness Config
    sla: SLAConfig | None = None,
    threat_severity: ThreatSeverityConfig | None = None,
    efficiency: EfficiencyConfig | None = None,
    state_consistency_before: dict[str, Any] | None = None,
    state_consistency_after: dict[str, Any] | None = None,
    state_consistency: StateConsistencyConfig | None = None,
    deadlock: DeadlockConfig | None = None,
    observability: ObservabilityConfig | None = None,
    consensus: ConsensusConfig | None = None,
    consensus_responses: list[str] | None = None,
    # v0.9.2+: Phase 3 Harness Config
    scope: ScopeConfig | None = None,
    context_retention: ContextRetentionConfig | None = None,
    explainability: ExplainabilityConfig | None = None,
    subtask_tracking: SubtaskConfig | None = None,
    propagation: PropagationConfig | None = None,
    context_retention_text: str | None = None,  # 추출된 context 인자 값
    # v0.9.3+: Phase 4 Harness Config
    agent_role: AgentRoleConfig | None = None,
    graceful_degradation: GracefulDegradationConfig | None = None,
    compliance: ComplianceConfig | None = None,
    resource_budget: ResourceBudgetConfig | None = None,
    conflict_resolution: ConflictResolutionConfig | None = None,
    # v0.9.4+: Phase 5 Harness Config
    tool_parameter_safety: ToolParameterSafetyConfig | None = None,
    knowledge_retention: KnowledgeRetentionConfig | None = None,
    retry_consistency: RetryConsistencyConfig | None = None,
    error_diagnosis: ErrorDiagnosisConfig | None = None,
    # v0.9.5+: Phase 6 Harness Config
    idempotency: IdempotencyConfig | None = None,
    threat_response: ThreatResponseConfig | None = None,
    context_window: ContextWindowConfig | None = None,
    latency_attribution: LatencyAttributionConfig | None = None,
    # SPEC-006 REQ-3/REQ-4: 비동기 경로에서 동기 judge() 대신 ajudge()를 사용하기 위한 배선.
    # True이면 이 호출 동안 monitor(s)의 enable_llm_judge를 일시 억제해 record_task() 내부의
    # 동기 judge() 호출을 막고, 대신 (monitor, task_id, question, response, context) 튜플을
    # async_judge_targets 리스트(호출자가 전달한 mutable 리스트)에 적재한다. 호출자는 이후
    # await _process_async_judge_targets(async_judge_targets) 로 ajudge() 기반 처리를 수행한다.
    use_async_judge: bool = False,
    async_judge_targets: list[Any] | None = None,
) -> Any | None:
    """TaskResult 를 생성·병합·기록하는 공통 로직. sync/async/streaming/Gemini wrapper 양쪽에서 호출."""
    try:
        from agent_evaluator.helpers.taskresult_helpers import (
            create_taskresult_from_execution,
        )

        # A5: task_id 중복 감지 (allow_duplicate_task_ids=False 일 때)
        if not allow_duplicate_task_ids:
            _monitors = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors:
                try:
                    _existing_ids = {t.task_id for t in (_m.tasks or [])}
                    if task_id in _existing_ids:
                        import warnings
                        warnings.warn(
                            f"Duplicate task_id detected: '{task_id}'. "
                            "Set allow_duplicate_task_ids=True to suppress this warning.",
                            UserWarning,
                            stacklevel=4,
                        )
                        break
                except Exception:
                    pass

        raw_result, eval_meta = _split_raw(raw)

        # Task 4: TaskType Enum 정규화
        task_type = _normalize_task_type(task_type)

        # A9: custom_parser — framework adapter보다 먼저, EvalMetadata 튜플 반환보다 낮은 우선순위
        if custom_parser is not None and eval_meta is None and not has_error:
            try:
                _custom_meta = custom_parser(raw_result)
                if _custom_meta is not None:
                    eval_meta = _custom_meta
                    logger.debug("custom_parser applied")
            except Exception as _cp_exc:
                logger.debug("custom_parser failed (ignored): %s", _cp_exc)

        # C7: auto_detect_framework — framework="native"/"auto"/None 이고 auto_detect_framework=True 이면
        # 응답 객체 타입/속성으로 프레임워크 자동 감지
        effective_framework = framework if framework not in (None, "auto") else "native"
        if auto_detect_framework and framework in ("native", "auto", None) and not has_error:
            _detected = _auto_detect_framework(raw_result)
            if _detected:
                effective_framework = _detected
                logger.debug("Auto-detected framework: %s", _detected)

        # Task 1: 프레임워크 어댑터 자동 적용
        # EvalMetadata 튜플 반환이나 eval_ctx 수동 주입이 없는 경우에만 어댑터 실행.
        # eval_ctx가 실질 데이터를 담고 있지 않으면(tool_calls=None 등) 어댑터로 보강.
        # H: _FRAMEWORK_ADAPTERS[framework] 가 None(예: "native")이면 어댑터 건너뜀
        _adapter_fn = _FRAMEWORK_ADAPTERS.get(effective_framework)
        if _adapter_fn is not None and effective_framework in _FRAMEWORK_ADAPTERS and not has_error:
            _ctx_has_data = eval_ctx is not None and any(
                getattr(eval_ctx, f, None) is not None
                for f in ("tool_calls", "chain_steps", "graph_traversal",
                          "agent_interactions", "conversation_turns", "state_transitions")
            )
            if eval_meta is None and not _ctx_has_data:
                # C8: _safe_adapter_call — 어댑터 에러를 안전하게 포착하고 extra에 기록
                _adapter_meta, _adapter_err = _safe_adapter_call(
                    _adapter_fn, raw_result, effective_framework
                )
                if _adapter_meta is not None:
                    eval_meta = _adapter_meta
                    logger.debug("Framework adapter '%s' auto-applied", effective_framework)
                elif _adapter_err is not None:
                    logger.debug("Framework adapter '%s' failed: %s", effective_framework, _adapter_err)
                    # B4: 어댑터 실패 기록 — extra_override에 병합하여 TaskResult.extra에 저장
                    if extra_override is None:
                        extra_override = {}
                    extra_override["adapter_error_fallback"] = {
                        "framework": effective_framework,
                        "error": _adapter_err,
                    }

        # Phase 2: Plugin Registry — FrameworkAdapterPlugin fallback
        # built-in 어댑터가 아무것도 설정하지 못했을 때 플러그인 어댑터를 시도
        if eval_meta is None and not has_error:
            try:
                from .plugin_registry import PluginRegistry as _PR  # type: ignore[import-not-found]
                if _PR.list_framework_plugins():
                    _plg_fw, _plg_meta = _PR.detect_and_extract(raw_result)
                    if _plg_meta is not None:
                        eval_meta = _plg_meta
                        if effective_framework in (None, "native", "auto"):
                            effective_framework = _plg_fw
                        logger.debug("PluginRegistry framework adapter '%s' applied", _plg_fw)
            except Exception as _pr_exc:
                logger.debug("PluginRegistry framework adapter failed (ignored): %s", _pr_exc)

        response = _extract_response(raw_result)  # has_error 시에도 partial content 보존
        openai_resp = raw_result if _is_openai_response(raw_result) else None
        anthropic_resp = raw_result if _is_anthropic_response(raw_result) else None
        lc_resp = raw_result if _is_langchain_response(raw_result) else None
        gemini_resp = raw_result if _is_gemini_response(raw_result) else None
        cohere_resp = raw_result if _is_cohere_response(raw_result) else None  # Gap O

        # Gap J: model_name — EvalMetadata > eval_ctx > decorator 파라미터
        # (model_name 은 TaskResult 필드가 아니므로 create 시점에 결정)
        effective_model = model_name
        if eval_ctx is not None and getattr(eval_ctx, "model_name", None):
            effective_model = eval_ctx.model_name
        if eval_meta is not None and getattr(eval_meta, "model_name", None):
            effective_model = eval_meta.model_name

        # Gap P: context / ground_truth 동적 재정의 — eval_ctx → eval_meta 우선순위
        effective_context = context
        effective_ground_truth = ground_truth
        if eval_ctx is not None:
            if getattr(eval_ctx, "context", None) is not None:
                effective_context = eval_ctx.context
            if getattr(eval_ctx, "ground_truth", None) is not None:
                effective_ground_truth = eval_ctx.ground_truth
        if eval_meta is not None:
            if getattr(eval_meta, "context", None) is not None:
                effective_context = eval_meta.context
            if getattr(eval_meta, "ground_truth", None) is not None:
                effective_ground_truth = eval_meta.ground_truth

        # G5: partial_reason 자동 생성
        _partial_reason: str | None = None
        if has_error:
            _partial_reason = "execution_error"
        elif not raw_result and not isinstance(raw_result, (int, float, bool)):
            _partial_reason = "empty_response"

        task_result = create_taskresult_from_execution(
            task_id=task_id,
            question=question,
            response=response,
            ground_truth=effective_ground_truth,
            execution_time=elapsed,
            openai_response=openai_resp,
            langchain_result=lc_resp,
            has_error=has_error,
            error_message=error_msg,
            task_type=task_type,
            context=effective_context,
            model_name=effective_model,
            partial_reason=_partial_reason,
            use_korean_tokenizer=getattr(monitor, "_use_korean_tokenizer", False),
        )

        # Anthropic 응답 토큰 주입 (create_taskresult_from_execution 는 Anthropic 미지원)
        # 항상 override — Anthropic exact 토큰 수가 휴리스틱보다 정확
        if anthropic_resp is not None:
            ant_tokens = _extract_anthropic_tokens(anthropic_resp)
            if ant_tokens is not None:
                task_result = dataclasses.replace(task_result, tokens_used=ant_tokens)

        # Gemini 응답 토큰 주입
        if gemini_resp is not None:
            gem_tokens = _extract_gemini_tokens(gemini_resp)
            if gem_tokens is not None:
                task_result = dataclasses.replace(task_result, tokens_used=gem_tokens)

        # Cohere 응답 토큰 주입 (Gap O)
        if cohere_resp is not None:
            coh_tokens = _extract_cohere_tokens(cohere_resp)
            if coh_tokens is not None:
                task_result = dataclasses.replace(task_result, tokens_used=coh_tokens)

        # expected_tools: EvalMetadata > eval_ctx > decorator arg 순
        # _apply_overrides 가 처리하지 못하는 경우를 대비해 arg를 먼저 주입
        if expected_tools_from_arg is not None and task_result.expected_tools is None:
            task_result = dataclasses.replace(task_result, expected_tools=expected_tools_from_arg)

        task_result = _apply_overrides(
            task_result,
            decorator_framework=effective_framework,
            eval_ctx=eval_ctx,
            eval_meta=eval_meta,
            score_fn=score_fn,
            completion_fn=completion_fn,
            response=response,
            ground_truth=ground_truth,
        )

        # Gap J: EvalMetadata.tokens_used 가 tokens_used 를 override 한 경우
        # effective_model 이 있어도 "model" 키가 사라질 수 있으므로 재주입
        if effective_model and isinstance(task_result.tokens_used, dict):
            if "model" not in task_result.tokens_used:
                updated_tokens = dict(task_result.tokens_used)
                updated_tokens["model"] = effective_model
                task_result = dataclasses.replace(task_result, tokens_used=updated_tokens)

        # Item F: chain_steps normalization — None → [], tool_calls → chain_steps fallback
        _cs = task_result.chain_steps if task_result.chain_steps is not None else []
        if not _cs and task_result.tool_calls:
            _cs = [
                {
                    "name": (tc.get("name", "unknown") if isinstance(tc, dict) else str(tc)),
                    "type": "tool_call",
                    "output": str(tc.get("args", "") if isinstance(tc, dict) else "")[:200],
                    "success": True,
                }
                for tc in task_result.tool_calls
            ]
        # Item J: chain_steps 유효성 검증 — dict가 아니거나 'name' 필드 없는 항목 제거
        _valid_cs: list[dict[str, Any]] = []
        for _step in _cs:
            if not isinstance(_step, dict):
                logger.warning("chain_steps item is not a dict (ignored): %s", type(_step).__name__)
                continue
            if "name" not in _step:
                logger.warning("chain_steps item missing 'name' field (ignored): %s", list(_step.keys()))
                continue
            _valid_cs.append(_step)
        _cs = _valid_cs
        if _cs != task_result.chain_steps:
            task_result = dataclasses.replace(task_result, chain_steps=_cs)

        # A2: extra_override — chunk-level streaming metrics 등 caller-side extras를 TaskResult.extra에 병합
        if extra_override:
            _existing_extra: dict[str, Any] = dict(task_result.extra) if task_result.extra else {}
            _existing_extra.update(extra_override)
            task_result = dataclasses.replace(task_result, extra=_existing_extra)

        # v0.9.0+: Phase 1 Harness Config 평가
        _p1_extra: dict[str, Any] = {}

        if instructions is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_instruction_adherence
                _raw_response = task_result.response or ""
                _instr_result = eval_instruction_adherence(_raw_response, instructions)
                _p1_extra["instruction_adherence"] = _instr_result
                # fail_on_violation=True → success=False
                if instructions.fail_on_violation and _instr_result.get("violation_count", 0) > 0:
                    task_result = dataclasses.replace(task_result, success=False)
            except Exception as _e:
                logger.debug("instruction_adherence evaluation failed (ignored): %s", _e)

        if loop_detection is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_loop_detection
                _ld_calls = task_result.tool_calls or []
                _ld_chain = task_result.extra.get("chain_steps") if task_result.extra else None
                # check_response_loop: 이전 응답과 유사도 비교를 위해 최근 응답 목록 전달
                _ld_response = task_result.response if task_result.response else None
                _ld_prev_responses: list = []
                if getattr(loop_detection, "check_response_loop", False):
                    _mon = monitor if not isinstance(monitor, list) else (monitor[0] if monitor else None)
                    if _mon is not None:
                        _ld_prev_responses = [
                            str(t.response) for t in list(getattr(_mon, "tasks", []))[-10:]
                            if t.response is not None
                        ]
                _ld_result = eval_loop_detection(
                    _ld_calls, _ld_chain, loop_detection,
                    response=_ld_response, previous_responses=_ld_prev_responses,
                )
                _p1_extra["loop_detection"] = _ld_result
                # on_loop_detected: "fail" → success=False, "warn" → logger 경고
                _on_loop = getattr(loop_detection, "on_loop_detected", "record")
                if _ld_result.get("detected"):
                    if _on_loop == "fail":
                        task_result = dataclasses.replace(task_result, success=False)
                    elif _on_loop == "warn":
                        logger.warning(
                            "Loop detected (task_id=%s): %s at step %s",
                            getattr(task_result, "task_id", "?"),
                            _ld_result.get("loop_type"),
                            _ld_result.get("loop_at_step"),
                        )
            except Exception as _e:
                logger.debug("loop_detection evaluation failed (ignored): %s", _e)

        if goal_alignment is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_goal_alignment
                _ga_calls = task_result.tool_calls or []
                _ga_result = eval_goal_alignment(question, _ga_calls, goal_alignment)
                if _ga_result is not None:
                    _p1_extra["goal_alignment"] = _ga_result
            except Exception as _e:
                logger.debug("goal_alignment evaluation failed (ignored): %s", _e)

        if reproducibility is not None and reproducibility_responses is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import compute_reproducibility_score
                _repro_result = compute_reproducibility_score(
                    reproducibility_responses, reproducibility.similarity_measure
                )
                _p1_extra["reproducibility"] = _repro_result
                if (
                    reproducibility.fail_on_low_reproducibility
                    and _repro_result["score"] < reproducibility.reproducibility_threshold
                ):
                    task_result = dataclasses.replace(task_result, success=False)
            except Exception as _e:
                logger.debug("reproducibility evaluation failed (ignored): %s", _e)

        if fault_tolerance is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_fault_tolerance
                _ft_calls = task_result.tool_calls or []
                _ft_result = eval_fault_tolerance(_ft_calls, fault_tolerance)
                _p1_extra["fault_tolerance"] = _ft_result
            except Exception as _e:
                logger.debug("fault_tolerance evaluation failed (ignored): %s", _e)

        if plan_tracking is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_plan_coherence
                _raw_response = task_result.response or ""
                _plan_result = eval_plan_coherence(_raw_response, question, plan_tracking)
                if _plan_result is not None:
                    _p1_extra["plan_coherence"] = _plan_result
            except Exception as _e:
                logger.debug("plan_coherence evaluation failed (ignored): %s", _e)

        if _p1_extra:
            _existing = dict(task_result.extra or {})
            _existing.update(_p1_extra)
            task_result = dataclasses.replace(task_result, extra=_existing)

        # v0.9.1+: 신규 Harness Config 평가
        _harness_extra: dict[str, Any] = {}

        if sla is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_sla
                _cost = None
                _ttft = None
                if task_result.extra:
                    _cost = task_result.extra.get("cost_usd") or (
                        task_result.extra.get("llm_judge", {}).get("cost_usd")
                        if isinstance(task_result.extra.get("llm_judge"), dict) else None
                    )
                    # ttft_ms가 extra에 있으면 SLA TTFT 검사에 사용
                    _raw_ttft = task_result.extra.get("ttft_ms") or task_result.extra.get("ttft")
                    if _raw_ttft is not None:
                        try:
                            _ttft = float(_raw_ttft)
                        except (TypeError, ValueError):
                            pass
                _sla_result = eval_sla(
                    task_result.execution_time or elapsed,
                    task_result.tokens_used or 0,
                    _cost,
                    sla,
                    ttft_ms=_ttft,
                )
                _harness_extra["sla"] = _sla_result
            except Exception as _e:
                logger.debug("SLAConfig evaluation failed (ignored): %s", _e)

        if threat_severity is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_threat_severity
                _ts_result = eval_threat_severity(
                    dict(task_result.extra) if task_result.extra else {},
                    threat_severity,
                )
                _harness_extra["threat_severity"] = _ts_result
                if _ts_result.get("fail_triggered"):
                    task_result = dataclasses.replace(task_result, success=False)
            except Exception as _e:
                logger.debug("ThreatSeverityConfig evaluation failed (ignored): %s", _e)

        if efficiency is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_efficiency
                _cost_usd = None
                if task_result.extra and isinstance(task_result.extra.get("llm_judge"), dict):
                    _cost_usd = task_result.extra["llm_judge"].get("cost_usd")
                _eff_result = eval_efficiency(
                    task_result.completion_score or 0.0,
                    task_result.tokens_used or 0,
                    task_result.execution_time or elapsed,
                    _cost_usd,
                    efficiency,
                )
                _harness_extra["efficiency"] = _eff_result
            except Exception as _e:
                logger.debug("EfficiencyConfig evaluation failed (ignored): %s", _e)

        if state_consistency is not None and state_consistency_before is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_state_consistency
                _sc_result = eval_state_consistency(
                    state_consistency_before,
                    state_consistency_after,
                    state_consistency,
                )
                if _sc_result is not None:
                    _harness_extra["state_consistency"] = _sc_result
                    # B-15: eval_state_consistency가 반환한 "failed" 키를 직접 사용 — 이중 조건 계산 제거
                    if _sc_result.get("failed"):
                        task_result = dataclasses.replace(task_result, success=False)
            except Exception as _e:
                logger.debug("StateConsistencyConfig evaluation failed (ignored): %s", _e)

        if deadlock is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_deadlock
                # B-53: EvalMetadata.agent_interactions → task_result.agent_interactions (직접 필드),
                # extra dict에는 저장되지 않으므로 직접 필드를 우선 참조.
                _ai = task_result.agent_interactions or (task_result.extra or {}).get("agent_interactions") or []
                _dl_result = eval_deadlock(
                    task_result.tool_calls or [],
                    _ai,
                    deadlock,
                )
                _harness_extra["deadlock"] = _dl_result
                if getattr(deadlock, "fail_on_deadlock", False) and _dl_result.get("deadlock_detected"):
                    task_result = dataclasses.replace(task_result, success=False)
            except Exception as _e:
                logger.debug("DeadlockConfig evaluation failed (ignored): %s", _e)

        if observability is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_observability
                _obs_result = eval_observability(
                    task_result.tool_calls or [],
                    dict(task_result.extra) if task_result.extra else {},
                    task_result.task_id or task_id,
                    task_result.task_type or task_type,
                    task_result.execution_time or elapsed,
                    observability,
                )
                _harness_extra["observability"] = _obs_result
            except Exception as _e:
                logger.debug("ObservabilityConfig evaluation failed (ignored): %s", _e)

        if consensus is not None and consensus_responses:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_consensus
                _cs_result = eval_consensus(
                    consensus_responses,
                    None,
                    consensus,
                )
                _harness_extra["consensus"] = _cs_result
            except Exception as _e:
                logger.debug("ConsensusConfig evaluation failed (ignored): %s", _e)

        if _harness_extra:
            _merged_extra: dict[str, Any] = dict(task_result.extra) if task_result.extra else {}
            _merged_extra.update(_harness_extra)
            task_result = dataclasses.replace(task_result, extra=_merged_extra)

        # v0.9.2+: Phase 3 Harness Config 평가
        _p3_extra: dict[str, Any] = {}

        if scope is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_scope
                _scope_result = eval_scope(task_result.tool_calls, scope)
                _p3_extra["scope"] = _scope_result
                if scope.fail_on_violation and not _scope_result["in_scope"]:
                    task_result = dataclasses.replace(task_result, success=False)
            except Exception as _e:
                logger.debug("ScopeConfig evaluation failed (ignored): %s", _e)

        # B-11: ScopeConfig(Gate B)와 AgentRoleConfig(Gate F)가 동일 tool 목록을 정의하면 이중 페널티 발생
        if scope is not None and agent_role is not None:
            _sc_allowed = set(getattr(scope, "allowed_tools", []) or [])
            _sc_forbidden = set(getattr(scope, "forbidden_tools", []) or [])
            _ar_allowed = set(getattr(agent_role, "allowed_tools", []) or [])
            _ar_forbidden = set(getattr(agent_role, "forbidden_tools", []) or [])
            _ov_allowed = _sc_allowed & _ar_allowed
            _ov_forbidden = _sc_forbidden & _ar_forbidden
            if _ov_allowed or _ov_forbidden:
                logger.warning(
                    "ScopeConfig(Gate B)와 AgentRoleConfig(Gate F)에 동일한 tool 목록이 중복 정의되어 "
                    "같은 위반이 Gate B와 Gate F 양쪽에 페널티로 반영됩니다. "
                    "allowed 중복: %s / forbidden 중복: %s",
                    sorted(_ov_allowed) or "없음",
                    sorted(_ov_forbidden) or "없음",
                )

        if context_retention is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_context_retention
                _ctx_text = context_retention_text or ""
                _cr_result = eval_context_retention(
                    task_result.response, task_result.question, _ctx_text, context_retention
                )
                _p3_extra["context_retention"] = _cr_result
            except Exception as _e:
                logger.debug("ContextRetentionConfig evaluation failed (ignored): %s", _e)

        if explainability is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_explainability
                _expl_result = eval_explainability(
                    task_result.response, task_result.tool_calls, explainability
                )
                _p3_extra["explainability"] = _expl_result
            except Exception as _e:
                logger.debug("ExplainabilityConfig evaluation failed (ignored): %s", _e)

        if subtask_tracking is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_subtask_completion
                _sub_result = eval_subtask_completion(
                    task_result.response, task_result.tool_calls, subtask_tracking,
                    question=task_result.question or "",
                )
                _p3_extra["subtask_completion"] = _sub_result
            except Exception as _e:
                logger.debug("SubtaskConfig evaluation failed (ignored): %s", _e)

        if propagation is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_propagation
                # B-53: EvalMetadata.agent_interactions → task_result.agent_interactions 직접 필드 우선 참조
                _agent_interactions = task_result.agent_interactions or (task_result.extra.get("agent_interactions", []) if task_result.extra else [])
                _prop_result = eval_propagation(
                    task_result.response, _agent_interactions, propagation
                )
                _p3_extra["propagation"] = _prop_result
            except Exception as _e:
                logger.debug("PropagationConfig evaluation failed (ignored): %s", _e)

        if _p3_extra:
            _merged_p3: dict[str, Any] = dict(task_result.extra or {})
            _merged_p3.update(_p3_extra)
            task_result = dataclasses.replace(task_result, extra=_merged_p3)

        # v0.9.3+: Phase 4 Harness Config 평가
        _p4_extra: dict[str, Any] = {}

        if agent_role is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_role_adherence
                _p4_extra["agent_role"] = eval_role_adherence(
                    task_result.tool_calls, task_result.response, agent_role
                )
            except Exception as _e:
                logger.debug("AgentRoleConfig evaluation failed (ignored): %s", _e)

        if graceful_degradation is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_graceful_degradation
                _p4_extra["graceful_degradation"] = eval_graceful_degradation(
                    task_result.response,
                    task_result.tool_calls,
                    task_result.errors is not None and len(task_result.errors) > 0,
                    task_result.execution_time * 1000,  # seconds → ms
                    graceful_degradation,
                )
            except Exception as _e:
                logger.debug("GracefulDegradationConfig evaluation failed (ignored): %s", _e)

        if compliance is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_compliance
                _comp_result = eval_compliance(
                    task_result.response, task_result.question, compliance,
                    task_extra=dict(task_result.extra or {}),
                )
                _p4_extra["compliance"] = _comp_result
                if _comp_result.get("fail_triggered"):
                    task_result = dataclasses.replace(task_result, success=False)
            except Exception as _e:
                logger.debug("ComplianceConfig evaluation failed (ignored): %s", _e)

        if resource_budget is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_resource_budget
                _cost = task_result.extra.get("cost_usd", 0.0) if task_result.extra else 0.0
                _rb_tok_dict = task_result.tokens_used or {}
                _rb_total_tok = (
                    int(_rb_tok_dict.get("total") or _rb_tok_dict.get("input", 0) + _rb_tok_dict.get("output", 0))
                    if isinstance(_rb_tok_dict, dict)
                    else int(_rb_tok_dict or 0)
                )
                _p4_extra["resource_budget"] = eval_resource_budget(
                    _rb_total_tok,
                    _cost,
                    task_result.execution_time * 1000,
                    resource_budget,
                    task_succeeded=task_result.success,
                )
            except Exception as _e:
                logger.debug("ResourceBudgetConfig evaluation failed (ignored): %s", _e)

        if conflict_resolution is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_conflict_resolution
                # B-53: EvalMetadata.agent_interactions → task_result.agent_interactions 직접 필드 우선 참조
                _agent_interactions_p4 = (
                    task_result.agent_interactions or (task_result.extra.get("agent_interactions", []) if task_result.extra else [])
                )
                _p4_extra["conflict_resolution"] = eval_conflict_resolution(
                    task_result.response, _agent_interactions_p4, conflict_resolution
                )
            except Exception as _e:
                logger.debug("ConflictResolutionConfig evaluation failed (ignored): %s", _e)

        if _p4_extra:
            _merged_p4: dict[str, Any] = dict(task_result.extra or {})
            _merged_p4.update(_p4_extra)
            task_result = dataclasses.replace(task_result, extra=_merged_p4)

        # v0.9.4+: Phase 5 Harness Config 평가
        _p5_extra: dict[str, Any] = {}

        if tool_parameter_safety is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_tool_parameter_safety
                _tps_result = eval_tool_parameter_safety(
                    task_result.tool_calls, tool_parameter_safety
                )
                _p5_extra["tool_parameter_safety"] = _tps_result
                # fail_on_dangerous=True: 위험 호출 감지 시 태스크 실패로 처리
                if _tps_result.get("fail_task"):
                    task_result = dataclasses.replace(task_result, success=False)
            except Exception as _e:
                logger.debug("ToolParameterSafetyConfig evaluation failed (ignored): %s", _e)

        if knowledge_retention is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_knowledge_retention
                _conv_history = (
                    task_result.extra.get("conversation_history", [])
                    if task_result.extra else []
                )
                _kr_result = eval_knowledge_retention(
                    task_result.response, _conv_history, knowledge_retention
                )
                if _kr_result is not None:
                    _p5_extra["knowledge_retention"] = _kr_result
            except Exception as _e:
                logger.debug("KnowledgeRetentionConfig evaluation failed (ignored): %s", _e)

        if retry_consistency is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_retry_consistency
                _rc_result = eval_retry_consistency(task_result, retry_consistency)
                if _rc_result is not None:
                    _p5_extra["retry_consistency"] = _rc_result
            except Exception as _e:
                logger.debug("RetryConsistencyConfig evaluation failed (ignored): %s", _e)

        if error_diagnosis is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_error_diagnosis
                _ed_result = eval_error_diagnosis(
                    task_result.response,
                    task_result.errors is not None and len(task_result.errors) > 0,
                    task_result.success,
                    error_diagnosis,
                )
                if _ed_result is not None:
                    _p5_extra["error_diagnosis"] = _ed_result
            except Exception as _e:
                logger.debug("ErrorDiagnosisConfig evaluation failed (ignored): %s", _e)

        if _p5_extra:
            _merged_p5: dict[str, Any] = dict(task_result.extra or {})
            _merged_p5.update(_p5_extra)
            task_result = dataclasses.replace(task_result, extra=_merged_p5)

        # ── Phase 6 Harness ──────────────────────────────────────────────────────────
        _p6_extra: dict[str, Any] = {}

        if idempotency is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_idempotency
                _idem_result = eval_idempotency(
                    task_result.tool_calls, task_result.response, idempotency
                )
                _p6_extra["idempotency"] = _idem_result
                if (getattr(idempotency, "warn_on_non_idempotent", True)
                        and _idem_result.get("non_idempotent_count", 0) > 0):
                    logger.warning(
                        "Non-idempotent tools detected in task %s: %s",
                        task_result.task_id,
                        _idem_result.get("non_idempotent_tools", []),
                    )
            except Exception as _e:
                logger.debug("IdempotencyConfig evaluation failed (ignored): %s", _e)

        if threat_response is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_threat_response
                _tr_result = eval_threat_response(
                    task_result.response,
                    task_result.tool_calls,
                    task_result.extra or {},
                    threat_response,
                )
                if _tr_result is not None:
                    _p6_extra["threat_response"] = _tr_result
            except Exception as _e:
                logger.debug("ThreatResponseConfig evaluation failed (ignored): %s", _e)

        if context_window is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_context_window
                _tok_dict = task_result.tokens_used or {}
                if isinstance(_tok_dict, dict):
                    # B-6: is not None 체크 필수 — total=0이 falsy로 처리되어 input+output으로 대체되는 것 방지
                    _raw_total = _tok_dict.get("total")
                    _total_tok = (
                        int(_raw_total) if _raw_total is not None
                        else int(_tok_dict.get("input", 0) + _tok_dict.get("output", 0))
                    )
                else:
                    _total_tok = int(_tok_dict or 0)
                # B-5: 토큰 데이터 없으면 평가 생략 — _total_tok=0이 saturation_score=1.0으로 Gate B를 인플레이션
                if _total_tok > 0:
                    _p6_extra["context_window"] = eval_context_window(
                        task_result.response,
                        _total_tok,
                        context_window,
                    )
                else:
                    # B-55: 묵음 스킵 → debug 로그로 진단 가능하게. context_window 키가 extra에 없어
                    # Gate B에 미기여하는 이유를 사용자가 파악하기 어려우므로 명시적으로 기록.
                    logger.debug(
                        "ContextWindowConfig: task_id=%s 토큰 수=0 — context_window 평가 생략 "
                        "(Gate B 미기여). tokens_used를 EvalMetadata로 전달하면 평가가 활성화됩니다.",
                        getattr(task_result, "task_id", "unknown"),
                    )
            except Exception as _e:
                logger.debug("ContextWindowConfig evaluation failed (ignored): %s", _e)

        if latency_attribution is not None:
            try:
                from agent_evaluator.helpers.taskresult_helpers import eval_latency_attribution
                _p6_extra["latency_attribution"] = eval_latency_attribution(
                    task_result.execution_time * 1000.0,
                    task_result.extra,
                    latency_attribution,
                )
            except Exception as _e:
                logger.debug("LatencyAttributionConfig evaluation failed (ignored): %s", _e)

        if _p6_extra:
            _merged_p6: dict[str, Any] = dict(task_result.extra or {})
            _merged_p6.update(_p6_extra)
            task_result = dataclasses.replace(task_result, extra=_merged_p6)

        # Phase 2: Plugin Registry — MetricPlugin 실행
        # extra_override 병합 후, 최종 extra에 plugin_metrics 추가
        try:
            from .plugin_registry import PluginRegistry as _PR2  # type: ignore[import-not-found]
            if _PR2.list_metric_plugins():
                _plugin_scores = _PR2.compute_all(
                    question=question,
                    response=task_result.response or "",
                    ground_truth=ground_truth or "",
                    context=context or "",
                    task_type=task_type,
                    extra=dict(task_result.extra) if task_result.extra else {},
                )
                if _plugin_scores:
                    _pm_extra: dict[str, Any] = dict(task_result.extra) if task_result.extra else {}
                    _pm_extra["plugin_metrics"] = _plugin_scores
                    task_result = dataclasses.replace(task_result, extra=_pm_extra)
                    logger.debug("MetricPlugin result applied: %s", list(_plugin_scores.keys()))
        except Exception as _pr2_exc:
            logger.debug("PluginRegistry MetricPlugin 실행 실패 (무시): %s", _pr2_exc)

        # H1: LLM Judge가 이 호출에서 활성화될지 미리 계산 (try/finally 이후 back-propagation용)
        _judge_will_be_active = enable_llm_judge or (
            isinstance(monitor, list) and any(getattr(_m, "enable_llm_judge", False) for _m in monitor)
        ) or (
            not isinstance(monitor, list) and getattr(monitor, "enable_llm_judge", False)
        )

        # A2: enable_anomaly_detection — 이 호출 동안만 anomaly detection 임시 활성화
        # (monitor.enable_anomaly_detection는 save_to_file 시 scan 여부를 제어하므로
        #  이 호출 동안 True로 임시 설정하면 기록 후 save 시 이상 탐지 포함)
        _anomaly_restored: list = []
        if enable_anomaly_detection:
            _monitors_a2 = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors_a2:
                if hasattr(_m, "enable_anomaly_detection") and not _m.enable_anomaly_detection:
                    _m.enable_anomaly_detection = True
                    _anomaly_restored.append(_m)

        # G4: enable_hallucination — 이 호출 동안만 hallucination detection 임시 활성화
        _hall_restored: list = []
        if enable_hallucination:
            _monitors_g4 = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors_g4:
                if hasattr(_m, "enable_hallucination_detection") and not _m.enable_hallucination_detection:
                    _m.enable_hallucination_detection = True
                    _hall_restored.append(_m)

        # E1: enable_llm_judge — 이 호출 동안만 LLM Judge 임시 활성화
        # Lazy init: monitor가 enable_llm_judge=False로 생성됐더라도 즉시 초기화
        _llm_judge_restored: list = []
        if enable_llm_judge:
            _monitors_e1 = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors_e1:
                if hasattr(_m, "enable_llm_judge") and not _m.enable_llm_judge:
                    _m.enable_llm_judge = True
                    # Lazy init: llm_judge 인스턴스가 없으면 지금 생성
                    if getattr(_m, "llm_judge", None) is None:
                        try:
                            from agent_evaluator.integrations.llm_judge import LLMJudge as _LJCls
                            _lj_kwargs: dict[str, Any] = {}
                            if judge_model:
                                _lj_kwargs["model"] = judge_model
                            if judge_criteria is not None:
                                _lj_kwargs["judge_criteria"] = judge_criteria
                            if judge_sample_rate is not None:
                                _lj_kwargs["sample_rate"] = judge_sample_rate
                            if judge_escalation_model:
                                _lj_kwargs["escalation_model"] = judge_escalation_model
                            _lj_kwargs["escalation_threshold"] = judge_escalation_threshold
                            if judge_budget_per_day is not None:
                                _lj_kwargs["budget_per_day"] = judge_budget_per_day
                            if judge_budget_storage_path is not None:
                                _lj_kwargs["budget_storage_path"] = judge_budget_storage_path
                            _lj_kwargs["max_context_chars"] = judge_max_context_chars
                            if judge_seed is not None:
                                _lj_kwargs["seed"] = judge_seed
                            _m.llm_judge = _LJCls(**_lj_kwargs)
                            logger.debug("LLM Judge lazy init: model=%s", _m.llm_judge.model)
                            _llm_judge_restored.append((_m, None, True))  # was_lazy=True
                        except Exception as _lj_exc:
                            logger.debug("LLM Judge lazy init 실패: %s", _lj_exc)
                            _m.enable_llm_judge = False
                    else:
                        _orig_judge_model = getattr(_m, "_judge_model", None)
                        if judge_model and hasattr(_m, "_judge_model"):
                            _m._judge_model = judge_model
                        _llm_judge_restored.append((_m, _orig_judge_model, False))

        # SPEC-006 REQ-3: use_async_judge=True이면 이 호출에 한해 monitor(s)의
        # enable_llm_judge를 억제해 record_task() 내부의 동기 judge() 호출을 막는다.
        # (위 E1 블록이 이미 lazy-init을 마쳤으므로 llm_judge 인스턴스는 존재함)
        # 실제 채점은 caller(async_wrapper)가 await ajudge()로 별도 수행한다.
        # llm_judge 인스턴스 자체를 캡처해두는 이유: E1 복원 블록이 was_lazy 케이스에서
        # _m.llm_judge = None 으로 되돌릴 수 있어, 이후 시점에 _m.llm_judge를 다시 읽으면
        # 유실될 수 있기 때문이다.
        _async_judge_deferred: list = []
        if use_async_judge:
            _monitors_req3 = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors_req3:
                _lj_req3 = getattr(_m, "llm_judge", None)
                if getattr(_m, "enable_llm_judge", False) and _lj_req3 is not None:
                    _m.enable_llm_judge = False
                    _async_judge_deferred.append((_m, _lj_req3))

        # J1: judge_criteria — 이 호출 동안만 LLMJudge.judge_criteria 임시 재정의 (G-Eval 대체)
        _judge_criteria_restored: list = []
        if judge_criteria is not None:
            _monitors_j1 = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors_j1:
                _lj = getattr(_m, "llm_judge", None)
                if _lj is not None:
                    _orig_criteria = list(getattr(_lj, "judge_criteria", []))
                    _lj.judge_criteria = list(judge_criteria)
                    _judge_criteria_restored.append((_lj, _orig_criteria))

        # J2: judge_sample_rate — 이 호출 동안만 LLMJudge.sample_rate 임시 재정의
        _judge_sample_rate_restored: list = []
        if judge_sample_rate is not None:
            _monitors_j2 = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors_j2:
                _lj = getattr(_m, "llm_judge", None)
                if _lj is not None:
                    _orig_sample_rate = getattr(_lj, "sample_rate", 1.0)
                    _lj.sample_rate = judge_sample_rate
                    _judge_sample_rate_restored.append((_lj, _orig_sample_rate))

        # E3: security_mode — 이 호출 동안만 security metrics 임시 활성화
        _security_restored: list = []
        if security_mode:
            _monitors_e3 = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors_e3:
                if hasattr(_m, "enable_security_metrics") and not _m.enable_security_metrics:
                    _m.enable_security_metrics = True
                    _security_restored.append(_m)
            # allowed_tools / restricted_tools / sample_rate → security_config 임시 주입
            if allowed_tools or restricted_tools or security_sample_rate is not None:
                for _m in _monitors_e3:
                    if hasattr(_m, "security_config"):
                        _new_cfg = dict(getattr(_m, "security_config", None) or {})
                        if allowed_tools:
                            _new_cfg["allowed_tools"] = allowed_tools
                        if restricted_tools:
                            _new_cfg["restricted_tools"] = restricted_tools
                        if security_sample_rate is not None:
                            _new_cfg["sample_rate"] = security_sample_rate
                        _m.security_config = _new_cfg
                    # sample_rate를 이미 초기화된 트래커 인스턴스에도 직접 전파
                    # (security_config 딕셔너리는 신규 모니터 초기화에만 사용됨)
                    if security_sample_rate is not None:
                        _clamped_sr = max(0.0, min(1.0, float(security_sample_rate)))
                        for _attr in ("input_sanitizer", "output_leakage_detector"):
                            _tracker = getattr(_m, _attr, None)
                            if _tracker is not None and hasattr(_tracker, "_sample_rate"):
                                _tracker._sample_rate = _clamped_sr

        # P2-B: enable_quality_evaluation — 이 호출 동안만 품질 평가 강제 활성화
        _quality_restored: list = []
        if enable_quality_evaluation:
            _monitors_pq = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors_pq:
                if hasattr(_m, "quality_tracker") and hasattr(_m.quality_tracker, "enabled"):
                    if not _m.quality_tracker.enabled:
                        _m.quality_tracker.enabled = True
                        _quality_restored.append(_m.quality_tracker)
                # ResponseQualityEvaluator 가 없더라도 enable_quality_evaluation 플래그 자체 설정
                elif hasattr(_m, "enable_quality_evaluation") and not _m.enable_quality_evaluation:
                    _m.enable_quality_evaluation = True
                    _quality_restored.append(_m)

        try:
            _record_to_monitors(monitor, task_result)  # Gap U: 단일/리스트 모두 지원
        finally:
            # SPEC-006 REQ-3: 이 호출 동안 억제한 enable_llm_judge를 우선 원복(True)한다.
            # E1 복원 블록이 뒤이어 실행되며 자신이 임시로 켠 monitor는 다시 False로
            # 덮어쓰므로, 두 메커니즘이 겹치는 monitor는 최종적으로 E1 규칙을 따른다.
            for _m, _ in _async_judge_deferred:
                _m.enable_llm_judge = True
            # G4: hallucination detection 복원
            for _m in _hall_restored:
                _m.enable_hallucination_detection = False
            # E1: LLM Judge 복원 (was_lazy=True → llm_judge 인스턴스 제거)
            for _restore_tuple in _llm_judge_restored:
                _m, _orig_jm, _was_lazy = _restore_tuple
                _m.enable_llm_judge = False
                if _was_lazy:
                    _m.llm_judge = None  # lazy-init 된 인스턴스 제거
                elif hasattr(_m, "_judge_model"):
                    _m._judge_model = _orig_jm
            # J1: judge_criteria 복원
            for _lj, _orig_criteria in _judge_criteria_restored:
                _lj.judge_criteria = _orig_criteria
            # J2: judge_sample_rate 복원
            for _lj, _orig_sr in _judge_sample_rate_restored:
                _lj.sample_rate = _orig_sr
            # E3: security metrics 복원
            for _m in _security_restored:
                _m.enable_security_metrics = False
            # A2: anomaly detection 복원
            for _m in _anomaly_restored:
                _m.enable_anomaly_detection = False
            # P2-B: quality evaluation 복원
            for _tracker_or_m in _quality_restored:
                if hasattr(_tracker_or_m, "enabled"):
                    _tracker_or_m.enabled = False
                elif hasattr(_tracker_or_m, "enable_quality_evaluation"):
                    _tracker_or_m.enable_quality_evaluation = False

        # SPEC-006 REQ-3/REQ-4: 억제해둔 judge 대상 정보를 호출자에게 전달한다.
        # task_result는 이 시점에 record_task()가 채운 question/response/context를
        # 그대로 담고 있으므로(judge만 억제했을 뿐 나머지 필드는 정상 기록됨), 동기
        # judge()가 사용했을 입력과 동일한 값을 ajudge()에 전달할 수 있다.
        if use_async_judge and async_judge_targets is not None and _async_judge_deferred:
            for _m, _lj in _async_judge_deferred:
                async_judge_targets.append((
                    _m, _lj, task_id,
                    task_result.question, task_result.response, task_result.context,
                ))

        # BUG-E6 fix: ThreatSeverityConfig / ThreatResponseConfig 재평가 (post-record)
        # 문제: eval_threat_severity(line 5218) / eval_threat_response(line 5577)는 하네스 Config
        # 평가 단계에서 실행되는데, 이 시점의 task_result.extra에는 보안 Tracker 결과
        # (input_sanitization, output_leakage 등)가 아직 없다.
        # 보안 Tracker는 _record_to_monitors() → monitor.record_task() 내부에서 실행돼
        # task_result.extra를 채우기 때문이다. 이 때문에 eval_threat_severity는 항상
        # breakdown={}(grade="A", weighted_score=0.0)를 반환하고 Gate E _cvss_normalized가
        # 항상 1.0이 되는 오탐이 발생한다. eval_threat_response도 threat_detected=False로
        # 항상 score_clean_tasks 기본값(1.0)을 반환하거나 None을 반환한다.
        # → _record_to_monitors() 이후 보안 Tracker 결과가 채워진 enriched extra로 재평가.
        if threat_severity is not None or threat_response is not None:
            _monitors_e6 = monitor if isinstance(monitor, list) else [monitor]
            for _m_e6 in _monitors_e6:
                try:
                    _tcr_e6 = getattr(_m_e6, "tcr_tracker", None)
                    _tcr_tasks_e6 = getattr(_tcr_e6, "_tasks", None)
                    if not _tcr_tasks_e6:
                        break
                    _enriched_t_e6 = None
                    for _te in reversed(_tcr_tasks_e6):
                        if getattr(_te, "task_id", None) == task_id:
                            _enriched_t_e6 = _te
                            break
                    if _enriched_t_e6 is None:
                        break
                    _enr_extra = dict(_enriched_t_e6.extra or {})
                    # 보안 Tracker 결과가 없으면 재평가해도 달라지지 않음 — 생략
                    _sec_data_keys = (
                        "input_sanitization", "output_leakage",
                        "privilege_escalation", "tool_chain_attack", "tool_authorization",
                    )
                    if not any(k in _enr_extra for k in _sec_data_keys):
                        break
                    _e6_changed = False
                    _e6_fail = False
                    if threat_severity is not None:
                        try:
                            from agent_evaluator.helpers.taskresult_helpers import (
                                eval_threat_severity as _ets_fn,
                            )
                            _ts_new = _ets_fn(_enr_extra, threat_severity)
                            _enr_extra["threat_severity"] = _ts_new
                            _e6_changed = True
                            if _ts_new.get("fail_triggered"):
                                _e6_fail = True
                        except Exception as _e6_ts:
                            logger.debug("E6 threat_severity re-eval (ignored): %s", _e6_ts)
                    if threat_response is not None:
                        try:
                            from agent_evaluator.helpers.taskresult_helpers import (
                                eval_threat_response as _etr_fn,
                            )
                            _tr_new = _etr_fn(
                                _enriched_t_e6.response,
                                _enriched_t_e6.tool_calls,
                                _enr_extra,
                                threat_response,
                            )
                            if _tr_new is not None:
                                _enr_extra["threat_response"] = _tr_new
                                _e6_changed = True
                        except Exception as _e6_tr:
                            logger.debug("E6 threat_response re-eval (ignored): %s", _e6_tr)
                    if _e6_changed:
                        _enriched_t_e6 = dataclasses.replace(
                            _enriched_t_e6,
                            extra=_enr_extra,
                            success=False if _e6_fail else _enriched_t_e6.success,
                        )
                        _tcr_tasks_e6[-1] = _enriched_t_e6
                        task_result = _enriched_t_e6
                        # SPEC-014 REQ-4: record_task() 이후 task를 in-place로 수정했으므로
                        # generate_report() 캐시를 무효화해 stale한 리포트가 반환되지 않게 한다.
                        _invalidate_e6 = getattr(_m_e6, "invalidate_report_cache", None)
                        if callable(_invalidate_e6):
                            _invalidate_e6()
                except Exception as _e6_outer:
                    logger.debug("E6 post-record re-eval outer error (ignored): %s", _e6_outer)
                break  # 첫 번째 monitor에서만 처리

        # H1: LLM Judge back-propagation — 모니터가 judge 결과를 주입한 enriched TaskResult 가져오기
        # record_task() 내부에서 dataclasses.replace(task_result, llm_judge=result) 후 저장하므로
        # _record_to_monitors() 완료 후 monitor.tasks 에서 llm_judge가 채워진 버전을 조회한다.
        if _judge_will_be_active:
            _monitors_h1 = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors_h1:
                try:
                    _tasks = getattr(_m, "tasks", None)
                    if _tasks:
                        for _t in reversed(_tasks):
                            if getattr(_t, "task_id", None) == task_id and getattr(_t, "llm_judge", None) is not None:
                                task_result = _t
                                break
                except Exception:
                    pass
                break  # 첫 번째 monitor에서 조회 후 종료

        if on_record is not None:
            try:
                _returned = on_record(task_result)
                # Gap H: on_record 가 TaskResult 를 반환하면 교체 (커스텀 오버라이드)
                if _returned is not None and hasattr(_returned, "task_id"):
                    task_result = _returned
                    # D2: on_record 가 반환한 TaskResult 의 점수를 [0,1] 범위로 재검증
                    _fields_to_clamp = ("completion_score", "accuracy_score")
                    _needs_clamp = any(
                        getattr(task_result, f, None) is not None
                        and not (0.0 <= getattr(task_result, f, 0.0) <= 1.0)
                        for f in _fields_to_clamp
                    )
                    if _needs_clamp:
                        import dataclasses as _dc
                        _clamped = {
                            f: max(0.0, min(1.0, getattr(task_result, f)))
                            for f in _fields_to_clamp
                            if getattr(task_result, f, None) is not None
                            and not (0.0 <= getattr(task_result, f, 0.0) <= 1.0)
                        }
                        task_result = _dc.replace(task_result, **_clamped)
            except Exception as cb_exc:
                logger.debug("on_record callback failed (ignored): %s", cb_exc)

        # D3: on_error 는 _record_to_monitors() 이후에 호출됨 — 태스크는 이미 기록 완료
        # Gap AK: on_error 콜백 — has_error 시에만 호출
        if on_error is not None and has_error:
            try:
                on_error(task_result)
            except Exception as e:
                logger.warning("on_error 콜백 실패: %s", e)  # L3: warn not debug

        return task_result  # Gap AM: 호출자가 수집할 수 있도록 반환

    except Exception as exc:
        logger.debug(
            "_build_and_record 실패 (평가 생략, 원본 실행 결과는 정상): %s", exc
        )
        return None  # Gap AM


# ---------------------------------------------------------------------------
# H1: Agent eval parameter presets — 공통 파라미터 묶음
# ---------------------------------------------------------------------------

# SPEC-039 REQ-1: preset과 명시적 파라미터가 충돌할 때 "파이썬 기본값과 우연히 같은 값"을
# "미지정"으로 오인하지 않기 위한 sentinel. `sample_rate=1.0`처럼 명시적으로 전달한 값이
# 기본값과 같다는 이유로 preset에 조용히 덮어써지는 걸 막는다 — `is` 비교로만 판정한다.
_UNSET: Any = object()


def _resolve_preset_field(
    explicit: Any, unset: bool, preset_vals: dict[str, Any], key: str, default: Any
) -> Any:
    """SPEC-039 REQ-1: `explicit`이 실제로 호출자가 전달한 값이면(``unset=False``) 그 값을
    preset보다 항상 우선한다. `unset=True`(호출자가 아예 전달하지 않음)일 때만 preset 값을
    쓰고, preset에도 키가 없으면 `default`로 떨어진다."""
    if not unset:
        return explicit
    return preset_vals.get(key, default)


AGENT_EVAL_PRESETS: dict[str, dict[str, Any]] = {
    "production": {
        # E5: 프로덕션 환경 — 샘플링 10%, 타임아웃 30s, 50건마다 flush, 중복 task_id 차단
        "sample_rate": 0.1,
        "timeout": 30.0,
        "flush_every": 50,
        "allow_duplicate_task_ids": False,
        "enabled": True,
        "enable_anomaly_detection": True,  # 프로덕션에서 이상 감지 기본 활성화
        "enable_llm_judge": True,          # 프로덕션 품질 자동 채점 활성화
    },
    "development": {
        # E5: 개발 환경 — 전량 평가, 타임아웃 없음, 매 건 flush, LLM Judge 활성화
        "sample_rate": 1.0,
        "timeout": None,
        "flush_every": 1,
        "enabled": True,
        "enable_llm_judge": True,          # 개발 중 LLM Judge로 상세 품질 확인
        "auto_detect_framework": True,
    },
    "testing": {
        "sample_rate": 0.1,    # 테스트 환경에서도 샘플링으로 부하 감소
        "timeout": 60.0,
        "flush_every": 5,      # 잦은 flush로 진행 상황 추적
        "enabled": True,
    },
    "canary": {
        "sample_rate": 0.05,   # 카나리: 5% 샘플링 (기존 1%는 너무 낮음)
        "timeout": 30.0,
        "flush_every": 50,
        "enable_anomaly_detection": True,  # 카나리 배포 시 이상 감지 필수
        "enabled": True,
    },
    "performance": {
        # D3: 레이턴시/토큰 지표에 집중 — LLM Judge 끄고 가볍게
        "sample_rate": 1.0,
        "timeout": 10.0,   # 빠른 응답 기준
        "enabled": True,
        "enable_anomaly_detection": True,  # latency 이상 감지
        "flush_every": 20,
    },
    "security": {
        # D3: 보안 지표 전용 — 모든 security tracker 활성화
        "sample_rate": 1.0,
        "timeout": 30.0,
        "enabled": True,
    },
}
"""사전 정의된 agent_eval / batch_eval 파라미터 묶음 (H1).

각 preset은 특정 운영 환경에 맞는 기본값을 제공한다. 직접 지정한 파라미터가 preset보다 우선한다.

Example::

    @agent_eval(monitor, task_type="qa", preset="production")
    def my_agent(question: str, ground_truth: str = "") -> str: ...
"""


def register_preset(name: str, config: dict[str, Any]) -> None:
    """사용자 정의 preset을 AGENT_EVAL_PRESETS에 등록합니다 (항목 W).

    Args:
        name: preset 이름 (예: ``"myco_prod"``). 빈 문자열 불가.
        config: agent_eval 파라미터 딕셔너리.
            예: ``{"sample_rate": 0.5, "flush_every": 10}``

    Raises:
        ValueError: name이 빈 문자열이거나 config가 dict가 아닌 경우.

    Example::

        register_preset("myco_prod", {
            "sample_rate": 0.5,
            "enable_anomaly_detection": True,
            "flush_every": 10,
        })

        @agent_eval(monitor, task_type="qa", preset="myco_prod")
        def agent(question, ground_truth=""): ...
    """
    if not name or not isinstance(name, str):
        raise ValueError("register_preset: name은 비어 있지 않은 문자열이어야 합니다")
    if not isinstance(config, dict):
        raise ValueError("register_preset: config는 dict여야 합니다")
    if name in AGENT_EVAL_PRESETS:
        import warnings as _warnings_w
        _warnings_w.warn(
            f"register_preset: '{name}' preset이 이미 존재합니다. 덮어씁니다.",
            UserWarning,
            stacklevel=2,
        )
    AGENT_EVAL_PRESETS[name] = config


# ---------------------------------------------------------------------------
# 동기 데코레이터
# ---------------------------------------------------------------------------


class _AgentEvalHandle:
    """agent_eval() 반환 객체 — 데코레이터와 컨텍스트 매니저 모두 지원.

    데코레이터 모드::

        @agent_eval(monitor, task_type="qa")
        def fn(question, ground_truth=""): ...

    컨텍스트 매니저 모드 (eval_context 대체)::

        with agent_eval(monitor, task_type="qa",
                        question="Q", ground_truth="A") as ctx:
            ctx.response = external_lib.call("Q")

        async with agent_eval(monitor, task_type="qa", question="Q") as ctx:
            ctx.response = await async_llm.call("Q")
    """

    def __init__(
        self,
        _decorator_fn: Callable,   # agent_eval 내부 decorator 함수
        _ctx_factory: Callable[[], eval_context],    # eval_context 생성용 팩토리 (callable)
    ) -> None:
        self._decorator_fn = _decorator_fn
        self._ctx_factory = _ctx_factory
        # context manager 모드에서 활성화되는 eval_context 인스턴스
        self._ctx_instance: eval_context | None = None

    # ── 데코레이터 모드 ──────────────────────────────────────────────────

    def __call__(self, func: Callable) -> Callable:
        """데코레이터로 사용: @agent_eval(monitor, ...)"""
        return self._decorator_fn(func)

    # ── 컨텍스트 매니저 모드 ─────────────────────────────────────────────

    def __enter__(self) -> eval_context:
        self._ctx_instance = self._ctx_factory()
        return self._ctx_instance.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if self._ctx_instance is not None:
            return self._ctx_instance.__exit__(exc_type, exc_val, exc_tb)
        return False

    async def __aenter__(self) -> eval_context:
        self._ctx_instance = self._ctx_factory()
        return self._ctx_instance.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if self._ctx_instance is not None:
            return self._ctx_instance.__exit__(exc_type, exc_val, exc_tb)
        return False


def agent_eval(
    monitor_or_fn: Any = None,
    task_type: Union[str, Any] = "qa",
    *,
    question_arg: str = "question",
    ground_truth_arg: str = "ground_truth",
    task_id_prefix: str = "task",
    context_arg: str | None = None,
    expected_tools_arg: str | None = None,
    expected_tools: list[str] | None = None,
    framework: Union[FrameworkLiteral, str] = "native",
    model_name: str = "",
    score_fn: Callable[[str, str], float] | None = None,
    completion_fn: Callable[[str, str], float] | None = None,
    task_id_fn: Callable | None = None,
    # SPEC-039 REQ-1: 기본값은 아래 docstring/Args에 문서화된 그대로다 — `_UNSET`은
    # "호출자가 이 인자를 아예 전달하지 않았다"를 preset/eval_config 자동 로드와
    # 구분하기 위한 내부 sentinel일 뿐, 함수 진입 직후 바로 실제 기본값으로 치환된다.
    sample_rate: float = _UNSET,  # 실제 기본값: 1.0
    on_record: Callable | None = None,
    on_error: Callable | None = None,
    timeout: float | None = _UNSET,  # 실제 기본값: None (무제한)
    enabled: bool = _UNSET,  # 실제 기본값: True
    alert_rules: list[SimpleTaskAlertRule] | None = None,
    flush_every: int | None = _UNSET,  # 실제 기본값: None
    # v0.8.1+: retry/llm_judge/security パラメータ묶음
    retry: RetryConfig | None = None,
    llm_judge: LLMJudgeConfig | None = None,
    security: SecurityConfig | None = None,
    # A9: custom_parser — framework adapter보다 낮은 우선순위로 EvalMetadata 생성
    custom_parser: Callable[[Any], EvalMetadata | None] | None = None,
    # H1: preset — 사전 정의된 파라미터 묶음 ("production" | "development" | "testing" | "canary")
    preset: str | None = None,
    # G4: 이 데코레이터에서만 hallucination detection 활성화 (monitor 전역 설정 우선)
    enable_hallucination_detection: bool = _UNSET,  # 실제 기본값: False
    # E2: RAG 단축 — context_arg + hallucination + task_type 자동 설정
    rag_mode: bool = False,
    enable_anomaly_detection: bool = _UNSET,  # 실제 기본값: False
    ttft_seconds: float | None = None,
    # S: alert 핸들러 예외 처리 모드 ("log" | "strict", 기본: "log")
    alert_error_mode: str = "log",
    # v0.9.0+: Phase 1 Harness Config
    instructions: InstructionConfig | None = None,
    loop_detection: LoopDetectionConfig | None = None,
    goal_alignment: GoalAlignmentConfig | None = None,
    reproducibility: ReproducibilityConfig | None = None,
    fault_tolerance: FaultToleranceConfig | None = None,
    plan_tracking: PlanConfig | None = None,
    # v0.9.1+: 신규 Harness Config
    sla: SLAConfig | None = None,
    threat_severity: ThreatSeverityConfig | None = None,
    efficiency: EfficiencyConfig | None = None,
    state_consistency: StateConsistencyConfig | None = None,
    deadlock: DeadlockConfig | None = None,
    observability: ObservabilityConfig | None = None,
    consensus: ConsensusConfig | None = None,
    # v0.9.2+: Phase 3 Harness Config
    scope: ScopeConfig | None = None,
    context_retention: ContextRetentionConfig | None = None,
    explainability: ExplainabilityConfig | None = None,
    subtask_tracking: SubtaskConfig | None = None,
    propagation: PropagationConfig | None = None,
    # v0.9.3+: Phase 4 Harness Config
    agent_role: AgentRoleConfig | None = None,
    graceful_degradation: GracefulDegradationConfig | None = None,
    compliance: ComplianceConfig | None = None,
    resource_budget: ResourceBudgetConfig | None = None,
    conflict_resolution: ConflictResolutionConfig | None = None,
    # v0.9.4+: Phase 5 Harness Config
    tool_parameter_safety: ToolParameterSafetyConfig | None = None,
    knowledge_retention: KnowledgeRetentionConfig | None = None,
    retry_consistency: RetryConsistencyConfig | None = None,
    error_diagnosis: ErrorDiagnosisConfig | None = None,
    # v0.9.5+: Phase 6 Harness Config
    idempotency: IdempotencyConfig | None = None,
    threat_response: ThreatResponseConfig | None = None,
    context_window: ContextWindowConfig | None = None,
    latency_attribution: LatencyAttributionConfig | None = None,
) -> Any:
    """동기·비동기 에이전트 함수에 평가를 자동 적용하는 데코레이터 (sync/async 자동 감지).

    **Quick Start — 90% 사용 사례를 커버하는 핵심 5개 파라미터**::

        @agent_eval(
            monitor,                      # 1. PerformanceMonitor 인스턴스 (필수)
            task_type="qa",               # 2. 태스크 유형
            framework="langchain",        # 3. 프레임워크 식별자 (대시보드 분류)
            model_name="gpt-5-nano",     # 4. LLM 모델명 (Phoenix 차트)
            score_fn=custom_score,        # 5. 커스텀 정확도 함수 (없으면 자동 계산)
        )
        def agent(question, ground_truth=""): ...

        # RAG 에이전트 — 한 줄로 완성
        @agent_eval(monitor, rag_mode=True)
        def rag_agent(question, context="", ground_truth=""): ...

        # 프리셋 — production 환경 권장 설정 일괄 적용
        @agent_eval(monitor, preset="production")
        def agent(question, ground_truth=""): ...

        # 재시도 내장 — max_retries=3, 지수 백오프
        @agent_eval(monitor, task_type="qa", max_retries=3, delay=1.0, backoff=2.0)
        def fragile_agent(question, ground_truth=""): ...

    Args:
        monitor: 결과를 기록할 :class:`~agent_evaluator.PerformanceMonitor` 인스턴스.
        task_type: Task 유형. ``"qa"``, ``"coding"``, ``"information_retrieval"`` 등.
        question_arg: 질문을 담고 있는 파라미터 이름 (기본: ``"question"``).
            일치하는 이름이 없으면 첫 번째 positional 인자를 사용한다.
        ground_truth_arg: 정답 파라미터 이름 (기본: ``"ground_truth"``).
        task_id_prefix: 자동 생성 task_id 의 접두어 (기본: ``"task"``).
        context_arg: RAG context 파라미터 이름. 지정하면 HallucinationDetector 에 전달.
        expected_tools_arg: expected_tools 파라미터 이름.
            지정하면 ToolSelectionTracker 의 F1 계산에 사용된다.
        framework: 프레임워크 식별자 (기본: ``"native"``).
            ``"langchain"``, ``"langgraph"``, ``"crewai"``, ``"autogen"`` 등.
            대시보드 프레임워크 분포 차트에 반영된다.
        model_name: 이 태스크에서 사용한 LLM 모델명.
            Phoenix "Top models" 차트에 표시된다.
        score_fn: 커스텀 accuracy 계산 함수 ``(response: str, ground_truth: str) -> float``.
            반환값은 ``[0.0, 1.0]`` 으로 클램핑된다.
            ``EvalMetadata.accuracy_score`` 보다 낮은 우선순위를 가진다.
        completion_fn: 커스텀 completion 계산 함수 ``(response: str, ground_truth: str) -> float``.
        task_id_fn: task_id 생성 함수 ``(args: tuple, kwargs: dict) -> str``.
            ``None`` 이면 ``{prefix}_{uuid8}`` 로 자동 생성한다.
        sample_rate: 평가 실행 비율 ``[0.0, 1.0]`` (기본: ``1.0`` = 항상 평가).
            ``0.1`` 이면 호출의 10%만 평가하고 나머지는 함수만 실행한다.
        on_record: 평가 기록 후 호출되는 콜백 함수 ``(task_result: TaskResult) -> None``.
            임계값 알림, DB 저장, 커스텀 메트릭 등 사이드이펙트에 활용한다.
            콜백 예외는 무시된다.
        timeout: 함수 실행 최대 허용 시간(초). ``None`` 이면 무제한.
            초과 시 ``TimeoutError`` 가 발생하며 ``has_error=True`` 로 기록된다.
            sync 함수는 ``ThreadPoolExecutor`` 를 사용하므로 GIL 종속 연산에는 효과 없음.
            스트리밍 generator 함수에는 적용되지 않는다.
        enabled: ``False`` 이면 데코레이터를 우회하고 원본 함수만 실행한다.

    Returns:
        데코레이터 함수.

    Examples::

        # 기본 QA
        @agent_eval(monitor, task_type="qa")
        def qa_agent(question: str, ground_truth: str = "") -> str:
            return llm.predict(question)

        # Tool Selection F1 활성화 + 프레임워크 지정
        @agent_eval(monitor, task_type="tool_use",
                    expected_tools_arg="expected", framework="langchain")
        def tool_agent(question, expected=None, ground_truth=""):
            return executor.invoke({"input": question})

        # EvalMetadata 튜플 반환으로 내부 재시도 횟수 기록
        @agent_eval(monitor, task_type="qa")
        def retry_agent(question, ground_truth=""):
            for n in range(1, 4):
                try:
                    resp = llm.predict(question)
                    return resp, EvalMetadata(attempts=n)
                except Exception:
                    if n == 3: raise

        # 커스텀 점수 함수
        @agent_eval(monitor, task_type="code_generation",
                    score_fn=lambda r, gt: rouge_score(r, gt))
        def code_agent(question, ground_truth=""):
            return llm.predict(question)

        # 스레드 로컬 컨텍스트로 메타데이터 주입 (반환값 타입 변경 불필요)
        @agent_eval(monitor, task_type="tool_use")
        def lc_agent(question, ground_truth=""):
            result = executor.invoke({"input": question})
            ctx = get_eval_ctx()
            if ctx:
                ctx.framework = "langchain"
                ctx.chain_steps = parse_steps(result)
            return result["output"]
    """
    # SPEC-039 REQ-1: 호출자가 실제로 이 값들을 전달했는지 여부를 sentinel(`_UNSET`)로
    # 기록해둔다 — 이후 eval_config 파일 자동 로드 블록과 preset 블록 둘 다 "값이 SDK
    # 기본값과 같음"이 아니라 "호출자가 실제로 안 넘겼음"으로 override 여부를 판정하게 한다.
    # `sample_rate=1.0`처럼 기본값과 우연히 같은 명시적 값이 preset/config에 조용히
    # 덮어써지던 버그(및 eval_config 경로의 동일 버그)를 여기서 함께 해소한다.
    _explicit_sample_rate = sample_rate is not _UNSET
    _explicit_timeout = timeout is not _UNSET
    _explicit_flush_every = flush_every is not _UNSET
    _explicit_enabled = enabled is not _UNSET
    _explicit_enable_anomaly = enable_anomaly_detection is not _UNSET
    _explicit_enable_hallucination = enable_hallucination_detection is not _UNSET
    if sample_rate is _UNSET:
        sample_rate = 1.0
    if timeout is _UNSET:
        timeout = None
    if flush_every is _UNSET:
        flush_every = None
    if enabled is _UNSET:
        enabled = True
    if enable_anomaly_detection is _UNSET:
        enable_anomaly_detection = False
    if enable_hallucination_detection is _UNSET:
        enable_hallucination_detection = False

    # ── Phase 1: Config-based zero-param decorator support ─────────────────
    # Usage modes:
    #   @agent_eval                    → monitor_or_fn is the function (bare decorator)
    #   @agent_eval()                  → monitor_or_fn is None
    #   @agent_eval(profile="rag")     → monitor_or_fn is None
    #   @agent_eval(monitor, ...)      → monitor_or_fn is PerformanceMonitor (backward compat)
    _bare_fn = None
    if callable(monitor_or_fn) and not hasattr(monitor_or_fn, "record_task"):
        # Bare @agent_eval: monitor_or_fn is the decorated function itself
        _bare_fn = monitor_or_fn
        monitor_or_fn = None

    if monitor_or_fn is None:
        # No explicit monitor: load from config file + monitor registry
        try:
            from .eval_config import get_active_config as _get_cfg  # type: ignore[import-not-found]
            from .eval_config import get_or_create_monitor as _get_mon  # type: ignore[import-not-found]
            _cfg = _get_cfg()
            monitor = _get_mon(config=_cfg)
            # Apply config values conservatively: only when param is still at its SDK default
            if task_type == "qa":
                task_type = _cfg.task_type
            if framework == "native":
                framework = _cfg.framework
            if model_name == "":
                model_name = _cfg.model_name
            if not _explicit_sample_rate:
                sample_rate = _cfg.sample_rate
            if not rag_mode:
                rag_mode = getattr(_cfg, "rag_mode", False)
            if not _explicit_enable_hallucination:
                enable_hallucination_detection = getattr(_cfg, "enable_hallucination", False) or getattr(_cfg, "enable_hallucination_detection", False)
            if llm_judge is None:
                _judge_cfg = getattr(_cfg, "judge", None)
                if _judge_cfg is not None and getattr(_judge_cfg, "enabled", False):
                    llm_judge = LLMJudgeConfig(
                        model=getattr(_judge_cfg, "model", None),
                        criteria=getattr(_judge_cfg, "criteria", None),
                    )
            if not _explicit_enable_anomaly:
                enable_anomaly_detection = getattr(_cfg, "enable_anomaly_detection", False) or getattr(getattr(_cfg, "anomaly", None), "enabled", False)
            if not _explicit_flush_every:
                flush_every = getattr(_cfg, "flush_every", None)
            if retry is None:
                _max_r = getattr(_cfg, "max_retries", 1)
                if _max_r > 1:
                    retry = RetryConfig(max=_max_r)
        except Exception:
            monitor = None
    else:
        monitor = monitor_or_fn
    # NOTE: .eval_config 모듈이 현재 존재하지 않아(위 import는 항상 ImportError로
    # except에 빠짐) monitor 없이 호출하는 경로(@agent_eval() 등)는 여기서 monitor=None
    # 으로 귀결된다. 이 세션에서는 타입 표기만 정리하고 런타임 가드는 추가하지 않았다 —
    # 아래 cast는 하위 _build_and_record() 등이 기대하는 타입을 명시할 뿐, monitor가
    # 실제로 None일 가능성 자체를 없애지는 않는다.
    monitor = cast("Union[PerformanceMonitor, list[PerformanceMonitor]]", monitor)
    # ── End Phase 1 ─────────────────────────────────────────────────────────

    # E2: rag_mode — context_arg + hallucination + task_type 자동 설정
    if rag_mode:
        if context_arg is None:
            context_arg = "context"
        enable_hallucination_detection = True
        if task_type == "qa":
            task_type = "information_retrieval"

    # H1: preset — 사전 정의된 파라미터 묶음 적용 (명시적 파라미터가 preset보다 우선)
    _preset_vals: dict[str, Any] = {}
    if preset is not None:
        if preset in AGENT_EVAL_PRESETS:
            _preset_vals = AGENT_EVAL_PRESETS[preset]
        else:
            import warnings
            _valid_presets = list(AGENT_EVAL_PRESETS.keys())
            warnings.warn(
                f"알 수 없는 preset: '{preset}'.\n"
                f"  사용 가능한 preset: {_valid_presets}\n"
                f"  예시: @agent_eval(monitor, preset='production')",
                UserWarning,
                stacklevel=2,
            )
    # SPEC-039 REQ-1: preset 값 적용 — "호출자가 명시적으로 전달했는가"로만 판정한다
    # (더 이상 "현재 값이 SDK 기본값과 같은가"로 오판하지 않음 — eval_config 블록이
    # 이미 값을 바꿔놨을 수 있으므로 함수 진입 시점에 캡처해둔 _explicit_* 플래그를 쓴다).
    _effective_sample_rate = _resolve_preset_field(
        sample_rate, not _explicit_sample_rate, _preset_vals, "sample_rate", sample_rate
    )
    _effective_timeout = _resolve_preset_field(
        timeout, not _explicit_timeout, _preset_vals, "timeout", timeout
    )
    _effective_flush_every = _resolve_preset_field(
        flush_every, not _explicit_flush_every, _preset_vals, "flush_every", flush_every
    )
    _effective_enabled = _resolve_preset_field(
        enabled, not _explicit_enabled, _preset_vals, "enabled", enabled
    )
    _effective_enable_anomaly = _resolve_preset_field(
        enable_anomaly_detection, not _explicit_enable_anomaly, _preset_vals,
        "enable_anomaly_detection", enable_anomaly_detection
    )
    _effective_enable_hallucination = _resolve_preset_field(
        enable_hallucination_detection, not _explicit_enable_hallucination, _preset_vals,
        "enable_hallucination",
        _preset_vals.get("enable_hallucination_detection", enable_hallucination_detection),
    )

    # v0.8.2+: resolve llm_judge config → internal variables for _build_and_record
    if llm_judge is not None:
        _effective_enable_llm_judge = True
        _effective_judge_model = llm_judge.model
        _effective_judge_criteria = llm_judge.criteria
        _effective_judge_sample_rate = llm_judge.sample_rate
        _effective_judge_escalation_model = llm_judge.escalation_model
        _effective_judge_escalation_threshold = llm_judge.escalation_threshold
        _effective_judge_budget_per_day = llm_judge.budget_per_day
        _effective_judge_budget_storage_path = llm_judge.budget_storage_path
        _effective_judge_max_context_chars = llm_judge.max_context_chars
        _effective_judge_seed = llm_judge.seed
    else:
        _effective_enable_llm_judge = bool(_preset_vals.get("enable_llm_judge", False))
        _effective_judge_model = _preset_vals.get("judge_model", None)
        _effective_judge_criteria = _preset_vals.get("judge_criteria", None)
        _effective_judge_sample_rate = None
        _effective_judge_escalation_model = None
        _effective_judge_escalation_threshold = 2.5
        _effective_judge_budget_per_day = None
        _effective_judge_budget_storage_path = None
        _effective_judge_max_context_chars = 4000
        _effective_judge_seed = None

    # v0.8.3+: resolve security config → internal variables for _build_and_record
    if security is not None:
        _effective_security_mode = True
        _effective_allowed_tools = security.allowed_tools
        _effective_restricted_tools = security.restricted_tools
        _effective_security_sample_rate: float | None = getattr(security, "sample_rate", None)
        if _effective_security_sample_rate == 1.0:
            _effective_security_sample_rate = None  # 기본값이면 주입 불필요
    else:
        _effective_security_mode = False
        _effective_allowed_tools = None
        _effective_restricted_tools = None
        _effective_security_sample_rate = None

    # H1: 계산된 effective 값을 원본 변수에 재할당
    # SPEC-039 REQ-1: sample_rate도 함께 재할당 — 이전에는 _effective_sample_rate가
    # 계산만 되고 실제 샘플링 게이트(`if sample_rate < 1.0 and ...`)에는 전혀 반영되지
    # 않는 죽은 변수였다(preset의 sample_rate가 한 번도 실제로 적용된 적이 없었음).
    sample_rate = _effective_sample_rate
    flush_every = _effective_flush_every
    enabled = _effective_enabled

    # v0.8.1+: resolve retry config → internal retry variables
    if retry is not None:
        _n_tries = max(1, retry.max)
        _retry_on = retry.on if retry.on else (Exception,)
        _retry_delay = retry.delay
        _retry_backoff = retry.backoff
        _retry_jitter_type = retry.jitter_type
        _retry_max_delay = retry.max_delay
        _retry_should_retry = retry.should_retry
        _retry_on_retry = retry.on_retry
    else:
        _n_tries = 1
        _retry_on = (Exception,)
        _retry_delay = 0.0
        _retry_backoff = 1.0
        _retry_jitter_type = "full"
        _retry_max_delay = 60.0
        _retry_should_retry = None
        _retry_on_retry = None

    # 데코레이터 수준의 static expected_tools 를 closure 변수로 캡처한다.
    _static_expected_tools: list[str] | None = expected_tools

    def decorator(func: Callable) -> Callable:
        if not enabled:
            return func

        sig = inspect.signature(func)

        # Task 4: task_type 정규화 (Enum → str)
        _task_type_str = _normalize_task_type(task_type)

        # Task 5: alert_rules → on_record 통합
        # 실행 순서: alert_rules 평가 → on_record 콜백 (항목 A)
        _effective_on_record = on_record
        if alert_rules:
            _effective_on_record = _make_alert_on_record(alert_rules, on_record, alert_error_mode)

        # Task 2: flush_every 카운터 (thread-safe)
        _flush_counter: list[int] = [0]
        _flush_lock = threading.Lock()

        def _maybe_flush(task_result: Any) -> None:
            if flush_every is None or flush_every <= 0:
                return
            with _flush_lock:
                _flush_counter[0] += 1
                if _flush_counter[0] % flush_every == 0:
                    try:
                        _mon = monitor if not isinstance(monitor, list) else monitor[0]
                        _mon.save_to_file("auto_save")
                        logger.debug("flush_every=%d 조건 충족 — 'auto_save' 저장", flush_every)
                    except Exception as _fe:
                        _flush_counter[0] -= 1  # M6: roll back counter so next call retries
                        logger.debug("flush_every 저장 실패 (무시): %s", _fe)

        # on_record에 _maybe_flush 연결 (Gap H: 반환값 보존)
        _orig_on_record = _effective_on_record
        def _combined_on_record(task_result: Any) -> Any:
            _ret = None
            if _orig_on_record is not None:
                try:
                    _ret = _orig_on_record(task_result)
                except Exception as e:
                    logger.debug("on_record 실패 (무시): %s", e)
            _maybe_flush(task_result)
            return _ret  # Gap H: 반환값 전달 → _build_and_record 에서 교체 여부 판단
        _effective_on_record = _combined_on_record

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return func(*args, **kwargs)

            # 항목 F: 이중 데코레이터 스택 감지 — 이미 agent_eval 내부에서 호출 시 경고
            if _eval_active.get(False):
                import warnings as _warnings_f
                _warnings_f.warn(
                    "agent_eval: 이미 평가 데코레이터 내부에서 호출됩니다. "
                    "이중 데코레이터(@langchain_eval + @agent_eval 등)는 태스크를 2번 기록할 수 있습니다.",
                    UserWarning,
                    stacklevel=3,
                )
            _eval_active_token = _eval_active.set(True)
            # M2: 중첩 깊이 추적 — ContextVar Token 기반으로 finally에서 복원
            _nest_depth_token = _NEST_DEPTH.set(_NEST_DEPTH.get() + 1)
            _current_depth = _NEST_DEPTH.get()
            if _current_depth > MAX_NESTING_DEPTH:
                import warnings as _warnings_m2
                _warnings_m2.warn(
                    f"agent_eval 중첩 깊이 {_current_depth}가 MAX_NESTING_DEPTH={MAX_NESTING_DEPTH}를 초과합니다. "
                    "재귀 호출 또는 과도한 데코레이터 중첩을 확인하세요.",
                    ResourceWarning,
                    stacklevel=3,
                )

            question, ground_truth, context, expected_tools = _resolve_args(
                sig, args, kwargs,
                question_arg, ground_truth_arg, context_arg, expected_tools_arg,
                fallback_expected_tools=_static_expected_tools,
            )
            # task_id_fn > auto
            task_id: str | None = (
                task_id_fn(args, kwargs)
                if task_id_fn is not None
                else f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
            )

            start = time.perf_counter()
            has_error = False
            error_msg: str | None = None
            raw: Any = None          # 함수 반환값 전체 (EvalMetadata 포함 가능)
            caller_result: Any = None  # 호출자에게 반환할 값 (EvalMetadata 제거)
            eval_ctx, _ctx_token = _push_ctx()
            _attempt = 0
            _errors: list[str] = []
            _wait = _retry_delay

            # StateConsistencyConfig: 실행 전 상태 스냅샷
            _state_before: dict[str, Any] | None = None
            _state_after: dict[str, Any] | None = None
            _state_fn = getattr(state_consistency, "state_fn", None) if state_consistency is not None else None
            if _state_fn is not None:
                try:
                    _state_before = _state_fn()
                except Exception as _se:
                    logger.debug("StateConsistencyConfig state_fn (before) 실패 (무시): %s", _se)
            # ReproducibilityConfig: 응답 목록 (추가 실행 후 채움)
            _repro_responses: list[str] | None = None

            try:
                while _attempt < _n_tries:
                    _attempt += 1
                    try:
                        if _effective_timeout is not None:
                            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
                                try:
                                    raw = _ex.submit(func, *args, **kwargs).result(timeout=_effective_timeout)
                                except concurrent.futures.TimeoutError:
                                    raise TimeoutError(f"exceeded {_effective_timeout}s")
                        else:
                            raw = func(*args, **kwargs)
                        break  # 성공 — retry 루프 탈출
                    except Exception as _exc:
                        # 재시도 없는 경우 또는 retry_on에 해당하지 않으면 즉시 전파
                        if _n_tries == 1 or not isinstance(_exc, _retry_on):
                            has_error = True
                            error_msg = str(_exc)
                            raise
                        _errors.append(str(_exc))
                        # should_retry 콜백 — False 반환 시 즉시 중단
                        if _retry_should_retry is not None:
                            try:
                                if not _retry_should_retry(_exc):
                                    has_error = True
                                    error_msg = str(_exc)
                                    raise
                            except Exception as _sre:
                                if not isinstance(_sre, _retry_on):
                                    pass
                        if _retry_on_retry is not None:
                            try:
                                _retry_on_retry(_attempt, str(_exc))
                            except Exception:
                                pass
                        if _attempt >= _n_tries:
                            has_error = True
                            error_msg = _errors[-1]
                            raise
                        # 지수 백오프 + jitter
                        if _wait > 0 or _retry_jitter_type in ("full", "decorrelated"):
                            _base = _retry_delay * (_retry_backoff ** (_attempt - 1))
                            if _retry_jitter_type == "decorrelated":
                                _actual = min(_retry_max_delay, random.uniform(_retry_delay, max(_retry_delay, _wait * 3)))
                            elif _retry_jitter_type == "none":
                                _actual = _wait
                            else:  # "full"
                                _actual = random.uniform(0.0, _base) if _retry_jitter_type == "full" else _wait
                            if _actual > 0:
                                time.sleep(_actual)
                        _wait = _wait * _retry_backoff
                caller_result, _ = _split_raw(raw)  # EvalMetadata 분리
                # StateConsistencyConfig: 실행 후 상태 스냅샷
                if _state_fn is not None and _state_before is not None:
                    try:
                        _state_after = _state_fn()
                    except Exception as _se:
                        logger.debug("StateConsistencyConfig state_fn (after) 실패 (무시): %s", _se)
                # ReproducibilityConfig: 추가 실행 수집
                if reproducibility is not None and not has_error:
                    _repro_responses = [str(caller_result) if caller_result is not None else ""]
                    if not getattr(reproducibility, "skip_side_effects", False):
                        _extra_runs = max(0, getattr(reproducibility, "runs", 3) - 1)
                        for _ in range(_extra_runs):
                            try:
                                _ex_raw = func(*args, **kwargs)
                                _ex_resp, _ = _split_raw(_ex_raw)
                                _repro_responses.append(str(_ex_resp) if _ex_resp is not None else "")
                            except Exception as _re:
                                logger.debug("reproducibility 추가 실행 실패 (무시): %s", _re)
                                _repro_responses.append("")
                    # skip_side_effects=True: 추가 실행 skip → run_count=1, score=1.0 반환
                return caller_result
            except Exception:
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)
                _eval_active.reset(_eval_active_token)  # 항목 F: 이중 감지 토큰 복원
                try:
                    _NEST_DEPTH.reset(_nest_depth_token)  # M2: 중첩 깊이 복원
                except Exception:
                    pass
                # 재시도 데이터를 eval_ctx에 주입 (attempts, errors)
                if eval_ctx is not None and _n_tries > 1:
                    eval_ctx.attempts = _attempt
                    if _errors:
                        eval_ctx.errors = _errors
                # ContextRetentionConfig.context_arg override
                _cr_context_text = context
                if context_retention is not None:
                    _cr_cfg_arg = getattr(context_retention, "context_arg", None) or context_arg
                    if _cr_cfg_arg and _cr_cfg_arg != context_arg:
                        try:
                            _cr_bound = sig.bind(*args, **kwargs)
                            _cr_bound.apply_defaults()
                            _cr_context_text = str(_cr_bound.arguments.get(_cr_cfg_arg, context or ""))
                        except Exception:
                            pass
                _build_and_record(
                        monitor,
                        task_type=_task_type_str,
                        task_id=task_id,
                        question=question,
                        ground_truth=ground_truth,
                        context=context,
                        expected_tools_from_arg=expected_tools,
                        elapsed=elapsed,
                        raw=raw,
                        has_error=has_error,
                        error_msg=error_msg,
                        model_name=model_name,
                        framework=framework,
                        score_fn=score_fn,
                        completion_fn=completion_fn,
                        eval_ctx=eval_ctx,
                        on_record=_effective_on_record,
                        on_error=on_error,
                        custom_parser=custom_parser,
                        auto_detect_framework=True,
                        enable_hallucination=_effective_enable_hallucination,
                        enable_llm_judge=_effective_enable_llm_judge,
                        judge_model=_effective_judge_model,
                        judge_criteria=_effective_judge_criteria,
                        judge_sample_rate=_effective_judge_sample_rate,
                        judge_escalation_model=_effective_judge_escalation_model,
                        judge_escalation_threshold=_effective_judge_escalation_threshold,
                        judge_budget_per_day=_effective_judge_budget_per_day,
                        judge_budget_storage_path=_effective_judge_budget_storage_path,
                        judge_max_context_chars=_effective_judge_max_context_chars,
                        judge_seed=_effective_judge_seed,
                        security_mode=_effective_security_mode,
                        allowed_tools=_effective_allowed_tools,
                        restricted_tools=_effective_restricted_tools,
                        security_sample_rate=_effective_security_sample_rate,
                        enable_anomaly_detection=_effective_enable_anomaly,
                        allow_duplicate_task_ids=True,
                        instructions=instructions,
                        loop_detection=loop_detection,
                        goal_alignment=goal_alignment,
                        reproducibility=reproducibility,
                        reproducibility_responses=_repro_responses,
                        fault_tolerance=fault_tolerance,
                        plan_tracking=plan_tracking,
                        sla=sla,
                        threat_severity=threat_severity,
                        efficiency=efficiency,
                        state_consistency_before=_state_before,
                        state_consistency_after=_state_after,
                        state_consistency=state_consistency,
                        deadlock=deadlock,
                        observability=observability,
                        consensus=consensus,
                        scope=scope,
                        context_retention=context_retention,
                        explainability=explainability,
                        subtask_tracking=subtask_tracking,
                        propagation=propagation,
                        context_retention_text=_cr_context_text if context_retention is not None else None,
                        agent_role=agent_role,
                        graceful_degradation=graceful_degradation,
                        compliance=compliance,
                        resource_budget=resource_budget,
                        conflict_resolution=conflict_resolution,
                        tool_parameter_safety=tool_parameter_safety,
                        knowledge_retention=knowledge_retention,
                        retry_consistency=retry_consistency,
                        error_diagnosis=error_diagnosis,
                        idempotency=idempotency,
                        threat_response=threat_response,
                        context_window=context_window,
                        latency_attribution=latency_attribution,
                )
                # M3: ttft_seconds 외부 주입 — 데코레이터 모드에서 track_ttft() 호출
                if ttft_seconds is not None:
                    _monitors_ttft = monitor if isinstance(monitor, list) else [monitor]
                    for _m_ttft in _monitors_ttft:
                        _lt = getattr(_m_ttft, "latency_tracker", None)
                        if _lt is not None and hasattr(_lt, "track_ttft"):
                            try:
                                _lt.track_ttft(task_id, ttft_seconds,
                                               task_type=_task_type_str)
                            except Exception as _ttft_e:
                                logger.debug("ttft track_ttft 실패 (무시): %s", _ttft_e)
                            break

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return await func(*args, **kwargs)

            question, ground_truth, context, expected_tools = _resolve_args(
                sig, args, kwargs,
                question_arg, ground_truth_arg, context_arg, expected_tools_arg,
                fallback_expected_tools=_static_expected_tools,
            )
            # task_id_fn > auto
            task_id: str | None = (
                task_id_fn(args, kwargs)
                if task_id_fn is not None
                else f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
            )

            start = time.perf_counter()
            has_error = False
            error_msg: str | None = None
            raw: Any = None
            eval_ctx, _ctx_token = _push_ctx()
            # H1: track _eval_active and _NEST_DEPTH for async wrapper (same as gen/agen wrappers)
            _async_eval_active_token = _eval_active.set(True)
            _async_nest_depth_token = _NEST_DEPTH.set(_NEST_DEPTH.get() + 1)
            _attempt = 0
            _errors: list[str] = []
            _wait = _retry_delay
            # SPEC-006 REQ-3: 이 호출에서 억제된 judge 대상을 _build_and_record가 적재하는 리스트
            _async_judge_targets: list[Any] = []

            # StateConsistencyConfig: 실행 전 상태 스냅샷 (async)
            _async_state_before: dict[str, Any] | None = None
            _async_state_after: dict[str, Any] | None = None
            _async_state_fn = getattr(state_consistency, "state_fn", None) if state_consistency is not None else None
            if _async_state_fn is not None:
                try:
                    _async_state_before = _async_state_fn()
                except Exception as _se:
                    logger.debug("StateConsistencyConfig state_fn async (before) 실패 (무시): %s", _se)
            # SPEC-039 REQ-2: ReproducibilityConfig: 응답 목록 (추가 실행 후 채움) — sync
            # wrapper와 동일한 필드. 이전에는 async에 이 로직이 아예 없어
            # reproducibility_responses=None이 하드코딩돼 있었고 async 에이전트에서
            # Gate C avg_reproducibility가 항상 조용히 None이었다.
            _repro_responses: list[str] | None = None

            try:
                while _attempt < _n_tries:
                    _attempt += 1
                    try:
                        if _effective_timeout is not None:
                            raw = await asyncio.wait_for(func(*args, **kwargs), timeout=_effective_timeout)
                        else:
                            raw = await func(*args, **kwargs)
                        break  # 성공
                    except Exception as _exc:
                        if _n_tries == 1 or not isinstance(_exc, _retry_on):
                            has_error = True
                            error_msg = str(_exc)
                            raise
                        _errors.append(str(_exc))
                        if _retry_should_retry is not None:
                            try:
                                if not _retry_should_retry(_exc):
                                    has_error = True
                                    error_msg = str(_exc)
                                    raise
                            except Exception as _sre:
                                if not isinstance(_sre, _retry_on):
                                    pass
                        if _retry_on_retry is not None:
                            try:
                                _retry_on_retry(_attempt, str(_exc))
                            except Exception:
                                pass
                        if _attempt >= _n_tries:
                            has_error = True
                            error_msg = _errors[-1]
                            raise
                        if _wait > 0 or _retry_jitter_type in ("full", "decorrelated"):
                            _base = _retry_delay * (_retry_backoff ** (_attempt - 1))
                            if _retry_jitter_type == "decorrelated":
                                _actual = min(_retry_max_delay, random.uniform(_retry_delay, max(_retry_delay, _wait * 3)))
                            elif _retry_jitter_type == "none":
                                _actual = _wait
                            else:
                                _actual = random.uniform(0.0, _base) if _retry_jitter_type == "full" else _wait
                            if _actual > 0:
                                await asyncio.sleep(_actual)
                        _wait = _wait * _retry_backoff
                caller_result, _ = _split_raw(raw)
                # StateConsistencyConfig: 실행 후 상태 스냅샷 (async)
                if _async_state_fn is not None and _async_state_before is not None:
                    try:
                        _async_state_after = _async_state_fn()
                    except Exception as _se:
                        logger.debug("StateConsistencyConfig state_fn async (after) 실패 (무시): %s", _se)
                # SPEC-039 REQ-2: ReproducibilityConfig: 추가 실행 수집 (async) — sync
                # wrapper(위 `caller_result, _ = _split_raw(raw)  # EvalMetadata 분리` 직후)와
                # 동일한 로직, `func(*args, **kwargs)` 대신 `await func(*args, **kwargs)`만 다르다.
                if reproducibility is not None and not has_error:
                    _repro_responses = [str(caller_result) if caller_result is not None else ""]
                    if not getattr(reproducibility, "skip_side_effects", False):
                        _extra_runs = max(0, getattr(reproducibility, "runs", 3) - 1)
                        for _ in range(_extra_runs):
                            try:
                                _ex_raw = await func(*args, **kwargs)
                                _ex_resp, _ = _split_raw(_ex_raw)
                                _repro_responses.append(
                                    str(_ex_resp) if _ex_resp is not None else ""
                                )
                            except Exception as _re:
                                logger.debug(
                                    "reproducibility 추가 실행 실패 (async, 무시): %s", _re
                                )
                                _repro_responses.append("")
                    # skip_side_effects=True: 추가 실행 skip → run_count=1, score=1.0 반환
                return caller_result
            except Exception:
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)
                # H1: restore ContextVar tokens set at async_wrapper entry
                try: _eval_active.reset(_async_eval_active_token)
                except Exception: pass
                try: _NEST_DEPTH.reset(_async_nest_depth_token)
                except Exception: pass
                if eval_ctx is not None and _n_tries > 1:
                    eval_ctx.attempts = _attempt
                    if _errors:
                        eval_ctx.errors = _errors
                # ContextRetentionConfig.context_arg override (async)
                _cr_context_text = context
                if context_retention is not None:
                    _cr_cfg_arg = getattr(context_retention, "context_arg", None) or context_arg
                    if _cr_cfg_arg and _cr_cfg_arg != context_arg:
                        try:
                            _cr_bound = sig.bind(*args, **kwargs)
                            _cr_bound.apply_defaults()
                            _cr_context_text = str(_cr_bound.arguments.get(_cr_cfg_arg, context or ""))
                        except Exception:
                            pass
                _build_and_record(
                        monitor,
                        task_type=_task_type_str,
                        task_id=task_id,
                        question=question,
                        ground_truth=ground_truth,
                        context=context,
                        expected_tools_from_arg=expected_tools,
                        elapsed=elapsed,
                        raw=raw,
                        has_error=has_error,
                        error_msg=error_msg,
                        model_name=model_name,
                        framework=framework,
                        score_fn=score_fn,
                        completion_fn=completion_fn,
                        eval_ctx=eval_ctx,
                        on_record=_effective_on_record,
                        on_error=on_error,
                        custom_parser=custom_parser,
                        auto_detect_framework=True,
                        enable_hallucination=_effective_enable_hallucination,
                        enable_llm_judge=_effective_enable_llm_judge,
                        judge_model=_effective_judge_model,
                        judge_criteria=_effective_judge_criteria,
                        judge_sample_rate=_effective_judge_sample_rate,
                        judge_escalation_model=_effective_judge_escalation_model,
                        judge_escalation_threshold=_effective_judge_escalation_threshold,
                        judge_budget_per_day=_effective_judge_budget_per_day,
                        judge_budget_storage_path=_effective_judge_budget_storage_path,
                        judge_max_context_chars=_effective_judge_max_context_chars,
                        judge_seed=_effective_judge_seed,
                        security_mode=_effective_security_mode,
                        allowed_tools=_effective_allowed_tools,
                        restricted_tools=_effective_restricted_tools,
                        security_sample_rate=_effective_security_sample_rate,
                        enable_anomaly_detection=_effective_enable_anomaly,
                        allow_duplicate_task_ids=True,
                        instructions=instructions,
                        loop_detection=loop_detection,
                        goal_alignment=goal_alignment,
                        reproducibility=reproducibility,
                        # SPEC-039 REQ-2: sync와 동일 지원
                        reproducibility_responses=_repro_responses,
                        fault_tolerance=fault_tolerance,
                        plan_tracking=plan_tracking,
                        sla=sla,
                        threat_severity=threat_severity,
                        efficiency=efficiency,
                        state_consistency_before=_async_state_before,
                        state_consistency_after=_async_state_after,
                        state_consistency=state_consistency,
                        deadlock=deadlock,
                        observability=observability,
                        consensus=consensus,
                        scope=scope,
                        context_retention=context_retention,
                        explainability=explainability,
                        subtask_tracking=subtask_tracking,
                        propagation=propagation,
                        context_retention_text=_cr_context_text if context_retention is not None else None,
                        agent_role=agent_role,
                        graceful_degradation=graceful_degradation,
                        compliance=compliance,
                        resource_budget=resource_budget,
                        conflict_resolution=conflict_resolution,
                        tool_parameter_safety=tool_parameter_safety,
                        knowledge_retention=knowledge_retention,
                        retry_consistency=retry_consistency,
                        error_diagnosis=error_diagnosis,
                        idempotency=idempotency,
                        threat_response=threat_response,
                        context_window=context_window,
                        latency_attribution=latency_attribution,
                        # SPEC-006 REQ-3: 비동기 경로 — 동기 judge() 대신 ajudge() 배선
                        use_async_judge=True,
                        async_judge_targets=_async_judge_targets,
                    )
                if _async_judge_targets:
                    await _process_async_judge_targets(_async_judge_targets)

        @functools.wraps(func)
        def gen_wrapper(*args, **kwargs):
            """sync generator 함수용 wrapper — chunk 를 passthrough 하며 소진 후 기록."""
            if sample_rate < 1.0 and random.random() > sample_rate:
                yield from func(*args, **kwargs)
                return

            question, ground_truth, context, expected_tools = _resolve_args(
                sig, args, kwargs,
                question_arg, ground_truth_arg, context_arg, expected_tools_arg,
                fallback_expected_tools=_static_expected_tools,
            )
            # task_id_fn > auto
            task_id: str | None = (
                task_id_fn(args, kwargs)
                if task_id_fn is not None
                else f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
            )
            start = time.perf_counter()
            has_error = False
            error_msg: str | None = None
            chunks: list[str] = []
            eval_meta_from_gen: EvalMetadata | None = None  # Gap AV
            _first_yield_time: float | None = None           # D6: 첫 청크 시간
            eval_ctx, _ctx_token = _push_ctx()
            # H6/M3: track _eval_active and _NEST_DEPTH for generators (same as regular wrapper)
            _gen_eval_active_token = _eval_active.set(True)
            _gen_nest_depth_token = _NEST_DEPTH.set(_NEST_DEPTH.get() + 1)

            try:
                for chunk in func(*args, **kwargs):
                    if isinstance(chunk, EvalMetadata):  # Gap AV: intercept, don't yield
                        eval_meta_from_gen = chunk
                    else:
                        if _first_yield_time is None:
                            _first_yield_time = time.perf_counter() - start  # D6
                        chunks.append(str(chunk))
                        yield chunk
            except Exception as exc:
                has_error = True
                error_msg = str(exc)
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)
                # H6/M3: restore ContextVar tokens set at gen_wrapper entry
                try: _eval_active.reset(_gen_eval_active_token)
                except Exception: pass
                try: _NEST_DEPTH.reset(_gen_nest_depth_token)
                except Exception: pass
                raw_str = "".join(chunks)
                # Gap AV: pass EvalMetadata from generator as (raw, eval_meta) tuple
                raw_to_record = (raw_str, eval_meta_from_gen) if eval_meta_from_gen else raw_str
                _build_and_record(
                        monitor,
                        task_type=_task_type_str,
                        task_id=task_id,
                        question=question,
                        ground_truth=ground_truth,
                        context=context,
                        expected_tools_from_arg=expected_tools,
                        elapsed=elapsed,
                        raw=raw_to_record,
                        has_error=has_error,
                        error_msg=error_msg,
                        model_name=model_name,
                        framework=framework,
                        score_fn=score_fn,
                        completion_fn=completion_fn,
                        eval_ctx=eval_ctx,
                        on_record=_effective_on_record,
                        on_error=on_error,
                        custom_parser=custom_parser,
                        auto_detect_framework=True,
                        enable_hallucination=_effective_enable_hallucination,
                        enable_llm_judge=_effective_enable_llm_judge,
                        judge_model=_effective_judge_model,
                        judge_criteria=_effective_judge_criteria,
                        judge_sample_rate=_effective_judge_sample_rate,
                        judge_escalation_model=_effective_judge_escalation_model,
                        judge_escalation_threshold=_effective_judge_escalation_threshold,
                        judge_budget_per_day=_effective_judge_budget_per_day,
                        judge_budget_storage_path=_effective_judge_budget_storage_path,
                        judge_max_context_chars=_effective_judge_max_context_chars,
                        judge_seed=_effective_judge_seed,
                        security_mode=_effective_security_mode,
                        allowed_tools=_effective_allowed_tools,
                        restricted_tools=_effective_restricted_tools,
                        security_sample_rate=_effective_security_sample_rate,
                        enable_anomaly_detection=_effective_enable_anomaly,
                        allow_duplicate_task_ids=True,
                        instructions=instructions,
                        loop_detection=loop_detection,
                        goal_alignment=goal_alignment,
                        fault_tolerance=fault_tolerance,
                        plan_tracking=plan_tracking,
                        agent_role=agent_role,
                        graceful_degradation=graceful_degradation,
                        compliance=compliance,
                        resource_budget=resource_budget,
                        conflict_resolution=conflict_resolution,
                        tool_parameter_safety=tool_parameter_safety,
                        knowledge_retention=knowledge_retention,
                        retry_consistency=retry_consistency,
                        error_diagnosis=error_diagnosis,
                        idempotency=idempotency,
                        threat_response=threat_response,
                        context_window=context_window,
                        latency_attribution=latency_attribution,
                )
                # D6: 첫 청크 시간을 TTFT로 자동 기록
                if _first_yield_time is not None:
                    _monitors_d6 = monitor if isinstance(monitor, list) else [monitor]
                    for _m in _monitors_d6:
                        try:
                            _lt = getattr(_m, "latency_tracker", None)
                            if _lt is not None and hasattr(_lt, "track_ttft"):
                                _lt.track_ttft(task_id, _first_yield_time,
                                               task_type=_task_type_str)
                                break
                        except Exception:
                            pass

        @functools.wraps(func)
        async def agen_wrapper(*args, **kwargs):
            """async generator 함수용 wrapper — chunk 를 passthrough 하며 소진 후 기록."""
            if sample_rate < 1.0 and random.random() > sample_rate:
                async for chunk in func(*args, **kwargs):
                    yield chunk
                return

            question, ground_truth, context, expected_tools = _resolve_args(
                sig, args, kwargs,
                question_arg, ground_truth_arg, context_arg, expected_tools_arg,
                fallback_expected_tools=_static_expected_tools,
            )
            # task_id_fn > auto
            task_id: str | None = (
                task_id_fn(args, kwargs)
                if task_id_fn is not None
                else f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
            )
            start = time.perf_counter()
            has_error = False
            error_msg: str | None = None
            chunks: list[str] = []
            eval_meta_from_gen: EvalMetadata | None = None  # Gap AV
            _first_yield_time: float | None = None           # D6: 첫 청크 시간
            eval_ctx, _ctx_token = _push_ctx()
            # H6/M3: track _eval_active and _NEST_DEPTH for async generators
            _agen_eval_active_token = _eval_active.set(True)
            _agen_nest_depth_token = _NEST_DEPTH.set(_NEST_DEPTH.get() + 1)

            try:
                async for chunk in func(*args, **kwargs):
                    if isinstance(chunk, EvalMetadata):  # Gap AV: intercept, don't yield
                        eval_meta_from_gen = chunk
                    else:
                        if _first_yield_time is None:
                            _first_yield_time = time.perf_counter() - start  # D6
                        chunks.append(str(chunk))
                        yield chunk
            except Exception as exc:
                has_error = True
                error_msg = str(exc)
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)
                # H6/M3: restore ContextVar tokens set at agen_wrapper entry
                try: _eval_active.reset(_agen_eval_active_token)
                except Exception: pass
                try: _NEST_DEPTH.reset(_agen_nest_depth_token)
                except Exception: pass
                raw_str = "".join(chunks)
                # Gap AV: pass EvalMetadata from generator as (raw, eval_meta) tuple
                raw_to_record = (raw_str, eval_meta_from_gen) if eval_meta_from_gen else raw_str
                _build_and_record(
                        monitor,
                        task_type=_task_type_str,
                        task_id=task_id,
                        question=question,
                        ground_truth=ground_truth,
                        context=context,
                        expected_tools_from_arg=expected_tools,
                        elapsed=elapsed,
                        raw=raw_to_record,
                        has_error=has_error,
                        error_msg=error_msg,
                        model_name=model_name,
                        framework=framework,
                        score_fn=score_fn,
                        completion_fn=completion_fn,
                        eval_ctx=eval_ctx,
                        on_record=_effective_on_record,
                        on_error=on_error,
                        custom_parser=custom_parser,
                        auto_detect_framework=True,
                        enable_hallucination=_effective_enable_hallucination,
                        enable_llm_judge=_effective_enable_llm_judge,
                        judge_model=_effective_judge_model,
                        judge_criteria=_effective_judge_criteria,
                        judge_sample_rate=_effective_judge_sample_rate,
                        judge_escalation_model=_effective_judge_escalation_model,
                        judge_escalation_threshold=_effective_judge_escalation_threshold,
                        judge_budget_per_day=_effective_judge_budget_per_day,
                        judge_budget_storage_path=_effective_judge_budget_storage_path,
                        judge_max_context_chars=_effective_judge_max_context_chars,
                        judge_seed=_effective_judge_seed,
                        security_mode=_effective_security_mode,
                        allowed_tools=_effective_allowed_tools,
                        restricted_tools=_effective_restricted_tools,
                        security_sample_rate=_effective_security_sample_rate,
                        enable_anomaly_detection=_effective_enable_anomaly,
                        allow_duplicate_task_ids=True,
                        instructions=instructions,
                        loop_detection=loop_detection,
                        goal_alignment=goal_alignment,
                        fault_tolerance=fault_tolerance,
                        plan_tracking=plan_tracking,
                        agent_role=agent_role,
                        graceful_degradation=graceful_degradation,
                        compliance=compliance,
                        resource_budget=resource_budget,
                        conflict_resolution=conflict_resolution,
                        tool_parameter_safety=tool_parameter_safety,
                        knowledge_retention=knowledge_retention,
                        retry_consistency=retry_consistency,
                        error_diagnosis=error_diagnosis,
                        idempotency=idempotency,
                        threat_response=threat_response,
                        context_window=context_window,
                        latency_attribution=latency_attribution,
                )
                # D6: async generator — 첫 청크 시간을 TTFT로 자동 기록
                if _first_yield_time is not None:
                    _monitors_d6 = monitor if isinstance(monitor, list) else [monitor]
                    for _m in _monitors_d6:
                        try:
                            _lt = getattr(_m, "latency_tracker", None)
                            if _lt is not None and hasattr(_lt, "track_ttft"):
                                _lt.track_ttft(task_id, _first_yield_time,
                                               task_type=_task_type_str)
                                break
                        except Exception:
                            pass

        # 항목 B: generator 함수에 timeout 지정 시 UserWarning 발행
        if timeout is not None and (inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func)):
            _timeout_msg = (
                f"agent_eval: timeout={timeout}은 generator 함수에 적용되지 않습니다. "
                "streaming 함수의 timeout은 수동으로 구현하세요."
            )
            import warnings as _warnings_b
            _warnings_b.warn(_timeout_msg, UserWarning, stacklevel=3)
            logger.warning(_timeout_msg)  # 기존 테스트(caplog) 호환성 유지

        # SPEC-039 REQ-3: generator 함수에 retry 지정 시 UserWarning 발행 — 위 timeout
        # 경고(항목 B)와 동일한 이유. gen_wrapper/agen_wrapper에는 재시도 루프 자체가
        # 없다(이미 호출자에게 일부 청크를 yield한 뒤 "재시도"가 무엇을 의미하는지 자체가
        # 정의되지 않으므로 — SPEC-039 Non-Goals). retry는 조용히 무시되던 것을 명시적으로
        # 알리기만 한다 — 동작 자체(재시도 없이 그대로 실행)는 바뀌지 않는다.
        if retry is not None and (
            inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func)
        ):
            _retry_gen_msg = (
                "agent_eval: retry=RetryConfig(...)는 generator/스트리밍 함수에 적용되지 않습니다 "
                "(재시도 없이 그대로 실행됩니다). 이미 호출자에게 전달된 청크를 재시도 시점에 "
                "어떻게 처리할지가 정의되지 않아 지원하지 않습니다."
            )
            import warnings as _warnings_c
            _warnings_c.warn(_retry_gen_msg, UserWarning, stacklevel=3)
            logger.warning(_retry_gen_msg)

        if inspect.isasyncgenfunction(func):
            return agen_wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        if inspect.isgeneratorfunction(func):
            return gen_wrapper
        return wrapper

    def _ctx_factory() -> eval_context:
        return eval_context(
            monitor,
            task_type,
            context=None,
            expected_tools=expected_tools,
            framework=framework,
            model_name=model_name,
            task_id=None,
            task_id_prefix=task_id_prefix,
            auto_task_id=True,
            score_fn=score_fn,
            completion_fn=completion_fn,
            on_record=on_record,
            on_error=on_error,
            alert_rules=alert_rules,
            sample_rate=sample_rate,
            enabled=enabled,
            timeout=timeout,
            ttft_seconds=ttft_seconds,
        )

    if _bare_fn is not None:
        return decorator(_bare_fn)  # bare @agent_eval: return the wrapped function directly
    return _AgentEvalHandle(decorator, _ctx_factory)


# ---------------------------------------------------------------------------
# @conversation_eval — ConversationSession 기반 멀티턴 대화 평가
# ---------------------------------------------------------------------------

# 세션 저장소: session_id → {"session": ConversationSession, "monitor": monitor}
_CONV_SESSIONS: dict[str, dict[str, Any]] = {}
_conv_sessions_lock = threading.Lock()


def flush_all_conversations() -> int:
    """모든 활성 ``conversation_eval`` 세션을 일괄 flush 한다 (Gap S).

    프로세스 종료 직전 또는 테스트 클린업 시 누락 없이 모든 세션을 기록할 때 사용한다.

    Returns:
        flush 된 세션 수.

    Example::

        flush_all_conversations()  # 모든 미완료 세션 일괄 종료
    """
    with _conv_sessions_lock:
        session_ids = list(_CONV_SESSIONS.keys())
        entries = [_CONV_SESSIONS.pop(sid) for sid in session_ids]

    for entry in entries:
        _do_flush(entry)

    return len(entries)


def flush_conversation(session_id: str) -> bool:
    """``conversation_eval`` 세션을 명시적으로 종료하고 지표를 기록한다.

    세션 종료 후 저장소에서 제거된다.
    ``max_turns`` 도달 시 자동 flush 되므로, 명시적 flush 가 필요 없는 경우도 있다.

    Args:
        session_id: 종료할 세션 ID.

    Returns:
        ``True`` if flushed successfully, ``False`` if session not found.

    Example::

        @conversation_eval(monitor, session_id_arg="sid")
        def chat(user_message: str, sid: str = "default") -> str:
            return llm.predict(user_message)

        chat("안녕하세요", sid="conv_001")
        chat("날씨는?", sid="conv_001")
        flush_conversation("conv_001")   # 지표 계산 및 monitor 기록
    """
    with _conv_sessions_lock:
        entry = _CONV_SESSIONS.pop(session_id, None)

    if entry is None:
        logger.debug("flush_conversation: 세션 '%s' 없음 (이미 flush 됐거나 미생성)", session_id)
        return False

    _do_flush(entry)
    return True


def _do_flush(entry: dict[str, Any]) -> None:
    """실제 flush 로직 — with monitor.conversation() 컨텍스트 매니저 활용."""
    # Gap AY: 타이머 취소
    timer = entry.get("_timer")
    if timer is not None:
        timer.cancel()

    session_id: str = entry["session_id"]
    turns: list[dict[str, Any]] = entry["turns"]   # [{user, agent, metadata}]
    stored_monitor = entry["monitor"]

    if not turns:
        logger.debug("flush_conversation: 세션 '%s' 턴 없음 — skip", session_id)
        return

    on_flush_cb: Callable | None = entry.get("on_flush")
    session_score_fn_cb: Callable | None = entry.get("session_score_fn")  # Gap T
    on_record_cb: Callable | None = entry.get("on_record")  # C: on_record 콜백

    # H2: conversation_eval LLM Judge lazy-init — agent_eval과 동일한 패턴
    _conv_judge_was_lazy = False
    _conv_enable_llm_judge = entry.get("enable_llm_judge", False)
    if _conv_enable_llm_judge and getattr(stored_monitor, "llm_judge", None) is None:
        try:
            from agent_evaluator.integrations.llm_judge import LLMJudge as _LJCls
            _lj_model = entry.get("judge_model") or None
            _lj_criteria = entry.get("judge_criteria") or None
            stored_monitor.llm_judge = _LJCls(model=_lj_model, judge_criteria=_lj_criteria)
            stored_monitor.enable_llm_judge = True
            _conv_judge_was_lazy = True
            logger.debug("conversation_eval: LLM Judge lazy-init (model=%s)", stored_monitor.llm_judge.model)
        except Exception as _lj_init_exc:
            logger.warning("conversation_eval: LLM Judge 초기화 실패 (무시): %s", _lj_init_exc)
            _conv_enable_llm_judge = False

    try:
        with stored_monitor.conversation(session_id) as conv:
            for t in turns:
                conv.turn(
                    user=t["user"],
                    agent=t["agent"],
                    metadata=t.get("metadata", {}),
                )
        logger.debug(
            "flush_conversation: 세션 '%s' flush 완료 (%d턴)", session_id, len(turns)
        )
        # Gap T: session_score_fn — 세션 전체 점수 커스터마이징
        if session_score_fn_cb is not None:
            try:
                sessions = getattr(stored_monitor, "conversation_sessions", [])
                if sessions:
                    last_session = sessions[-1]
                    metrics = getattr(last_session, "metrics", None)
                    if metrics is not None:
                        custom_score = session_score_fn_cb(metrics)
                        if custom_score is not None:
                            metrics.overall_score = float(custom_score)
            except Exception as sf_exc:
                logger.debug("session_score_fn 실패 (무시): %s", sf_exc)
        # C: on_record 콜백 — 세션 flush 후 마지막 기록된 TaskResult에 적용
        if on_record_cb is not None:
            try:
                _last_tasks = getattr(stored_monitor, "tasks", None) or []
                if _last_tasks:
                    _last_tr = _last_tasks[-1]
                    _returned_tr = on_record_cb(_last_tr)
                    # on_record 가 TaskResult 를 반환하면 교체
                    if _returned_tr is not None and hasattr(_returned_tr, "task_id"):
                        pass  # conversation session task_result 교체는 지원하지 않음 (기록 완료 후)
            except Exception as _orec_exc:
                logger.debug("conversation_eval on_record callback failed (ignored): %s", _orec_exc)
        # Gap M: on_flush 콜백 — 예외 무시
        # 시그니처: (metrics, session_id) 우선; 구버전 (session_id,) 호환 fallback
        if on_flush_cb is not None:
            try:
                _flush_sessions = getattr(stored_monitor, "conversation_sessions", [])
                _flush_metrics = _flush_sessions[-1].metrics if _flush_sessions else None
            except Exception:
                _flush_metrics = None
            try:
                on_flush_cb(_flush_metrics, session_id)
            except TypeError:
                try:
                    on_flush_cb(session_id)
                except Exception as cb_exc:
                    logger.debug("on_flush 콜백 실패 (무시): %s", cb_exc)
            except Exception as cb_exc:
                logger.debug("on_flush 콜백 실패 (무시): %s", cb_exc)
        # alert_rules — 세션 flush 후 마지막 기록된 TaskResult 에 적용
        _flush_alert_rules = entry.get("alert_rules")
        if _flush_alert_rules:
            try:
                tcr_tracker = getattr(stored_monitor, "tcr_tracker", None)
                if tcr_tracker is not None and tcr_tracker.tasks:
                    last_task = tcr_tracker.tasks[-1]
                    for rule in _flush_alert_rules:
                        rule.evaluate(last_task)
            except Exception as _ar_exc:
                logger.debug("conversation alert_rules 실패 (무시): %s", _ar_exc)
    except Exception as exc:
        logger.debug("flush_conversation: 세션 '%s' flush 실패: %s", session_id, exc)
    finally:
        # H2: lazy-init한 LLM Judge 인스턴스 제거 (monitor 원상 복원)
        if _conv_judge_was_lazy:
            stored_monitor.llm_judge = None
            stored_monitor.enable_llm_judge = False


# SPEC-039 REQ-5: conversation_eval이 시그니처로는 받지만 실제 평가에 전혀 반영하지 않는
# Harness Config 파라미터 27개. `_do_flush()`가 `_build_and_record()`(agent_eval/batch_eval/
# eval_context가 공유하는 경로)를 거치지 않고 `conv.turn()`이라는 별도 경로로 기록하기
# 때문이다(2026-07-09 세션에서 `grep -n "\binstructions\b"`로 함수 본문 전체를 확인해
# 참조가 0건임을 검증). 실제 턴 단위 Harness 평가 배선은 이 스펙의 Non-Goals — 여기서는
# 호출자가 이 사실을 모른 채 조용히 무시당하지 않도록 경고만 낸다.
_CONVERSATION_EVAL_UNUSED_HARNESS_PARAMS = (
    "instructions", "loop_detection", "goal_alignment", "reproducibility",
    "fault_tolerance", "plan_tracking",
    "sla", "threat_severity", "efficiency", "state_consistency", "deadlock",
    "observability", "consensus",
    "scope", "context_retention", "explainability", "subtask_tracking", "propagation",
    "agent_role", "graceful_degradation", "compliance", "resource_budget", "conflict_resolution",
    "tool_parameter_safety", "knowledge_retention", "retry_consistency", "error_diagnosis",
    "idempotency", "threat_response", "context_window", "latency_attribution",
)


def conversation_eval(
    monitor: PerformanceMonitor,
    *,
    session_id_arg: str = "session_id",
    user_arg: str = "question",
    ground_truth_arg: str = "ground_truth",
    max_turns: int | None = None,
    flush_on_error: bool = True,
    sample_rate: float = _UNSET,  # SPEC-039 REQ-1: 실제 기본값 1.0 (sentinel, preset 충돌 판정용)
    on_flush: Callable | None = None,              # Gap M: (metrics, session_id: str) → None
    on_turn: Callable | None = None,               # Gap Z: (session_id, user, response, metadata) → None
    on_record: Callable[[TaskResult], TaskResult | None] | None = None,  # C: (TaskResult) → Optional[TaskResult]
    session_score_fn: Callable | None = None,      # Gap T: (ConversationMetrics) → float
    turn_score_fn: Callable | None = None,         # Gap AX: (user, response, metadata) → float
    max_session_seconds: float | None = None,      # Gap AY: 비활성 세션 자동 flush 타이머
    on_session_timeout: Callable | None = None,    # Gap J: (session_id: str) → None — 타임아웃 시 호출
    alert_rules: list[Any] | None = None,          # SimpleTaskAlertRule 리스트 — 세션 flush 후 발동
    flush_every: int | None = _UNSET,  # A3: 실제 기본값 None, N 세션마다 자동 저장
    enabled: bool = _UNSET,                           # 실제 기본값 True
    # A1: preset — AGENT_EVAL_PRESETS 키로 공통 파라미터 적용
    preset: str | None = None,
    # LLM Judge 통합
    llm_judge: LLMJudgeConfig | None = None,
    framework: str = "native",
    model_name: str = "",
    on_error: Callable | None = None,
    context_arg: str | None = None,
    expected_tools_arg: str | None = None,
    custom_parser: Callable | None = None,
    task_id_prefix: str = "conv",
    # A10: max_turns 초과 시 동작 ("flush" | "warn" | "error", 기본: "flush")
    max_turns_exceeded_action: str = "flush",
    # v0.9.0+: Phase 1 Harness Config
    instructions: InstructionConfig | None = None,
    loop_detection: LoopDetectionConfig | None = None,
    goal_alignment: GoalAlignmentConfig | None = None,
    # SPEC-039 REQ-4: agent_eval에는 있었지만 conversation_eval 시그니처에 아예 빠져있던
    # 4개 Harness Config를 추가(드리프트 감지 테스트로 발견). 다른 26개와 마찬가지로
    # 현재는 평가에 반영되지 않는다(REQ-5 경고 대상).
    reproducibility: ReproducibilityConfig | None = None,
    fault_tolerance: FaultToleranceConfig | None = None,
    plan_tracking: PlanConfig | None = None,
    # v0.9.1+: 신규 Harness Config
    sla: SLAConfig | None = None,
    threat_severity: ThreatSeverityConfig | None = None,
    efficiency: EfficiencyConfig | None = None,
    state_consistency: StateConsistencyConfig | None = None,  # SPEC-039 REQ-4
    deadlock: DeadlockConfig | None = None,
    observability: ObservabilityConfig | None = None,
    consensus: ConsensusConfig | None = None,  # SPEC-039 REQ-4
    # v0.9.2+: Phase 3 Harness Config
    scope: ScopeConfig | None = None,
    context_retention: ContextRetentionConfig | None = None,
    explainability: ExplainabilityConfig | None = None,
    subtask_tracking: SubtaskConfig | None = None,
    propagation: PropagationConfig | None = None,  # SPEC-039 REQ-4
    # v0.9.3+: Phase 4 Harness Config
    agent_role: AgentRoleConfig | None = None,
    graceful_degradation: GracefulDegradationConfig | None = None,
    compliance: ComplianceConfig | None = None,
    resource_budget: ResourceBudgetConfig | None = None,
    conflict_resolution: ConflictResolutionConfig | None = None,
    # v0.9.4+: Phase 5 Harness Config
    tool_parameter_safety: ToolParameterSafetyConfig | None = None,
    knowledge_retention: KnowledgeRetentionConfig | None = None,
    retry_consistency: RetryConsistencyConfig | None = None,
    error_diagnosis: ErrorDiagnosisConfig | None = None,
    # v0.9.5+: Phase 6 Harness Config
    idempotency: IdempotencyConfig | None = None,
    threat_response: ThreatResponseConfig | None = None,
    context_window: ContextWindowConfig | None = None,
    latency_attribution: LatencyAttributionConfig | None = None,
) -> Callable:
    """멀티턴 대화 함수에 ``ConversationSession`` 기반 세션 평가를 자동 적용.

    동일 ``session_id`` 로 반복 호출하면 내부적으로 턴을 누적한다.
    ``flush_conversation(session_id)`` 로 세션을 종료하거나
    ``max_turns`` 에 도달하면 자동으로 지표를 계산하고 ``monitor`` 에 기록한다.

    Args:
        monitor: :class:`~agent_evaluator.PerformanceMonitor` 인스턴스.
        session_id_arg: 세션 ID 를 담고 있는 파라미터 이름 (기본: ``"session_id"``).
            일치하는 이름이 없으면 새 UUID 로 세션을 시작한다.
        user_arg: 사용자 메시지 파라미터 이름 (기본: ``"question"``).
        ground_truth_arg: 정답 파라미터 이름 (기본: ``"ground_truth"``).
            추출된 값은 각 턴의 ``metadata["ground_truth"]`` 에 저장되어
            ``session_score_fn`` / ``on_turn`` 콜백에서 접근할 수 있다.
        on_turn: 매 턴 기록 직후 호출되는 콜백 (Gap Z).
            시그니처: ``(session_id: str, user: str, response: str, metadata: dict) -> None``.
            실시간 턴별 알림·로깅에 활용한다. 예외는 무시된다.
        max_turns: 이 턴 수 도달 시 자동 flush (기본: ``None`` = 수동 flush 전용).
        flush_on_error: 예외 발생 시 세션을 자동 flush 할지 여부 (기본: ``True``).
        sample_rate: 세션 기록 비율 ``[0.0, 1.0]`` (기본: ``1.0``).
            세션 최초 생성 시 샘플링 여부를 결정하며 이후 동일 세션의 모든 턴에 적용된다.
        enabled: ``False`` 이면 원본 함수만 실행한다.

    함수가 ``(response, TurnMetadata(...))`` 튜플을 반환하면 turn별 메타데이터
    (model, tokens, tool_calls 등)가 ``ConversationSession.turn()`` 에 전달된다.
    호출자에게는 ``response`` 만 반환된다.

    .. warning::
        SPEC-039 REQ-5: ``instructions``/``sla``/``scope`` 등 27개 Harness Config
        파라미터(``agent_eval``/``batch_eval``이 받는 것과 동일한 이름)는 시그니처로는
        받지만 **현재 평가에 전혀 반영되지 않는다** — ``conversation_eval``은 이 값들을
        ``TaskResult``/``_build_and_record()`` 경로가 아니라 별도의
        ``ConversationSession``/``conv.turn()`` 경로로 기록하기 때문이다. 하나라도
        전달하면 데코레이션 시점에 ``UserWarning``이 발생한다.

    Example::

        @conversation_eval(monitor, session_id_arg="sid", max_turns=5)
        def chat(question: str, sid: str = "conv_001") -> str:
            return llm.predict(question)

        chat("안녕하세요", sid="conv_001")
        chat("오늘 날씨는?", sid="conv_001")
        chat("내일은요?", sid="conv_001")
        # max_turns=5 미도달 시 수동 flush 필요
        flush_conversation("conv_001")
        # → ConversationSession: context_retention, topic_coherence 등 계산 후 기록
    """
    # SPEC-039 REQ-5: 이 27개 Harness Config 파라미터는 시그니처로는 받지만 conversation_eval의
    # 실제 기록 경로(_do_flush → conv.turn())가 전혀 참조하지 않는다 — 조용히 무시되던 것을
    # 호출자에게 알린다. 실제 평가 배선은 이 스펙의 범위 밖(Non-Goals).
    # 주의: `locals()`는 list comprehension 내부에서 호출하면 컴프리헨션 자체의 스코프를
    # 반환해 함수 파라미터를 보지 못한다 — 반드시 컴프리헨션 밖에서 한 번 캡처해야 한다.
    _conv_locals = locals()
    _conv_ignored_harness = [
        _name for _name in _CONVERSATION_EVAL_UNUSED_HARNESS_PARAMS
        if _conv_locals.get(_name) is not None
    ]
    if _conv_ignored_harness:
        import warnings as _w_conv
        _w_conv.warn(
            f"conversation_eval: {_conv_ignored_harness}는 현재 평가에 반영되지 않습니다 "
            "(conversation_eval은 TaskResult가 아니라 ConversationSession에 기록하며, 이 "
            "Harness Config 파라미터들을 평가하는 경로가 아직 구현돼 있지 않습니다 — "
            "SPEC-039 REQ-5 Non-Goals). 시그니처에는 남아 있으나 실제 효과가 없습니다.",
            UserWarning, stacklevel=2,
        )

    # SPEC-039 REQ-1: 호출자 전달 여부를 preset 병합 전에 캡처(sentinel 치환 전에 판정).
    _explicit_sample_rate = sample_rate is not _UNSET
    _explicit_flush_every = flush_every is not _UNSET
    _explicit_enabled = enabled is not _UNSET
    if sample_rate is _UNSET:
        sample_rate = 1.0
    if flush_every is _UNSET:
        flush_every = None
    if enabled is _UNSET:
        enabled = True

    # A1: preset — conversation_eval도 동일한 preset 시스템 지원
    if preset is not None:
        if preset in AGENT_EVAL_PRESETS:
            _cp = AGENT_EVAL_PRESETS[preset]
            sample_rate = _resolve_preset_field(
                sample_rate, not _explicit_sample_rate, _cp, "sample_rate", sample_rate
            )
            flush_every = _resolve_preset_field(
                flush_every, not _explicit_flush_every, _cp, "flush_every", flush_every
            )
            enabled = _resolve_preset_field(enabled, not _explicit_enabled, _cp, "enabled", enabled)
        else:
            import warnings as _w
            _w.warn(
                f"conversation_eval: 알 수 없는 preset '{preset}'. 사용 가능: {list(AGENT_EVAL_PRESETS.keys())}",
                UserWarning, stacklevel=2,
            )
    # LLM Judge 설정 추출
    _enable_llm_judge = llm_judge is not None
    _judge_model = llm_judge.model if llm_judge else None
    _judge_criteria = llm_judge.criteria if llm_judge else None
    # A3: participant_id_arg — 내부 기본값 (파라미터로 노출하지 않음)
    participant_id_arg: str | None = None

    def decorator(func: Callable) -> Callable:
        if not enabled:
            return func

        is_async = asyncio.iscoroutinefunction(func)
        sig = inspect.signature(func)

        # A3: flush_every 카운터 (session flush 단위)
        _conv_flush_counter: list[int] = [0]
        _conv_flush_lock = threading.Lock()

        def _maybe_flush_conv() -> None:
            if not flush_every or flush_every <= 0:
                return
            with _conv_flush_lock:
                _conv_flush_counter[0] += 1
                _should = (_conv_flush_counter[0] % flush_every == 0)
            if _should:
                _mon = monitor if not isinstance(monitor, list) else monitor[0]
                try:
                    _mon.save_to_file("auto_save")
                except Exception as _fe:
                    logger.debug("conversation_eval flush_every 저장 실패 (무시): %s", _fe)

        def _load_previous_session_turns(session_id: str) -> list[dict[str, Any]]:
            """이전 세션 턴 로드 (미지원 — 항상 빈 리스트 반환)."""
            return []

        def _get_or_create_session(session_id: str) -> dict[str, Any]:
            with _conv_sessions_lock:
                if session_id not in _CONV_SESSIONS:
                    sampled = sample_rate >= 1.0 or random.random() < sample_rate
                    # A7: 이전 세션 이력 로드
                    _prev_turns = _load_previous_session_turns(session_id)
                    _CONV_SESSIONS[session_id] = {
                        "session_id": session_id,
                        "monitor": monitor,
                        "turns": list(_prev_turns),  # A7: 이전 턴으로 초기화
                        "sampled": sampled,
                        "on_flush": on_flush,           # Gap M
                        "session_score_fn": session_score_fn,  # Gap T
                        "alert_rules": alert_rules,     # SimpleTaskAlertRule 리스트
                        "on_record": on_record,         # C: on_record 콜백
                        "on_turn": on_turn,             # H4: store callback in registry for external access
                        # LLM Judge per-session 설정
                        "enable_llm_judge": _enable_llm_judge,
                        "judge_model": _judge_model,
                        "judge_criteria": _judge_criteria,
                    }
                return _CONV_SESSIONS[session_id]

        def _add_turn(
            session_id: str,
            user: str,
            agent_resp: str,
            metadata: dict[str, Any],
        ) -> int:
            with _conv_sessions_lock:
                entry = _CONV_SESSIONS.get(session_id)
                if entry is None:
                    return 0
                entry["turns"].append({
                    "user": user,
                    "agent": agent_resp,
                    "metadata": metadata,
                })
                return len(entry["turns"])

        def _extract_session_args(*args, **kwargs):
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                all_args = dict(bound.arguments)
            except TypeError:
                all_args = {}

            session_id = all_args.get(session_id_arg) or f"conv_{uuid.uuid4().hex[:8]}"
            user_msg = all_args.get(user_arg)
            if user_msg is None:
                param_names = list(sig.parameters.keys())
                user_msg = all_args.get(param_names[0], "") if param_names else ""
            # Gap AD: ground_truth 실제 추출
            ground_truth_val = str(all_args.get(ground_truth_arg) or "")
            # A3: participant_id_arg 에서 발화자 ID 추출
            participant_id_val: str | None = None
            if participant_id_arg:
                _pid = all_args.get(participant_id_arg)
                if _pid is not None:
                    participant_id_val = str(_pid)
            return str(session_id), str(user_msg), ground_truth_val, participant_id_val

        def _build_turn_metadata(
            elapsed: float,
            turn_meta: TurnMetadata | None,
            participant_id: str | None = None,
        ) -> dict[str, Any]:
            """elapsed(자동 측정)과 TurnMetadata 를 합쳐 metadata dict 를 생성."""
            latency = (
                turn_meta.latency if (turn_meta and turn_meta.latency is not None) else elapsed
            )
            meta: dict[str, Any] = {"latency": latency}
            if turn_meta:
                if turn_meta.model is not None:
                    meta["model"] = turn_meta.model
                if turn_meta.tokens is not None:
                    meta["tokens"] = turn_meta.tokens
                if turn_meta.tool_calls is not None:
                    meta["tool_calls"] = turn_meta.tool_calls
                # Gap AP: TurnMetadata.ground_truth 주입
                if turn_meta.ground_truth is not None:
                    meta["ground_truth"] = turn_meta.ground_truth
                # A3: TurnMetadata.participant_id 우선, 그 다음 파라미터에서 추출한 값
                if turn_meta.participant_id is not None:
                    meta["participant_id"] = turn_meta.participant_id
                if turn_meta.extra:
                    meta.update(turn_meta.extra)
            # A3: participant_id — TurnMetadata보다 낮은 우선순위로 주입
            if participant_id is not None and "participant_id" not in meta:
                meta["participant_id"] = participant_id
            return meta

        def _reset_timer(session_id: str, entry: dict[str, Any]) -> None:
            """Gap AY: max_session_seconds 타이머를 재설정한다."""
            if max_session_seconds is None:
                return
            old = entry.get("_timer")
            if old is not None:
                old.cancel()

            def _on_timeout() -> None:
                # Gap J: on_session_timeout 콜백 — flush 직전에 호출
                if on_session_timeout is not None:
                    try:
                        on_session_timeout(session_id)
                    except Exception as _te:
                        logger.debug("on_session_timeout 콜백 실패 (무시): %s", _te)
                flush_conversation(session_id)

            t = threading.Timer(max_session_seconds, _on_timeout)
            t.daemon = True
            t.start()
            entry["_timer"] = t

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            session_id, user_msg, ground_truth, participant_id = _extract_session_args(*args, **kwargs)  # Gap AD / A3
            entry = _get_or_create_session(session_id)

            if not entry["sampled"]:
                return func(*args, **kwargs)

            start = time.perf_counter()
            raw: Any = None
            has_error = False

            try:
                raw = func(*args, **kwargs)
                raw_response, turn_meta = _split_turn_raw(raw)
                return raw_response
            except Exception:
                has_error = True
                if flush_on_error:
                    flush_conversation(session_id)
                raise
            finally:
                if not has_error:
                    elapsed = time.perf_counter() - start
                    raw_response, turn_meta = _split_turn_raw(raw)
                    agent_resp = _extract_response(raw_response)
                    metadata = _build_turn_metadata(elapsed, turn_meta, participant_id=participant_id)  # A3
                    # Gap AD: ground_truth 를 metadata 에 주입 — on_turn / session_score_fn 에서 활용
                    # Gap AP: TurnMetadata.ground_truth 우선 (_build_turn_metadata 가 이미 설정했을 수 있음)
                    if ground_truth and "ground_truth" not in metadata:
                        metadata["ground_truth"] = ground_truth
                    # Gap AX: turn_score_fn 호출
                    if turn_score_fn is not None:
                        try:
                            ts = float(turn_score_fn(user_msg, agent_resp, metadata))
                            metadata["turn_score"] = max(0.0, min(1.0, ts))
                        except Exception as ts_exc:
                            logger.debug("turn_score_fn 실패 (무시): %s", ts_exc)
                    turn_count = _add_turn(session_id, user_msg, agent_resp, metadata)
                    # Gap AY: 타이머 재설정
                    with _conv_sessions_lock:
                        _entry = _CONV_SESSIONS.get(session_id)
                    if _entry is not None:
                        _reset_timer(session_id, _entry)
                    # Gap Z: on_turn 콜백 — 예외 무시
                    if on_turn is not None:
                        try:
                            on_turn(session_id, user_msg, agent_resp, metadata)
                        except Exception as ot_exc:
                            logger.debug("on_turn 콜백 실패 (무시): %s", ot_exc)
                    if max_turns is not None and turn_count >= max_turns:
                        _action = max_turns_exceeded_action or "flush"
                        if _action == "error":
                            raise ValueError(
                                f"max_turns={max_turns} 초과: 세션 '{session_id}'"
                            )
                        elif _action == "warn":
                            logger.warning(
                                "max_turns=%d 초과: 세션 '%s' (계속 진행)", max_turns, session_id
                            )
                        else:  # "flush"
                            flush_conversation(session_id)
                            _maybe_flush_conv()

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            session_id, user_msg, ground_truth, participant_id = _extract_session_args(*args, **kwargs)  # Gap AD / A3
            entry = _get_or_create_session(session_id)

            if not entry["sampled"]:
                return await func(*args, **kwargs)

            start = time.perf_counter()
            raw: Any = None
            has_error = False

            try:
                raw = await func(*args, **kwargs)
                raw_response, turn_meta = _split_turn_raw(raw)
                return raw_response
            except Exception:
                has_error = True
                if flush_on_error:
                    flush_conversation(session_id)
                raise
            finally:
                if not has_error:
                    elapsed = time.perf_counter() - start
                    raw_response, turn_meta = _split_turn_raw(raw)
                    agent_resp = _extract_response(raw_response)
                    metadata = _build_turn_metadata(elapsed, turn_meta, participant_id=participant_id)  # A3
                    # Gap AD: ground_truth 를 metadata 에 주입
                    # Gap AP: TurnMetadata.ground_truth 우선
                    if ground_truth and "ground_truth" not in metadata:
                        metadata["ground_truth"] = ground_truth
                    # Gap AX: turn_score_fn 호출
                    if turn_score_fn is not None:
                        try:
                            ts = float(turn_score_fn(user_msg, agent_resp, metadata))
                            metadata["turn_score"] = max(0.0, min(1.0, ts))
                        except Exception as ts_exc:
                            logger.debug("turn_score_fn 실패 (무시): %s", ts_exc)
                    turn_count = _add_turn(session_id, user_msg, agent_resp, metadata)
                    # Gap AY: 타이머 재설정
                    with _conv_sessions_lock:
                        _entry = _CONV_SESSIONS.get(session_id)
                    if _entry is not None:
                        _reset_timer(session_id, _entry)
                    # Gap Z: on_turn 콜백 — 예외 무시
                    if on_turn is not None:
                        try:
                            on_turn(session_id, user_msg, agent_resp, metadata)
                        except Exception as ot_exc:
                            logger.debug("on_turn 콜백 실패 (무시): %s", ot_exc)
                    if max_turns is not None and turn_count >= max_turns:
                        flush_conversation(session_id)
                        _maybe_flush_conv()

        # D6: async generator 지원 — chunk passthrough 후 세션 턴 기록
        @functools.wraps(func)
        async def agen_conv_wrapper(*args, **kwargs):
            session_id, user_msg, ground_truth, participant_id = _extract_session_args(*args, **kwargs)  # A3
            entry = _get_or_create_session(session_id)

            if not entry["sampled"]:
                async for chunk in func(*args, **kwargs):
                    yield chunk
                return

            start = time.perf_counter()
            chunks: list[str] = []
            has_error = False

            try:
                async for chunk in func(*args, **kwargs):
                    chunks.append(str(chunk))
                    yield chunk
            except Exception:
                has_error = True
                if flush_on_error:
                    flush_conversation(session_id)
                raise
            finally:
                if not has_error:
                    elapsed = time.perf_counter() - start
                    agent_resp = "".join(chunks)
                    # A3: participant_id 주입
                    metadata: dict[str, Any] = {"latency": elapsed}
                    if participant_id is not None:
                        metadata["participant_id"] = participant_id
                    if ground_truth and "ground_truth" not in metadata:
                        metadata["ground_truth"] = ground_truth
                    if turn_score_fn is not None:
                        try:
                            ts = float(turn_score_fn(user_msg, agent_resp, metadata))
                            metadata["turn_score"] = max(0.0, min(1.0, ts))
                        except Exception as ts_exc:
                            logger.debug("turn_score_fn 실패 (무시): %s", ts_exc)
                    turn_count = _add_turn(session_id, user_msg, agent_resp, metadata)
                    with _conv_sessions_lock:
                        _entry = _CONV_SESSIONS.get(session_id)
                    if _entry is not None:
                        _reset_timer(session_id, _entry)
                    if on_turn is not None:
                        try:
                            on_turn(session_id, user_msg, agent_resp, metadata)
                        except Exception as ot_exc:
                            logger.debug("on_turn 콜백 실패 (무시): %s", ot_exc)
                    if max_turns is not None and turn_count >= max_turns:
                        flush_conversation(session_id)
                        _maybe_flush_conv()

        if inspect.isasyncgenfunction(func):
            return agen_conv_wrapper
        return async_wrapper if is_async else sync_wrapper

    return decorator


# ---------------------------------------------------------------------------
# @batch_eval — List[str] 배치 함수 평가
# ---------------------------------------------------------------------------

def batch_eval(
    monitor: Union[PerformanceMonitor, list[PerformanceMonitor]],
    task_type: str = "qa",
    *,
    questions_arg: str = "questions",
    ground_truths_arg: str = "ground_truths",
    contexts_arg: str | None = None,
    expected_tools_arg: str | None = None,
    task_id_prefix: str = "batch",
    task_id_fn: Callable | None = None,
    framework: str = "native",
    model_name: str = "",
    score_fn: Callable | None = None,
    completion_fn: Callable | None = None,
    on_record: Callable | None = None,
    on_error: Callable | None = None,
    on_batch_complete: Callable | None = None,
    on_batch_progress: Callable | None = None,
    alert_rules: list[Any] | None = None,
    # SPEC-039 REQ-1: `_UNSET` sentinel — 실제 기본값은 주석대로, preset과의 충돌 판정용.
    flush_every: int | None = _UNSET,          # 실제 기본값: None (N 배치 호출마다 자동 저장)
    sample_rate: float = _UNSET,                  # 실제 기본값: 1.0
    timeout: float | None = _UNSET,            # 실제 기본값: None
    enabled: bool = _UNSET,                       # 실제 기본값: True
    concurrency: int = 0,                       # >0이면 항목별로 병렬 실행 (asyncio.gather), 상한 설정
    # SPEC-006 REQ-4: LLM Judge 호출을 asyncio.gather로 동시 처리(옵트인). 기본 False=기존 순차 처리.
    concurrent_judge: bool = False,
    on_item_error: Callable | None = None,
    item_timeout: float | None = None,
    return_format: str = "list",
    preset: str | None = None,
    enable_hallucination_detection: bool = False,
    custom_parser: Callable | None = None,
    enable_anomaly_detection: bool = False,
    security: SecurityConfig | None = None,
    llm_judge: LLMJudgeConfig | None = None,
    # v0.9.0+: Phase 1 Harness Config
    instructions: InstructionConfig | None = None,
    loop_detection: LoopDetectionConfig | None = None,
    goal_alignment: GoalAlignmentConfig | None = None,
    reproducibility: ReproducibilityConfig | None = None,
    fault_tolerance: FaultToleranceConfig | None = None,
    plan_tracking: PlanConfig | None = None,
    # v0.9.1+: 신규 Harness Config
    sla: SLAConfig | None = None,
    threat_severity: ThreatSeverityConfig | None = None,
    efficiency: EfficiencyConfig | None = None,
    state_consistency: StateConsistencyConfig | None = None,
    deadlock: DeadlockConfig | None = None,
    observability: ObservabilityConfig | None = None,
    consensus: ConsensusConfig | None = None,
    # v0.9.2+: Phase 3 Harness Config
    scope: ScopeConfig | None = None,
    context_retention: ContextRetentionConfig | None = None,
    explainability: ExplainabilityConfig | None = None,
    subtask_tracking: SubtaskConfig | None = None,
    propagation: PropagationConfig | None = None,
    # v0.9.3+: Phase 4 Harness Config
    agent_role: AgentRoleConfig | None = None,
    graceful_degradation: GracefulDegradationConfig | None = None,
    compliance: ComplianceConfig | None = None,
    resource_budget: ResourceBudgetConfig | None = None,
    conflict_resolution: ConflictResolutionConfig | None = None,
    # v0.9.4+: Phase 5 Harness Config
    tool_parameter_safety: ToolParameterSafetyConfig | None = None,
    knowledge_retention: KnowledgeRetentionConfig | None = None,
    retry_consistency: RetryConsistencyConfig | None = None,
    error_diagnosis: ErrorDiagnosisConfig | None = None,
    # v0.9.5+: Phase 6 Harness Config
    idempotency: IdempotencyConfig | None = None,
    threat_response: ThreatResponseConfig | None = None,
    context_window: ContextWindowConfig | None = None,
    latency_attribution: LatencyAttributionConfig | None = None,
) -> Callable:
    """배치 에이전트 함수(``List[str]`` → ``List[str]``)에 평가를 자동 적용하는 데코레이터.

    함수 호출 시 ``questions[i]`` / ``ground_truths[i]`` / ``responses[i]`` 를 묶어
    각각 독립된 ``TaskResult`` 로 기록한다. 총 실행 시간을 배치 크기로 균등 분할한다.

    Args:
        monitor: :class:`~agent_evaluator.PerformanceMonitor` 인스턴스.
        task_type: Task 유형 (기본: ``"qa"``).
        questions_arg: 질문 리스트를 담고 있는 파라미터 이름 (기본: ``"questions"``).
            일치하는 이름이 없으면 첫 번째 positional 인자를 사용한다.
        ground_truths_arg: 정답 리스트 파라미터 이름 (기본: ``"ground_truths"``).
        contexts_arg: RAG context 리스트를 담은 파라미터 이름.
            지정하면 ``contexts[i]`` 가 각 항목의 할루시네이션 감지에 사용된다.
        expected_tools_arg: expected_tools 리스트(``List[List[str]]``)를 담은 파라미터 이름 (Gap W).
            지정하면 ``expected_tools[i]`` 가 각 항목의 Tool Selection F1 계산에 사용된다.
        task_id_prefix: 자동 생성 task_id 의 접두어 (기본: ``"batch"``).
            각 아이템에 ``{prefix}_{uuid8}_{i:03d}`` 형식으로 부여된다.
        task_id_fn: 항목별 task_id 생성 함수 ``(index: int, question: str, ground_truth: str) -> str`` (Gap V).
            ``None`` 이면 ``{prefix}_{uuid8}_{i:03d}`` 자동 생성.
        framework: 프레임워크 식별자 (기본: ``"native"``).
        model_name: LLM 모델명.
        score_fn: 커스텀 accuracy 계산 함수 ``(response: str, ground_truth: str) -> float``.
        completion_fn: 커스텀 completion 계산 함수.
        on_record: 항목별 기록 후 호출되는 콜백 ``(task_result: TaskResult) -> None``.
        sample_rate: 평가 실행 비율 ``[0.0, 1.0]`` (기본: ``1.0``).
            ``0.5`` 이면 호출의 50% 에서만 배치 전체를 평가한다.
        timeout: 배치 함수 전체 실행 최대 허용 시간(초) (Gap X).
            ``None`` 이면 무제한. 초과 시 ``TimeoutError`` 발생 후 ``has_error=True`` 기록.
        enabled: ``False`` 이면 데코레이터를 우회하고 원본 함수만 실행한다.

    Returns:
        데코레이터 함수.

    Examples::

        @batch_eval(monitor, task_type="qa", task_id_prefix="qa_batch")
        def qa_batch(questions: List[str], ground_truths: List[str] = None) -> List[str]:
            return [llm.predict(q) for q in questions]

        qa_batch(
            questions=["한국의 수도는?", "Python 창시자는?"],
            ground_truths=["서울", "귀도 반 로섬"],
        )
        # → 2개의 TaskResult 가 monitor 에 기록됨
    """
    # SPEC-039 REQ-1: 호출자 전달 여부를 preset 병합 전에 캡처(sentinel 치환 전에 판정).
    _explicit_sample_rate = sample_rate is not _UNSET
    _explicit_timeout = timeout is not _UNSET
    _explicit_flush_every = flush_every is not _UNSET
    _explicit_enabled = enabled is not _UNSET
    if sample_rate is _UNSET:
        sample_rate = 1.0
    if timeout is _UNSET:
        timeout = None
    if flush_every is _UNSET:
        flush_every = None
    if enabled is _UNSET:
        enabled = True

    # A1: preset — batch_eval도 agent_eval과 동일한 preset 시스템 지원
    if preset is not None:
        if preset in AGENT_EVAL_PRESETS:
            _bp = AGENT_EVAL_PRESETS[preset]
            sample_rate = _resolve_preset_field(
                sample_rate, not _explicit_sample_rate, _bp, "sample_rate", sample_rate
            )
            timeout = _resolve_preset_field(timeout, not _explicit_timeout, _bp, "timeout", timeout)
            flush_every = _resolve_preset_field(
                flush_every, not _explicit_flush_every, _bp, "flush_every", flush_every
            )
            enabled = _resolve_preset_field(enabled, not _explicit_enabled, _bp, "enabled", enabled)
        else:
            import warnings as _w
            _w.warn(
                f"batch_eval: 알 수 없는 preset '{preset}'. 사용 가능: {list(AGENT_EVAL_PRESETS.keys())}",
                UserWarning, stacklevel=2,
            )

    # Resolve llm_judge and security config
    _effective_enable_llm_judge = llm_judge is not None
    _effective_judge_model = llm_judge.model if llm_judge else None
    _effective_judge_criteria = llm_judge.criteria if llm_judge else None
    _effective_judge_sample_rate = llm_judge.sample_rate if llm_judge else None
    _effective_judge_escalation_model = llm_judge.escalation_model if llm_judge else None
    _effective_judge_escalation_threshold = llm_judge.escalation_threshold if llm_judge else 2.5
    _effective_judge_budget_per_day = llm_judge.budget_per_day if llm_judge else None
    _effective_judge_budget_storage_path = llm_judge.budget_storage_path if llm_judge else None
    _effective_judge_max_context_chars = llm_judge.max_context_chars if llm_judge else 4000
    _effective_judge_seed = llm_judge.seed if llm_judge else None
    _effective_security_mode = security is not None
    _effective_allowed_tools = security.allowed_tools if security else None
    _effective_restricted_tools = security.restricted_tools if security else None
    _sr = getattr(security, "sample_rate", 1.0) if security else 1.0
    _effective_security_sample_rate: float | None = None if _sr == 1.0 else _sr

    def decorator(func: Callable) -> Callable:
        if not enabled:
            return func

        # F-A: batch_eval은 consensus_responses를 각 항목에 전달하지 않으므로
        # consensus=ConsensusConfig(...)를 설정해도 eval_consensus가 항상 건너뛰어짐
        # (agent_eval 내부 조건: `if consensus is not None and consensus_responses:` → 항상 False)
        #
        # 2026-07 Ch09 리뷰에서 확인: `consensus_responses`는 `_build_and_record()`(내부 헬퍼)
        # 에만 존재하고 공개 `agent_eval()`/`batch_eval()` 시그니처에는 노출되지 않는다
        # (agent_eval(consensus_responses=...)는 TypeError). 아래 경고문이 예전에는
        # "agent_eval의 consensus_responses= 파라미터"를 대안으로 안내했지만, 그 파라미터
        # 자체를 호출자가 쓸 수 없으므로 실재하지 않는 해결책을 가리키고 있었다 — 실제로
        # 동작하는 유일한 경로(EvalMetadata(extra={"consensus": {...}}) 수동 주입, 또는
        # eval_consensus()를 직접 호출)로 안내를 정정한다.
        if consensus is not None:
            import warnings as _w_fa
            _w_fa.warn(
                "batch_eval에 consensus=ConsensusConfig(...)가 설정되어 있지만 "
                "batch_eval은 각 항목에 consensus_responses를 주입하지 않으므로 "
                "consensus 평가가 항상 건너뜁니다. "
                "ConsensusConfig 점수는 "
                "EvalMetadata(extra={'consensus': {'consensus_score': ...}})로 직접 계산해 "
                "주입하거나, agent_evaluator.gates.gate_f_multiagent.evaluators."
                "eval_consensus()를 배치 응답 목록에 직접 호출한 뒤 그 결과를 주입하세요.",
                UserWarning,
                stacklevel=2,
            )

        is_async = asyncio.iscoroutinefunction(func)
        sig = inspect.signature(func)

        # alert_rules → per-item on_record 통합
        _effective_on_record = on_record
        if alert_rules:
            _effective_on_record = _make_alert_on_record(alert_rules, on_record)

        # A8: return_format — mutable holder shared between wrapper and wrapper_with_format
        _last_batch_results_holder: list[list[Any]] = [[]]

        # flush_every 카운터 (thread-safe)
        _flush_counter: list[int] = [0]
        _flush_lock = threading.Lock()

        def _maybe_flush_batch() -> None:
            if flush_every is None or flush_every <= 0:
                return
            with _flush_lock:
                _flush_counter[0] += 1
                _should = (_flush_counter[0] % flush_every == 0)
            if _should:
                _mon = monitor if not isinstance(monitor, list) else monitor[0]
                try:
                    _mon.save_to_file("batch_eval_auto")
                except Exception as _fe:
                    logger.debug("batch_eval flush_every 저장 실패 (무시): %s", _fe)

        def _resolve_batch_args(*args, **kwargs):
            """questions / ground_truths / contexts / expected_tools_list 를 함수 인자에서 추출."""
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                all_args = dict(bound.arguments)
            except TypeError:
                all_args = {}

            questions: list[str] | None = all_args.get(questions_arg)
            if questions is None:
                param_names = list(sig.parameters.keys())
                questions = all_args.get(param_names[0], []) if param_names else []
            if not isinstance(questions, list):
                questions = list(cast(Any, questions))

            ground_truths: list[str] = all_args.get(ground_truths_arg) or []
            if not isinstance(ground_truths, list):
                ground_truths = list(cast(Any, ground_truths))

            # Gap Q: contexts 리스트 추출 (List[str])
            contexts: list[str] | None = None
            if contexts_arg:
                raw_ctx = all_args.get(contexts_arg)
                if raw_ctx is not None:
                    # M5: string must be wrapped as single-element list, not split char-by-char
                    if isinstance(raw_ctx, str):
                        contexts = [raw_ctx]
                    elif isinstance(raw_ctx, list):
                        contexts = [str(c) for c in raw_ctx]
                    else:
                        contexts = [str(c) for c in raw_ctx]

            # Gap W: expected_tools_list 추출 (List[List[str]])
            expected_tools_list: list[list[str] | None] | None = None
            if expected_tools_arg:
                raw_et = all_args.get(expected_tools_arg)
                if raw_et is not None and isinstance(raw_et, list):
                    # 각 요소는 List[str] 또는 None
                    expected_tools_list = [
                        (list(et) if et is not None else None) for et in raw_et
                    ]

            return (
                [str(q) for q in questions],
                [str(gt) for gt in ground_truths],
                contexts,
                expected_tools_list,
            )

        def _record_batch(
            questions: list[str],
            ground_truths: list[str],
            responses: Any,
            elapsed: float,
            has_error: bool,
            error_msg: str | None,
            batch_uuid: str,
            eval_ctx: _EvalContext | None = None,                           # Gap L
            contexts: list[str] | None = None,                              # Gap Q
            expected_tools_list: list[list[str] | None] | None = None,  # Gap W
            use_async_judge: bool = False,                # SPEC-006 REQ-4
            async_judge_targets: list[Any] | None = None,  # SPEC-006 REQ-4
        ) -> list[Any]:  # A8: returns list of TaskResult objects
            if not isinstance(responses, list):
                responses = [responses] if responses is not None else []

            n = max(len(questions), 1)
            per_item_time = elapsed / n

            # H2: 길이 불일치 경고 — 디버깅을 돕기 위해 명시적으로 기록
            if isinstance(responses, list) and len(responses) != len(questions):
                logger.debug(
                    "batch_eval: questions(%d) vs responses(%d) 길이 불일치. "
                    "responses가 부족한 항목은 빈 문자열로 처리됩니다.",
                    len(questions), len(responses),
                )

            # Gap AM: collect results for on_batch_complete
            batch_results: list[Any] = []

            for i, question in enumerate(questions):
                ground_truth = ground_truths[i] if i < len(ground_truths) else ""
                raw_response = responses[i] if i < len(responses) else ""
                # Gap V: task_id_fn 우선, 없으면 prefix+uuid 자동 생성
                if task_id_fn is not None:
                    try:
                        item_task_id = str(task_id_fn(i, question, ground_truth))
                    except Exception as tid_exc:
                        logger.debug("task_id_fn 실패 (자동 생성): %s", tid_exc)
                        item_task_id = f"{task_id_prefix}_{batch_uuid}_{i:03d}"
                else:
                    item_task_id = f"{task_id_prefix}_{batch_uuid}_{i:03d}"
                item_context = contexts[i] if (contexts and i < len(contexts)) else None  # Gap Q
                item_expected_tools = (                                                   # Gap W
                    expected_tools_list[i]
                    if (expected_tools_list and i < len(expected_tools_list))
                    else None
                )

                tr = _build_and_record(
                    monitor,
                    task_type=task_type,
                    task_id=item_task_id,
                    question=question,
                    ground_truth=ground_truth,
                    context=item_context,
                    expected_tools_from_arg=item_expected_tools,
                    elapsed=per_item_time,
                    raw=raw_response,
                    has_error=has_error and (not responses or i == len(responses) - 1),
                    error_msg=error_msg if has_error else None,
                    model_name=model_name,
                    framework=framework,
                    score_fn=score_fn,
                    completion_fn=completion_fn,
                    eval_ctx=eval_ctx,  # Gap L: 배치 공통 eval_ctx 전달
                    on_record=_effective_on_record,
                    on_error=on_error,
                    # H3: forward per-call params (parity with agent_eval wrappers)
                    enable_llm_judge=_effective_enable_llm_judge,
                    judge_model=_effective_judge_model,
                    judge_criteria=_effective_judge_criteria,
                    judge_sample_rate=_effective_judge_sample_rate,
                    judge_escalation_model=_effective_judge_escalation_model,
                    judge_escalation_threshold=_effective_judge_escalation_threshold,
                    judge_budget_per_day=_effective_judge_budget_per_day,
                    judge_budget_storage_path=_effective_judge_budget_storage_path,
                    judge_max_context_chars=_effective_judge_max_context_chars,
                    judge_seed=_effective_judge_seed,
                    security_mode=_effective_security_mode,
                    allowed_tools=_effective_allowed_tools,
                    restricted_tools=_effective_restricted_tools,
                    security_sample_rate=_effective_security_sample_rate,
                    enable_hallucination=enable_hallucination_detection,
                    auto_detect_framework=True,
                    custom_parser=custom_parser,
                    enable_anomaly_detection=enable_anomaly_detection,
                    allow_duplicate_task_ids=True,
                    instructions=instructions,
                    loop_detection=loop_detection,
                    goal_alignment=goal_alignment,
                    fault_tolerance=fault_tolerance,
                    plan_tracking=plan_tracking,
                    sla=sla,
                    threat_severity=threat_severity,
                    efficiency=efficiency,
                    state_consistency=state_consistency,
                    deadlock=deadlock,
                    observability=observability,
                    consensus=consensus,
                    scope=scope,
                    context_retention=context_retention,
                    explainability=explainability,
                    subtask_tracking=subtask_tracking,
                    propagation=propagation,
                    context_retention_text=item_context if context_retention is not None else None,
                    agent_role=agent_role,
                    graceful_degradation=graceful_degradation,
                    compliance=compliance,
                    resource_budget=resource_budget,
                    conflict_resolution=conflict_resolution,
                    tool_parameter_safety=tool_parameter_safety,
                    knowledge_retention=knowledge_retention,
                    retry_consistency=retry_consistency,
                    error_diagnosis=error_diagnosis,
                    idempotency=idempotency,
                    threat_response=threat_response,
                    context_window=context_window,
                    latency_attribution=latency_attribution,
                    # SPEC-006 REQ-4: 옵트인 동시 judge 처리 배선
                    use_async_judge=use_async_judge,
                    async_judge_targets=async_judge_targets,
                )
                if tr is not None:
                    batch_results.append(tr)
                # Gap I: on_batch_progress — 항목별 진행률 콜백
                if on_batch_progress is not None:
                    try:
                        on_batch_progress(i + 1, n)
                    except Exception as _pe:
                        logger.debug("on_batch_progress 콜백 실패 (무시): %s", _pe)

            # Gap AM: on_batch_complete 콜백
            if on_batch_complete is not None and batch_results:
                try:
                    on_batch_complete(batch_results)
                except Exception as e:
                    logger.debug("on_batch_complete 콜백 실패: %s", e)

            return batch_results  # A8: return task results list to wrapper

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return func(*args, **kwargs)
            questions, ground_truths, contexts, expected_tools_list = _resolve_batch_args(*args, **kwargs)
            batch_uuid = uuid.uuid4().hex[:8]
            start = time.perf_counter()
            has_error = False
            error_msg: str | None = None
            responses: Any = None
            eval_ctx, _ctx_token = _push_ctx()  # Gap L

            # A1: _item_failures 리스트 초기화 (concurrent 실행 시 개별 실패 추적)
            _item_failures: list[dict[str, Any]] = []

            try:
                # concurrency>0: 항목별 병렬 실행 (asyncio.gather for async, ThreadPoolExecutor for sync)
                # async 경로와 동일하게 questions_arg in kwargs 조건 추가 — positional 호출 시 TypeError 방지
                if concurrency > 0 and not is_async and questions_arg in kwargs and len(questions) > 0:
                    import concurrent.futures as _futures_mod
                    _max_w = concurrency if concurrency > 0 else len(questions)

                    def _call_one_sync(i: int) -> Any:
                        _kw = dict(kwargs)
                        _kw[questions_arg] = [questions[i]]
                        _kw[ground_truths_arg] = [ground_truths[i]] if i < len(ground_truths) else []
                        if contexts_arg and contexts_arg in _kw and isinstance(_kw.get(contexts_arg), list):
                            _kw[contexts_arg] = [contexts[i]] if contexts and i < len(contexts) else []
                        if expected_tools_arg and expected_tools_arg in _kw and isinstance(_kw.get(expected_tools_arg), list):
                            _kw[expected_tools_arg] = [expected_tools_list[i]] if expected_tools_list and i < len(expected_tools_list) else []
                        _r = func(*args, **_kw)
                        return _r[0] if isinstance(_r, list) and _r else _r

                    responses = [None] * len(questions)
                    with _futures_mod.ThreadPoolExecutor(max_workers=_max_w) as _ex:
                        _fmap = {_ex.submit(_call_one_sync, _i): _i for _i in range(len(questions))}
                        for _fut in _futures_mod.as_completed(_fmap):
                            _idx = _fmap[_fut]
                            try:
                                # A1: item_timeout — 개별 아이템 타임아웃
                                _item_wait = item_timeout if item_timeout is not None else timeout
                                responses[_idx] = _fut.result(timeout=_item_wait) if _item_wait else _fut.result()
                            except Exception as _fe:
                                responses[_idx] = ""
                                if not has_error:
                                    has_error = True
                                    error_msg = str(_fe)
                                # A1: 개별 아이템 실패 추적
                                _item_failures.append({
                                    "index": _idx,
                                    "question": questions[_idx] if _idx < len(questions) else "",
                                    "error": _fe,
                                })
                                if on_item_error is not None:
                                    try:
                                        on_item_error(
                                            _idx,
                                            questions[_idx] if _idx < len(questions) else "",
                                            _fe,
                                        )
                                    except Exception as _oie_exc:
                                        logger.debug("on_item_error 콜백 실패 (무시): %s", _oie_exc)
                elif timeout is not None:  # Gap X: 배치 전체 timeout
                    import concurrent.futures as _futures_mod2
                    with _futures_mod2.ThreadPoolExecutor(max_workers=1) as _ex:
                        try:
                            responses = _ex.submit(func, *args, **kwargs).result(timeout=timeout)
                        except _futures_mod2.TimeoutError:
                            raise TimeoutError(f"batch exceeded {timeout}s")
                else:
                    responses = func(*args, **kwargs)
                return responses
            except Exception as exc:
                has_error = True
                error_msg = str(exc)
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)  # Gap L
                # A1: wrapper._last_failures 저장 (concurrent 실패 목록)
                wrapper._last_failures = list(_item_failures)  # type: ignore[attr-defined]
                try:
                    # SPEC-006 REQ-4: concurrent_judge=True (옵트인)면 judge 대상을 적재해뒀다가
                    # asyncio.gather 기반으로 동시 처리한다. 기본값(False)은 기존과 동일하게
                    # _record_batch() 내부에서 항목별 순차 judge 처리(record_task 동기 호출).
                    _sync_async_judge_targets: list[Any] = []
                    _batch_task_results = _record_batch(
                        questions, ground_truths, responses,
                        elapsed, has_error, error_msg, batch_uuid,
                        eval_ctx=eval_ctx,
                        contexts=contexts,
                        expected_tools_list=expected_tools_list,
                        use_async_judge=concurrent_judge,
                        async_judge_targets=_sync_async_judge_targets if concurrent_judge else None,
                    )
                    if concurrent_judge and _sync_async_judge_targets:
                        try:
                            asyncio.run(_process_async_judge_targets(_sync_async_judge_targets))
                        except RuntimeError as _loop_exc:
                            # 이미 실행 중인 이벤트 루프 안에서 호출된 경우(드묾) — 동시 처리를
                            # 생략하고 조용히 무시한다 (judge 결과 없이도 나머지 기록은 정상 완료됨).
                            logger.debug(
                                "SPEC-006: concurrent_judge asyncio.run 실패 (무시): %s", _loop_exc
                            )
                    wrapper._last_task_results = _batch_task_results or []  # type: ignore[attr-defined]
                    _last_batch_results_holder[0] = _batch_task_results or []  # A8: shared holder
                    _maybe_flush_batch()
                except Exception as rec_exc:
                    logger.debug("batch_eval: record 실패: %s", rec_exc)
                    wrapper._last_task_results = []  # type: ignore[attr-defined]
                    _last_batch_results_holder[0] = []  # A8: shared holder reset

        # A8: return_format 후처리 래퍼
        _original_wrapper = wrapper
        if return_format in ("tuple", "dataframe"):
            @functools.wraps(func)
            def wrapper_with_format(*args, **kwargs):  # type: ignore[misc]
                _resp = _original_wrapper(*args, **kwargs)
                _trs = _last_batch_results_holder[0]  # A8: use shared holder
                if return_format == "tuple":
                    return (_resp, _trs)
                elif return_format == "dataframe":
                    try:
                        import pandas as pd
                        _rows = []
                        for _tr in _trs:
                            _tu = getattr(_tr, "tokens_used", None) or {}
                            _rows.append({
                                "task_id":          getattr(_tr, "task_id", ""),
                                "task_type":        getattr(_tr, "task_type", ""),
                                "success":          getattr(_tr, "success", None),
                                "accuracy_score":   getattr(_tr, "accuracy_score", None),
                                "completion_score": getattr(_tr, "completion_score", None),
                                "execution_time":   getattr(_tr, "execution_time", None),
                                "errors":           getattr(_tr, "errors", []),
                                # D3: 추가 필드
                                "tokens_total":     _tu.get("total") if isinstance(_tu, dict) else None,
                                "tokens_input":     _tu.get("input") if isinstance(_tu, dict) else None,
                                "tokens_output":    _tu.get("output") if isinstance(_tu, dict) else None,
                                "framework":        getattr(_tr, "framework", None) or (_tu.get("model") if isinstance(_tu, dict) else None),
                                "tool_call_count":  len(getattr(_tr, "tool_calls", None) or []),
                                "has_error":        bool(getattr(_tr, "errors", None)),
                                "attempts":         getattr(_tr, "attempts", 1),
                                "timestamp":        getattr(_tr, "timestamp", ""),
                                "response":         str(getattr(_tr, "response", ""))[:200],
                            })
                        return pd.DataFrame(_rows)
                    except ImportError:
                        logger.warning(
                            "return_format='dataframe' requires pandas "
                            "(pip install pandas). Returning raw list instead."
                        )
                        return _resp
                return _resp
            wrapper_with_format._last_failures = []  # type: ignore[attr-defined]
            wrapper_with_format._last_task_results = []  # type: ignore[attr-defined]
            wrapper = wrapper_with_format  # type: ignore[assignment]

        wrapper._last_failures = []  # type: ignore[attr-defined]  # A1: 초기화 (첫 호출 전 속성 존재 보장)
        wrapper._last_task_results = []  # type: ignore[attr-defined]  # A8: 초기화

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return await func(*args, **kwargs)
            questions, ground_truths, contexts, expected_tools_list = _resolve_batch_args(*args, **kwargs)
            batch_uuid = uuid.uuid4().hex[:8]
            start = time.perf_counter()
            has_error = False
            error_msg: str | None = None
            responses: Any = None
            eval_ctx, _ctx_token = _push_ctx()  # Gap L

            try:
                if concurrency > 0 and questions_arg in kwargs and len(questions) > 0:
                    # concurrency>0: 항목별 병렬 실행 — asyncio.gather
                    _sem: asyncio.Semaphore | None = (
                        asyncio.Semaphore(concurrency) if concurrency > 0 else None
                    )

                    async def _call_one(i: int) -> Any:
                        _kw = {**kwargs, questions_arg: [questions[i]]}
                        _kw[ground_truths_arg] = [ground_truths[i]] if i < len(ground_truths) else []
                        if contexts_arg and contexts_arg in _kw and isinstance(_kw.get(contexts_arg), list):
                            _kw[contexts_arg] = [contexts[i]] if contexts and i < len(contexts) else []
                        if expected_tools_arg and expected_tools_arg in _kw and isinstance(_kw.get(expected_tools_arg), list):
                            _kw[expected_tools_arg] = [expected_tools_list[i]] if expected_tools_list and i < len(expected_tools_list) else []
                        # item_timeout 우선, 없으면 배치 전체 timeout 사용
                        _item_wait = item_timeout if item_timeout is not None else timeout
                        if _sem:
                            async with _sem:
                                _r = await (
                                    asyncio.wait_for(func(*args, **_kw), timeout=_item_wait)
                                    if _item_wait else func(*args, **_kw)
                                )
                        else:
                            _r = await (
                                asyncio.wait_for(func(*args, **_kw), timeout=_item_wait)
                                if _item_wait else func(*args, **_kw)
                            )
                        return _r[0] if isinstance(_r, list) and _r else _r

                    gathered = await asyncio.gather(
                        *[_call_one(i) for i in range(len(questions))],
                        return_exceptions=True,
                    )
                    responses = []
                    for _i, _r in enumerate(gathered):
                        if isinstance(_r, BaseException):
                            responses.append("")
                            if not has_error:
                                has_error = True
                                error_msg = str(_r)
                            if on_item_error is not None:
                                try:
                                    on_item_error(
                                        _i,
                                        questions[_i] if _i < len(questions) else "",
                                        _r,
                                    )
                                except Exception as _oie_exc:
                                    logger.debug("on_item_error 콜백 실패 (무시): %s", _oie_exc)
                        else:
                            responses.append(_r)
                elif timeout is not None:  # Gap X: 비동기 배치 timeout (순차)
                    responses = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                else:
                    responses = await func(*args, **kwargs)
                return responses
            except Exception as exc:
                has_error = True
                error_msg = str(exc)
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)  # Gap L
                try:
                    # SPEC-006 REQ-4: concurrent_judge=True (옵트인)면 judge 대상을 적재해뒀다가
                    # asyncio.gather 기반으로 동시 처리한다. 기본값(False)은 기존과 동일하게
                    # _record_batch() 내부에서 항목별 순차 judge 처리(record_task 동기 호출).
                    _async_judge_targets_batch: list[Any] = []
                    # H2: store return value so _last_task_results is populated for async too
                    _async_batch_task_results = _record_batch(
                        questions, ground_truths, responses,
                        elapsed, has_error, error_msg, batch_uuid,
                        eval_ctx=eval_ctx,
                        contexts=contexts,
                        expected_tools_list=expected_tools_list,
                        use_async_judge=concurrent_judge,
                        async_judge_targets=_async_judge_targets_batch if concurrent_judge else None,
                    )
                    if concurrent_judge and _async_judge_targets_batch:
                        await _process_async_judge_targets(_async_judge_targets_batch)
                    async_wrapper._last_task_results = _async_batch_task_results or []  # type: ignore[attr-defined]
                    _last_batch_results_holder[0] = _async_batch_task_results or []
                    _maybe_flush_batch()
                except Exception as rec_exc:
                    logger.debug("batch_eval (async): record 실패: %s", rec_exc)
                    async_wrapper._last_task_results = []  # type: ignore[attr-defined]
                    _last_batch_results_holder[0] = []

        async_wrapper._last_task_results = []  # type: ignore[attr-defined]  # H2: initialize before first call

        # M4: return_format 후처리 — async 함수에도 tuple/dataframe 지원
        _original_async_wrapper = async_wrapper
        if is_async and return_format in ("tuple", "dataframe"):
            @functools.wraps(func)
            async def async_wrapper_with_format(*args, **kwargs):  # type: ignore[misc]
                _resp = await _original_async_wrapper(*args, **kwargs)
                _trs = _last_batch_results_holder[0]
                if return_format == "tuple":
                    return (_resp, _trs)
                elif return_format == "dataframe":
                    try:
                        import pandas as pd
                        _rows = []
                        for _tr in _trs:
                            _tu = getattr(_tr, "tokens_used", None) or {}
                            _rows.append({
                                "task_id":          getattr(_tr, "task_id", ""),
                                "task_type":        getattr(_tr, "task_type", ""),
                                "success":          getattr(_tr, "success", None),
                                "accuracy_score":   getattr(_tr, "accuracy_score", None),
                                "completion_score": getattr(_tr, "completion_score", None),
                                "execution_time":   getattr(_tr, "execution_time", None),
                                "errors":           getattr(_tr, "errors", []),
                            })
                        return pd.DataFrame(_rows)
                    except ImportError:
                        logger.warning(
                            "return_format='dataframe' requires pandas. Returning raw list instead."
                        )
                        return _resp
                return _resp
            async_wrapper_with_format._last_task_results = []  # type: ignore[attr-defined]
            async_wrapper = async_wrapper_with_format  # type: ignore[assignment]

        return async_wrapper if is_async else wrapper

    return decorator


# ---------------------------------------------------------------------------
# eval_context — agent_eval 컨텍스트 매니저 모드 전용 클래스
# agent_eval(monitor, question="Q") as ctx: 패턴으로도 동일하게 사용 가능.
# ---------------------------------------------------------------------------
# eval_context — 컨텍스트 매니저 방식 평가 (데코레이터 불가 코드용)
# ---------------------------------------------------------------------------

class eval_context:
    """데코레이터를 적용할 수 없는 코드에 대한 컨텍스트 매니저 방식 평가.

    외부 라이브러리 함수, lambda, 동적 호출 등에서 ``@agent_eval`` 과 동일한
    평가를 수행한다. ``with`` 블록 내에서 ``ctx.response`` 를 설정하면 ``__exit__``
    시점에 ``TaskResult`` 가 생성·기록된다. 동기·비동기 모두 지원한다.

    ``get_eval_ctx()`` 를 통한 메타데이터 주입도 ``with`` 블록 내에서 동일하게 동작한다.

    Args:
        monitor: :class:`~agent_evaluator.PerformanceMonitor` 인스턴스.
        task_type: Task 유형 (기본: ``"qa"``).
        question: 평가할 질문 문자열.
        ground_truth: 정답 문자열 (기본: ``""``).
        context: RAG context 문자열. 지정 시 HallucinationDetector 에 전달.
        expected_tools: expected tool 목록. ToolSelectionTracker F1 계산에 사용.
        framework: 프레임워크 식별자 (기본: ``"native"``).
        model_name: LLM 모델명.
        task_id: task_id 를 직접 지정. ``None`` 이면 ``{prefix}_{uuid8}`` 자동 생성.
        task_id_prefix: 자동 생성 task_id 접두어 (기본: ``"eval"``).
        score_fn: 커스텀 accuracy 계산 함수 ``(response, gt) -> float``.
        completion_fn: 커스텀 completion 계산 함수.
        on_record: 기록 후 호출되는 콜백 ``(task_result) -> None``.
        timeout: ``with`` 블록 최대 허용 시간(초). 초과 시 ``has_error=True`` 로 기록됨.
            실제 코드 실행을 중단하지는 않고 결과를 오류로 표시한다.

    Attributes:
        response: ``with`` 블록 내에서 설정할 응답 문자열 또는 LLM 응답 객체.
            ``None`` 이면 빈 문자열로 처리된다.

    Examples::

        # 기본 사용
        with eval_context(monitor, task_type="qa",
                          question="한국의 수도는?", ground_truth="서울") as ctx:
            ctx.response = third_party_llm.call("한국의 수도는?")

        # get_eval_ctx() 메타데이터 주입 병행
        with eval_context(monitor, task_type="tool_use", question=q) as ctx:
            result = external_agent.run(q)
            ctx.response = result["output"]
            ec = get_eval_ctx()
            if ec:
                ec.framework = "langchain"
                ec.chain_steps = parse_steps(result)

        # 비동기
        async with eval_context(monitor, task_type="qa", question=q) as ctx:
            ctx.response = await async_llm.call(q)
    """

    def __init__(
        self,
        monitor: Union[PerformanceMonitor, list[PerformanceMonitor]],
        task_type: str = "qa",
        *,
        question: str = "",
        ground_truth: str = "",
        context: str | None = None,
        expected_tools: list[str] | None = None,
        framework: str = "native",
        model_name: str = "",
        task_id: str | None = None,
        task_id_prefix: str = "eval",
        task_id_fn: Callable | None = None,  # Gap AS
        score_fn: Callable | None = None,
        completion_fn: Callable | None = None,
        on_record: Callable | None = None,
        on_error: Callable | None = None,      # (task_result) → None — 오류 시 호출
        alert_rules: list[Any] | None = None,  # SimpleTaskAlertRule 리스트
        sample_rate: float = 1.0,  # Gap R: 컨텍스트 매니저 수준 샘플링
        enabled: bool = True,       # Gap R: 컨텍스트 매니저 수준 활성화
        timeout: float | None = None,  # with 블록 최대 허용 시간(초); 초과 시 has_error=True 기록
        auto_task_id: bool = False,       # A8: True이면 UUID prefix를 "auto"로 변경 (명시적 자동 생성)
        ttft_seconds: float | None = None,  # E4: 외부에서 측정한 TTFT 값 직접 주입 (chunk_step 없이 사용)
    ) -> None:
        self._monitor = monitor
        self._task_type = task_type
        self._context = context
        self._expected_tools = expected_tools
        self._framework = framework
        self._model_name = model_name
        self._score_fn = score_fn
        self._completion_fn = completion_fn
        self._on_error = on_error
        # alert_rules → on_record 통합
        if alert_rules:
            self._on_record = _make_alert_on_record(alert_rules, on_record)
        else:
            self._on_record = on_record
        self._sample_rate = sample_rate
        self._enabled = enabled
        # Gap AS: task_id priority: task_id > task_id_fn > auto
        # A8: auto_task_id=True이면 "auto_{uuid8}" prefix 사용
        if task_id is not None:
            if auto_task_id:
                logger.warning(
                    "auto_task_id=True가 지정됐지만 task_id=%r가 있어 task_id를 사용합니다",
                    task_id,
                )
            self._task_id = task_id
            self._task_id_fn: Callable | None = None
        elif task_id_fn is not None:
            self._task_id_fn = task_id_fn
            self._task_id: str | None = None  # will be set in __enter__
        else:
            # A8: auto_task_id=True이면 "auto_{uuid8}", False이면 기존 "{prefix}_{uuid8}"
            if auto_task_id:
                self._task_id = f"auto_{uuid.uuid4().hex[:8]}"
            else:
                self._task_id = f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
            self._task_id_fn = None
        self._task_id_prefix = task_id_prefix

        # Gap K: 공개 속성 — with 블록 내에서 자유롭게 재설정 가능
        self.question: str = question
        self.ground_truth: str = ground_truth
        self.response: Any = None          # 사용자가 with 블록 내에서 설정

        self._timeout = timeout
        self._start: float = 0.0
        self._eval_ctx: _EvalContext | None = None
        self._ctx_token: Any = None
        self._skip: bool = False  # Gap R: True 이면 __exit__ 에서 기록 생략
        # A4: nested depth 추적
        self._depth_val: int = 1
        self._prev_depth_token: Any = None
        # A2: chunk-level streaming metrics
        self._chunk_steps: list[dict[str, Any]] = []
        # G1: 첫 청크 TTFT (None = 미기록); E4: 외부 주입값 있으면 사전 설정
        self._ttft_seconds: float | None = ttft_seconds

    def chunk_step(self, content: str = "", metadata: dict[str, Any] | None = None) -> eval_context:
        """스트리밍 응답의 청크 단위 메트릭을 기록한다 (A2).

        ``with eval_context(...)`` 블록 내에서 스트리밍 청크마다 호출한다.
        ``__exit__`` 시점에 ``extra["streaming_steps"]``, ``extra["chunk_count"]``,
        ``extra["total_chunk_chars"]`` 로 자동 저장된다.

        Args:
            content: 청크 내용 문자열.
            metadata: 청크별 추가 메타데이터 (선택).

        Returns:
            self (method chaining 지원).

        Example::

            with eval_context(monitor, "qa", question=q) as ctx:
                for chunk in streaming_llm.stream(q):
                    ctx.chunk_step(content=chunk.text, metadata={"tokens": chunk.token_count})
                    ctx.response = (ctx.response or "") + chunk.text
        """
        _elapsed = time.perf_counter() - self._start if self._start else 0.0
        # G1: 첫 청크 → TTFT 자동 기록
        if not self._chunk_steps and self._ttft_seconds is None:
            self._ttft_seconds = _elapsed
        step: dict[str, Any] = {
            "index": len(self._chunk_steps),
            "content_length": len(content),
            "timestamp": _elapsed,
        }
        if metadata:
            step.update(metadata)
        self._chunk_steps.append(step)
        return self

    def add_step(
        self,
        step_name: str,
        duration_s: float | None = None,
        step_type: str = "step",
        success: bool = True,
        output: str | None = None,
    ) -> eval_context:
        """현재 스텝을 chain_steps에 추가한다 (Item X).

        스트리밍 청크 기록과 달리 이름 있는 파이프라인 스텝(retrieval, ranking,
        generation 등)을 명시적으로 기록할 때 사용한다.
        ``__exit__`` 시점에 ``extra["chain_steps"]`` 로 자동 저장된다.

        Args:
            step_name: 스텝 이름 (예: ``"retrieval"``, ``"generation"``).
            duration_s: 스텝 실행 시간(초). ``None`` 이면 ``0.0`` 으로 기록.
            step_type: 스텝 타입 (``"retrieval"`` / ``"ranking"`` / ``"generation"`` /
                ``"tool_call"`` 등).
            success: 스텝 성공 여부.
            output: 스텝 출력 결과 (최대 200자 자동 절단).

        Returns:
            self (method chaining 지원).

        Example::

            with eval_context(monitor, "qa", question=q) as ctx:
                ctx.add_step("retrieval", duration_s=0.3, step_type="retrieval")
                ctx.add_step("ranking", duration_s=0.1, step_type="ranking")
                ctx.add_step("generation", duration_s=1.2, step_type="generation")
                ctx.response = llm.generate(q)
        """
        if not hasattr(self, "_named_steps"):
            self._named_steps: list[dict[str, Any]] = []
        step: dict[str, Any] = {
            "name": step_name,
            "type": step_type,
            "success": success,
            "execution_time": duration_s if duration_s is not None else 0.0,
        }
        if output is not None:
            step["output"] = str(output)[:200]
        self._named_steps.append(step)
        # eval_ctx의 chain_steps에도 반영 (주입 가능한 경우)
        if self._eval_ctx is not None:
            existing = getattr(self._eval_ctx, "chain_steps", None) or []
            self._eval_ctx.chain_steps = list(existing) + [step]
        return self

    @property
    def depth(self) -> int:
        """현재 중첩 깊이 (1 = 최상위).

        ``with eval_context(...)`` 블록 내에서 호출하면 몇 겹으로 중첩됐는지 반환한다.
        ``contextvars.Token`` 기반으로 동시 코루틴에서도 정확히 동작한다.

        Example::

            with eval_context(monitor, "qa", question=q) as ctx:
                assert ctx.depth == 1
                with eval_context(monitor, "qa", question=q2) as inner:
                    assert inner.depth == 2
        """
        return getattr(self, "_depth_val", 1)

    # --- sync ---

    def __enter__(self) -> eval_context:
        # Gap R: enabled / sample_rate 체크 — skip 이면 ctx push 도 생략
        if not self._enabled or (self._sample_rate < 1.0 and random.random() > self._sample_rate):
            self._skip = True
            return self
        # Gap AS: task_id_fn 지연 평가
        if self._task_id is None and self._task_id_fn is not None:
            try:
                self._task_id = str(self._task_id_fn())
            except Exception:
                self._task_id = f"eval_{uuid.uuid4().hex[:8]}"
        self._start = time.perf_counter()
        self._eval_ctx, self._ctx_token = _push_ctx()
        # A4: 중첩 깊이 업데이트
        self._prev_depth_token = _NEST_DEPTH.set(_NEST_DEPTH.get() + 1)
        self._depth_val = _NEST_DEPTH.get()
        # G2: 중첩 깊이 과다 경고
        if self._depth_val > MAX_NESTING_DEPTH:
            import warnings
            warnings.warn(
                f"eval_context 중첩 깊이 {self._depth_val}가 MAX_NESTING_DEPTH={MAX_NESTING_DEPTH}를 초과했습니다. "
                "컨텍스트 누수가 발생할 수 있습니다.",
                ResourceWarning,
                stacklevel=3,
            )
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> bool:
        # Gap R: skip 이면 기록 없이 반환
        if self._skip:
            return False
        elapsed = time.perf_counter() - self._start
        _pop_ctx(self._ctx_token)
        # A4: 중첩 깊이 복원
        if self._prev_depth_token is not None:
            try:
                _NEST_DEPTH.reset(self._prev_depth_token)
            except Exception:
                pass
        # timeout 초과 시 TimeoutError 로 처리 (실제 중단은 불가, 기록 수준 처리)
        if self._timeout is not None and elapsed > self._timeout and exc_type is None:
            has_error = True
            error_msg = f"eval_context exceeded timeout of {self._timeout}s (elapsed={elapsed:.2f}s)"
        else:
            has_error = exc_type is not None
            error_msg = str(exc_val) if exc_val is not None else None
        # Safety fallback for task_id (should not happen normally)
        task_id = self._task_id or f"{self._task_id_prefix}_{uuid.uuid4().hex[:8]}"
        # A2: chunk-level streaming metrics → extra 필드에 저장
        _extra_override: dict[str, Any] | None = None
        if self._chunk_steps:
            _extra_override = {
                "streaming_steps": self._chunk_steps,
                "chunk_count": len(self._chunk_steps),
                "total_chunk_chars": sum(s.get("content_length", 0) for s in self._chunk_steps),
            }
        # Item X: add_step() 으로 추가된 named steps → extra["chain_steps"] 에 저장
        _named_steps = getattr(self, "_named_steps", None)
        if _named_steps:
            if _extra_override is None:
                _extra_override = {}
            _extra_override["chain_steps"] = _named_steps
        _build_and_record(
            self._monitor,
            task_type=self._task_type,
            task_id=task_id,
            question=self.question,        # Gap K: 블록 내 재설정 반영
            ground_truth=self.ground_truth,  # Gap K
            context=self._context,
            expected_tools_from_arg=self._expected_tools,
            elapsed=elapsed,
            raw=self.response,
            has_error=has_error,
            error_msg=error_msg,
            model_name=self._model_name,
            framework=self._framework,
            score_fn=self._score_fn,
            completion_fn=self._completion_fn,
            eval_ctx=self._eval_ctx,
            on_record=self._on_record,
            on_error=self._on_error,
            extra_override=_extra_override,
        )
        # G1: TTFT 자동 기록 — 첫 청크가 있었던 경우 latency_tracker.track_ttft() 호출
        if self._ttft_seconds is not None:
            _monitors = self._monitor if isinstance(self._monitor, list) else [self._monitor]
            for _m in _monitors:
                try:
                    _lt = getattr(_m, "latency_tracker", None)
                    if _lt is not None and hasattr(_lt, "track_ttft"):
                        _lt.track_ttft(task_id, self._ttft_seconds,
                                       task_type=self._task_type)
                except Exception as _ttft_exc:
                    import logging as _logging
                    _logging.getLogger(__name__).debug(
                        "TTFT track_ttft 실패 (무시): %s", _ttft_exc)
        return False  # 예외를 억제하지 않음

    # --- async ---

    async def __aenter__(self) -> eval_context:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> bool:
        return self.__exit__(exc_type, exc_val, exc_tb)


# ---------------------------------------------------------------------------
# 항목 E: _ContextShortcut — EvalDecorator.context 속성 양방향 호출 지원
# ---------------------------------------------------------------------------

class _ContextShortcut:
    """EvalDecorator.context 속성 — ``with eval.context(...)`` 와 ``with eval.context as ctx:`` 모두 지원.

    두 가지 사용 패턴을 지원한다::

        # 파라미터 전달 후 컨텍스트 매니저로 사용
        with eval.context(task_type="qa", timeout=5.0) as ctx:
            ctx.response = agent(question)

        # 기본값으로 즉시 컨텍스트 매니저로 사용
        with eval.context as ctx:
            ctx.response = agent(question)

        # 데코레이터 반환 패턴 (기존 호환)
        ctx_mgr = eval.context(task_type="qa")
        with ctx_mgr as ctx:
            ctx.response = agent(question)
    """

    def __init__(self, eval_dec: EvalDecorator) -> None:
        self._eval_dec = eval_dec
        self._ctx: eval_context | None = None

    def __call__(self, task_type: str | None = None, **kwargs) -> eval_context:
        """``with eval.context(task_type="qa", ...) as ctx:`` 형태 지원."""
        ctx_defaults = {
            "framework": self._eval_dec._defaults.get("framework", "native"),
            "model_name": self._eval_dec._defaults.get("model_name", ""),
            "sample_rate": self._eval_dec._defaults.get("sample_rate", 1.0),
            "enabled": self._eval_dec._defaults.get("enabled", True),
            "score_fn": self._eval_dec._defaults.get("score_fn"),
            "completion_fn": self._eval_dec._defaults.get("completion_fn"),
            "on_record": self._eval_dec._defaults.get("on_record"),
            "on_error": self._eval_dec._defaults.get("on_error"),
            "alert_rules": self._eval_dec._defaults.get("alert_rules"),
            "timeout": self._eval_dec._defaults.get("timeout"),
        }
        merged: dict[str, Any] = {k: v for k, v in ctx_defaults.items() if v is not None or k in ("framework", "model_name")}
        merged.update(kwargs)
        _task_type = task_type if task_type is not None else self._eval_dec._defaults.get("task_type", "qa")
        return eval_context(self._eval_dec._monitor, _task_type, **merged)

    def __enter__(self) -> eval_context:
        """``with eval.context as ctx:`` 형태 (task_type은 defaults 사용)."""
        self._ctx = self.__call__()
        return self._ctx.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if self._ctx is not None:
            return self._ctx.__exit__(exc_type, exc_val, exc_tb)
        return False


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# D1: _ShortcutCallable — EvalDecorator 단축 속성에서 파라미터 전달 지원
# ---------------------------------------------------------------------------

class _ShortcutCallable:
    """EvalDecorator 단축 속성(.qa, .rag 등)의 반환 타입 (D1).

    두 가지 사용 패턴을 모두 지원한다::

        @eval.qa                          # 기존: 파라미터 없이 직접 데코레이터
        def agent(question, ground_truth=""): ...

        @eval.qa(score_fn=my_score)       # 신규: 파라미터 전달 후 데코레이터
        def agent(question, ground_truth=""): ...
    """

    def __init__(self, eval_dec: EvalDecorator, task_type: str, **base_kwargs: Any) -> None:
        self._eval_dec = eval_dec
        self._task_type = task_type
        self._base_kwargs = base_kwargs

    def __call__(self, func_or_none=None, **extra_kwargs):
        """단일 함수(direct decorator) 또는 kwargs(파라미터 전달) 처리."""
        if func_or_none is not None and callable(func_or_none):
            # @eval.qa 형태 — 함수를 직접 전달 받음
            merged = {**self._base_kwargs}
            return self._eval_dec(self._task_type, **merged)(func_or_none)
        # @eval.qa(score_fn=...) 형태 — kwargs를 받고 데코레이터 반환
        if func_or_none is not None:
            # 위치 인자가 함수가 아닌 경우 (오용 방지)
            raise TypeError(
                f"@eval.{self._task_type} 의 첫 번째 인자는 함수여야 합니다. "
                f"파라미터는 키워드로 전달하세요: @eval.{self._task_type}(score_fn=...)"
            )
        merged = {**self._base_kwargs, **extra_kwargs}

        def decorator(func: Callable) -> Callable:
            return self._eval_dec(self._task_type, **merged)(func)

        return decorator

    def __repr__(self) -> str:
        return f"_ShortcutCallable(task_type={self._task_type!r})"


# ---------------------------------------------------------------------------
# EvalDecorator — 팩토리 패턴 (Gap N): 공통 설정 한 번만 지정
# ---------------------------------------------------------------------------

class EvalDecorator:
    """공통 설정(monitor, framework, model_name 등)을 한 번만 지정하고
    여러 함수에 재사용하는 데코레이터 팩토리.

    동일한 ``PerformanceMonitor`` 와 공통 파라미터를 공유하는 에이전트 함수가
    많을 때 반복 코드를 줄여 준다.

    Args:
        monitor: 결과를 기록할 :class:`~agent_evaluator.PerformanceMonitor` 인스턴스.
        framework: 기본 프레임워크 식별자 (기본: ``"native"``).
        model_name: 기본 LLM 모델명 (기본: ``""``).
        sample_rate: 기본 평가 실행 비율 (기본: ``1.0``).
        enabled: 기본 활성화 여부 (기본: ``True``).
        score_fn: 기본 커스텀 accuracy 함수.
        completion_fn: 기본 커스텀 completion 함수.
        on_record: 기본 on_record 콜백.
        task_id_prefix: 기본 task_id 접두어 (기본: ``"task"``).

    Examples::

        # 공통 설정 한 번만
        eval = EvalDecorator(monitor, framework="langchain", model_name="gpt-5-nano")

        @eval(task_type="qa")
        def qa_agent(question, ground_truth=""): ...

        @eval(task_type="tool_use", expected_tools_arg="expected")
        def tool_agent(question, expected=None, ground_truth=""): ...

        @eval.with_retry(task_type="qa", max_retries=3)
        def fragile_agent(question, ground_truth=""): ...

        @eval.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None): ...

        @eval.conversation(session_id_arg="sid", max_turns=5)
        def chat(question, sid="s1"): ...
    """

    # agent_eval / agent_eval_with_retry 에 전달 가능한 공통 파라미터
    # NOTE: 새 파라미터 추가 시 agent_eval 시그니처와 함께 이 frozenset도 업데이트 필요  # A5
    _COMMON_PARAMS: frozenset = frozenset({
        "framework", "model_name", "sample_rate", "enabled",
        "on_record", "score_fn", "completion_fn", "task_id_prefix",
        "alert_rules", "flush_every",
        "custom_parser",                  # A9
        "enable_hallucination_detection",  # G4: per-call hallucination detection (EvalDecorator internal)
        "enable_llm_judge",               # E1: per-call LLM Judge (EvalDecorator internal)
        "judge_model",                    # E1: LLM Judge 모델 (EvalDecorator internal)
        "judge_criteria",                 # J1: G-Eval 스타일 커스텀 평가 기준 (EvalDecorator internal)
        "enable_anomaly_detection",       # E1: per-call anomaly detection
        "security",                       # SecurityConfig 통합
        "llm_judge",                      # LLMJudgeConfig 통합
        "timeout",                        # A: 함수 실행 최대 허용 시간(초)
    })
    # batch_eval 이 지원하는 _defaults 파라미터 — _COMMON_PARAMS 초과분 포함
    # NOTE: 새 파라미터 추가 시 batch_eval 시그니처와 함께 이 frozenset도 업데이트 필요  # A5
    _BATCH_PARAMS: frozenset = frozenset({
        "framework", "model_name", "sample_rate", "enabled",
        "on_record", "on_error", "score_fn", "completion_fn",
        "task_id_prefix", "task_id_fn",
        "alert_rules", "flush_every",
        "timeout", "context_arg", "expected_tools_arg",
        "on_batch_progress",  # Gap BA / Gap I
        "on_batch_complete",  # AM: 배치 전체 완료 콜백
        "item_timeout",       # A1: 개별 아이템 타임아웃
        "return_format",      # A8: 반환 형식 (list/tuple/dataframe)
        "streaming_mode",     # G1: 메모리 효율적 스트리밍 모드
        "preset",             # A1: 사전 정의 파라미터 묶음
        # H3: LLM Judge parity with agent_eval
        "enable_llm_judge", "judge_model", "judge_criteria",
        "security",           # SecurityConfig 통합
        "llm_judge",          # LLMJudgeConfig 통합
        "concurrency",        # concurrent execution
        # v0.9.0+: Phase 1 Harness Config
        "instructions", "loop_detection", "goal_alignment", "reproducibility", "fault_tolerance", "plan_tracking",
        # v0.9.1+: 신규 Harness Config
        "sla", "threat_severity", "efficiency", "state_consistency", "deadlock", "observability", "consensus",
        # v0.9.2+: Phase 3 Harness Config
        "scope", "context_retention", "explainability", "subtask_tracking", "propagation",
        # v0.9.3+: Phase 4 Harness Config
        "agent_role", "graceful_degradation", "compliance", "resource_budget", "conflict_resolution",
        # v0.9.4+: Phase 5 Harness Config
        "tool_parameter_safety", "knowledge_retention", "retry_consistency", "error_diagnosis",
        # v0.9.5+: Phase 6 Harness Config
        "idempotency", "threat_response", "context_window", "latency_attribution",
    })
    # conversation_eval 에는 framework/model_name/score_fn/completion_fn 미전달
    _CONV_PARAMS: frozenset = frozenset({
        "sample_rate", "enabled", "alert_rules", "on_session_timeout",  # Gap J
        # A4/D9: 추가 conversation_eval 파라미터
        "on_flush", "on_turn", "session_score_fn", "turn_score_fn",
        "max_turns", "flush_on_error", "max_session_seconds",
        "flush_every",
        "on_error",               # Gap A2: 오류 태스크 기록 후 호출되는 콜백
        "preset",                 # A1: 사전 정의 파라미터 묶음
        "on_record",              # C: 세션 flush 후 마지막 TaskResult에 호출되는 콜백
        "llm_judge",              # LLMJudgeConfig 통합
        # v0.9.0+: Phase 1 Harness Config
        "instructions", "loop_detection", "goal_alignment", "reproducibility",
        "fault_tolerance", "plan_tracking",
        # v0.9.1+: 신규 Harness Config
        "sla", "threat_severity", "efficiency", "state_consistency", "deadlock",
        "observability", "consensus",
        # v0.9.2+: Phase 3 Harness Config
        "scope", "context_retention", "explainability", "subtask_tracking", "propagation",
        # v0.9.3+: Phase 4 Harness Config
        "agent_role", "graceful_degradation", "compliance", "resource_budget", "conflict_resolution",
        # v0.9.4+: Phase 5 Harness Config
        "tool_parameter_safety", "knowledge_retention", "retry_consistency", "error_diagnosis",
        # v0.9.5+: Phase 6 Harness Config
        "idempotency", "threat_response", "context_window", "latency_attribution",
    })

    @classmethod
    def _auto_common_params(cls) -> frozenset:
        """agent_eval 함수 시그니처에서 자동으로 common 파라미터 추출.  # A5

        ``_COMMON_PARAMS`` 와의 동기화를 검증하거나 런타임에 파라미터 목록을
        갱신할 때 사용한다. 예외 시 ``_COMMON_PARAMS`` 를 그대로 반환한다.

        Example::

            params = EvalDecorator._auto_common_params()
            # agent_eval 시그니처에서 monitor / task_type 을 제외한 파라미터 집합 반환
        """
        try:
            sig = inspect.signature(agent_eval)
            return frozenset(sig.parameters.keys()) - {"monitor", "task_type"}
        except Exception:
            return cls._COMMON_PARAMS

    def __init__(
        self,
        monitor: Union[PerformanceMonitor, list[PerformanceMonitor]],
        *,
        framework: Union[FrameworkLiteral, str] = "native",
        model_name: str = "",
        sample_rate: float = 1.0,
        enabled: bool = True,
        score_fn: Callable | None = None,
        completion_fn: Callable | None = None,
        on_record: Callable | None = None,
        on_error: Callable | None = None,      # Gap AK
        task_id_prefix: str = "task",
        # Gap AI: agent_eval 파라미터 기본값 — 반복 지정 불필요
        question_arg: str = "question",
        ground_truth_arg: str = "ground_truth",
        context_arg: str | None = None,
        expected_tools_arg: str | None = None,
        task_id_fn: Callable | None = None,
        timeout: float | None = None,
        alert_rules: list[Any] | None = None,  # SimpleTaskAlertRule 리스트 기본값
        flush_every: int | None = None,         # N 태스크마다 자동 save_to_file
        custom_parser: Callable | None = None,     # A9: framework adapter 전 EvalMetadata 생성
        # H4: 단축 속성에서 자동 전파되는 eval 모드 플래그
        enable_llm_judge: bool = False,
        judge_model: str | None = None,
        judge_criteria: list[str] | None = None,  # J1: G-Eval 스타일 커스텀 평가 기준
        enable_anomaly_detection: bool = False,
        enable_hallucination_detection: bool = False,  # per-call hallucination detection
        enable_hallucination: bool = False,            # legacy alias for enable_hallucination_detection
        security: SecurityConfig | None = None,  # SecurityConfig 통합
        llm_judge: LLMJudgeConfig | None = None,  # LLMJudgeConfig 통합
        # A9: sample_condition — 조건부 샘플링 (args, kwargs) → bool
        sample_condition: Callable | None = None,
    ) -> None:
        self._monitor = monitor
        # Legacy alias: enable_hallucination → enable_hallucination_detection
        if enable_hallucination and not enable_hallucination_detection:
            enable_hallucination_detection = True
        self._defaults: dict[str, Any] = {
            "framework": framework,
            "model_name": model_name,
            "sample_rate": sample_rate,
            "enabled": enabled,
            "score_fn": score_fn,
            "completion_fn": completion_fn,
            "on_record": on_record,
            "on_error": on_error,                 # Gap AK
            "task_id_prefix": task_id_prefix,
            # Gap AI
            "question_arg": question_arg,
            "ground_truth_arg": ground_truth_arg,
            "context_arg": context_arg,
            "expected_tools_arg": expected_tools_arg,
            "task_id_fn": task_id_fn,
            "timeout": timeout,
            "alert_rules": alert_rules,
            "flush_every": flush_every,
            "custom_parser": custom_parser,        # A9
            # H4: eval 모드 플래그
            "enable_anomaly_detection": enable_anomaly_detection,
            "enable_hallucination_detection": enable_hallucination_detection,
            "security": security,
            "llm_judge": llm_judge,
            "sample_condition": sample_condition,
        }

    @property
    def monitor(self) -> Union[PerformanceMonitor, list[PerformanceMonitor]]:
        """기저 :class:`~agent_evaluator.PerformanceMonitor` 인스턴스 반환 (Gap AA).

        ``for_rag()`` / ``for_security()`` 로 생성한 경우에도 동일하게 접근한다.

        Example::

            eval = EvalDecorator.for_rag("results/")
            eval.monitor.save_to_file("rag_results")
        """
        return self._monitor

    def inspect(self) -> dict[str, Any]:
        """현재 EvalDecorator에 적용된 기본값(defaults)을 반환한다 (Item U).

        Returns:
            적용된 파라미터 딕셔너리 (예: ``{"framework": "langchain", "sample_rate": 0.5, ...}``).

        Example::

            eval = EvalDecorator(monitor, framework="langchain", sample_rate=0.5)
            config = eval.inspect()
            # {"framework": "langchain", "sample_rate": 0.5, ...}
        """
        return dict(self._defaults)

    # Item U: 별칭
    get_config = inspect

    def __call__(self, task_type: str = "qa", **kwargs) -> Callable:
        """``@agent_eval`` 데코레이터 반환.

        파라미터 우선순위: 개별 데코레이터 파라미터 > EvalDecorator 기본값(_defaults) > 함수 기본값

        Example::

            @eval(task_type="qa")
            def agent(question, ground_truth=""): ...

            # 개별 파라미터가 EvalDecorator 기본값보다 우선 적용됨
            @eval(task_type="qa", model_name="gpt-4o")  # model_name 재정의
            def agent2(question, ground_truth=""): ...
        """
        merged = {**self._defaults, **kwargs}
        # EvalDecorator 전용 키를 agent_eval 파라미터로 변환
        # A9: sample_condition 추출 (agent_eval에 없으므로 별도 처리)
        _sample_cond = merged.pop("sample_condition", None)
        # enable_hallucination → enable_hallucination_detection
        if merged.pop("enable_hallucination", False):
            merged.setdefault("enable_hallucination_detection", True)
        # enable_llm_judge/judge_model/judge_criteria → llm_judge=LLMJudgeConfig(...)
        _elj = merged.pop("enable_llm_judge", False)
        _jm = merged.pop("judge_model", None)
        _jc = merged.pop("judge_criteria", None)
        if _elj and "llm_judge" not in merged:
            merged["llm_judge"] = LLMJudgeConfig(model=_jm, criteria=_jc)
        # agent_eval이 허용하는 파라미터만 전달 (나머지 EvalDecorator 전용 키 필터링)
        try:
            _ae_sig = inspect.signature(agent_eval)
            _ae_params = set(_ae_sig.parameters.keys()) - {"monitor_or_fn", "task_type"}
            merged = {k: v for k, v in merged.items() if k in _ae_params}
        except Exception:
            pass
        _decorator = agent_eval(self._monitor, task_type, **merged)
        # A9: sample_condition 적용 — False 반환 시 평가 skip (원본 함수 직접 호출)
        if _sample_cond is None:
            return _decorator

        def _sc_decorator(func: Callable) -> Callable:
            _wrapped = _decorator(func)
            @functools.wraps(func)
            def _sc_wrapper(*args, **kw):
                try:
                    _should = bool(_sample_cond(args, kw))
                except Exception:
                    _should = True
                if _should:
                    return _wrapped(*args, **kw)
                return func(*args, **kw)
            return _sc_wrapper

        return _sc_decorator

    def with_retry(self, task_type: str = "qa", **kwargs) -> Callable:
        """``@agent_eval_with_retry`` 데코레이터 반환.

        Example::

            @eval.with_retry(task_type="qa", max_retries=3, retry_on=(ConnectionError,))
            def fragile(question, ground_truth=""): ...
        """
        merged = {**self._defaults, **kwargs}
        # agent_eval이 허용하는 파라미터만 전달 (EvalDecorator 전용 키 필터링)
        try:
            _ae_sig = inspect.signature(agent_eval)
            _ae_params = set(_ae_sig.parameters.keys()) - {"monitor_or_fn", "task_type"}
            merged = {k: v for k, v in merged.items() if k in _ae_params}
        except Exception:
            pass
        return agent_eval_with_retry(self._monitor, task_type, **merged)

    def batch(self, task_type: str = "qa", **kwargs) -> Callable:  # A7: 반환 타입 Callable 명시
        """``@batch_eval`` 데코레이터 반환.

        Example::

            @eval.batch(task_type="qa", task_id_prefix="qa_batch")
            def qa_batch(questions, ground_truths=None): ...
        """
        # batch_eval 은 questions_arg / ground_truths_arg 파라미터 이름이 다름
        # _BATCH_PARAMS 기반 전파: on_error, task_id_fn, timeout, context_arg 등 포함
        batch_defaults = {k: v for k, v in self._defaults.items()
                          if k in self._BATCH_PARAMS and v is not None}
        merged = {**batch_defaults, **kwargs}
        return batch_eval(self._monitor, task_type, **merged)

    def conversation(self, **kwargs) -> Callable:  # A7: 반환 타입 Callable 명시
        """``@conversation_eval`` 데코레이터 반환.

        Example::

            @eval.conversation(session_id_arg="sid", max_turns=5)
            def chat(question, sid="s1"): ...
        """
        conv_defaults = {k: v for k, v in self._defaults.items()
                         if k in self._CONV_PARAMS}
        merged = {**conv_defaults, **kwargs}
        # conversation_eval()은 단일 PerformanceMonitor만 지원한다(_do_flush()가
        # stored_monitor.conversation(...)을 리스트 분기 없이 직접 호출) — self._monitor가
        # 리스트면 첫 번째 모니터로 폴백해 AttributeError를 방지한다.
        _mon = self._monitor if not isinstance(self._monitor, list) else self._monitor[0]
        return conversation_eval(_mon, **merged)

    @property
    def context(self) -> _ContextShortcut:  # 항목 E: 양방향 호출 지원 — with eval.context(...) / with eval.context as ctx
        """``eval_context`` 컨텍스트 매니저 단축 속성 (항목 E).

        두 가지 사용 패턴을 지원한다::

            # 파라미터 지정 (기존 패턴)
            with eval.context(task_type="qa", question=q, ground_truth=gt) as ctx:
                ctx.response = external_fn(q)

            # 파라미터 없이 즉시 컨텍스트 매니저로 사용 (신규 패턴)
            with eval.context as ctx:
                ctx.question = q
                ctx.response = external_fn(q)
        """
        return _ContextShortcut(self)

    @classmethod
    def for_rag(cls, output_dir: str = "results/", **kwargs) -> EvalDecorator:
        """RAG 평가에 최적화된 ``EvalDecorator`` 팩토리 메서드 (Gap S).

        ``PerformanceMonitor.for_rag_evaluation()`` 로 monitor 를 생성하고
        기본값으로 ``framework="native"`` 를 적용한다.
        hallucination 감지가 기본 활성화된다.

        Example::

            eval = EvalDecorator.for_rag("results/")

            @eval(task_type="information_retrieval", context_arg="ctx")
            def rag_agent(question, ctx="", ground_truth=""): ...
        """
        import warnings as _warnings
        _warnings.warn(
            "EvalDecorator.for_rag() is deprecated. Use QuickEval.for_rag() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor as _PM
        monitor = _PM.for_rag_evaluation(output_dir=output_dir)
        return cls(monitor, **kwargs)

    @classmethod
    def for_security(cls, output_dir: str = "results/", **kwargs) -> EvalDecorator:
        """보안 평가에 최적화된 ``EvalDecorator`` 팩토리 메서드 (Gap S).

        ``PerformanceMonitor.for_secure_agents()`` 로 monitor 를 생성한다.
        보안 지표(InputSanitization, OutputLeakage, ToolAuth 등)가 기본 활성화된다.

        Example::

            eval = EvalDecorator.for_security("results/")

            @eval(task_type="tool_use")
            def secure_agent(question, ground_truth=""): ...
        """
        import warnings as _warnings
        _warnings.warn(
            "EvalDecorator.for_security() is deprecated. Use QuickEval.for_security() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor as _PM
        monitor = _PM.for_secure_agents(output_dir=output_dir)
        return cls(monitor, **kwargs)

    def update_defaults(self, **kwargs) -> EvalDecorator:
        """기본값을 부분 업데이트한다. 변경사항은 이후 생성되는 데코레이터에 적용된다.
        체이닝을 지원한다: ``eval.update_defaults(model_name="gpt-4-turbo").update_defaults(timeout=30)``.

        Returns:
            self (체이닝 지원)
        """
        self._defaults.update(kwargs)
        return self

    def __repr__(self) -> str:
        framework = self._defaults.get("framework", "native")
        model_name = self._defaults.get("model_name", "")
        tcr_tracker = getattr(self._monitor, "tcr_tracker", None)
        tasks = len(tcr_tracker.tasks) if tcr_tracker is not None else 0
        return (
            f"EvalDecorator(framework={framework!r}, model_name={model_name!r}, tasks={tasks})"
        )

    # E1/D1: task_type 단축 속성 — QuickEval과 동일한 편의 문법 지원
    # @eval.qa 또는 @eval.qa(score_fn=...) 모두 지원 (_ShortcutCallable 사용)
    @property
    def qa(self) -> _ShortcutCallable:
        """``@eval.qa`` 또는 ``@eval.qa(score_fn=...)`` 단축키 (D1)."""
        return _ShortcutCallable(self, "qa")

    @property
    def tool_use(self) -> _ShortcutCallable:
        """``@eval.tool_use`` 또는 ``@eval.tool_use(timeout=5.0)`` 단축키 (D1)."""
        return _ShortcutCallable(self, "tool_use")

    @property
    def rag(self) -> _ShortcutCallable:
        """``@eval.rag`` 또는 ``@eval.rag(score_fn=...)`` 단축키 (D1/H4).

        ``rag_mode=True`` + ``context_arg="context"`` 자동 설정.
        """
        return _ShortcutCallable(
            self, "information_retrieval",
            context_arg=self._defaults.get("context_arg") or "context",
            rag_mode=True,
            enable_hallucination=True,
        )

    @property
    def code(self) -> _ShortcutCallable:
        """``@eval.code`` 또는 ``@eval.code(score_fn=...)`` 단축키 (D1)."""
        return _ShortcutCallable(self, "code_generation")

    @property
    def reasoning(self) -> _ShortcutCallable:
        """``@eval.reasoning`` 단축키 (D1)."""
        return _ShortcutCallable(self, "reasoning")

    @property
    def planning(self) -> _ShortcutCallable:
        """``@eval.planning`` 단축키 (D1)."""
        return _ShortcutCallable(self, "planning")

    @property
    def data_analysis(self) -> _ShortcutCallable:
        """``@eval.data_analysis`` 단축키 (D1)."""
        return _ShortcutCallable(self, "data_analysis")

    @property
    def creative(self) -> _ShortcutCallable:
        """``@eval.creative`` 단축키 (D1)."""
        return _ShortcutCallable(self, "creative")

    @property
    def multi_agent(self) -> _ShortcutCallable:
        """``@eval.multi_agent`` 단축키 (D1)."""
        return _ShortcutCallable(self, "tool_use")

    @property
    def secure(self) -> _ShortcutCallable:
        """``@eval.secure`` 단축키 (D1/H4) — ``security=SecurityConfig()`` 자동 설정."""
        return _ShortcutCallable(self, "tool_use", security=SecurityConfig())

    @property
    def streaming(self) -> _ShortcutCallable:
        """``@eval.streaming`` 또는 ``@eval.streaming(score_fn=...)`` 단축키 (D1/D4).

        generator/async generator 함수 평가용. task_type은 agent_eval이 자동 처리.
        """
        return _ShortcutCallable(self, "qa")

    @classmethod
    def for_llm_judge(cls, output_dir: str = "results/", model: str = "gpt-5-nano", **kwargs) -> EvalDecorator:
        """LLM Judge 평가에 최적화된 ``EvalDecorator`` 팩토리 메서드.

        ``LLMJudge`` 와 ``enable_llm_judge=True`` 를 자동 설정한다.
        ``[llm]`` extras 필요: ``pip install "agent-evaluator[llm]"``.

        Example::

            eval = EvalDecorator.for_llm_judge("results/", model="gpt-5-nano")

            @eval(task_type="qa")
            def agent(question, ground_truth=""): ...
        """
        import warnings as _warnings
        _warnings.warn(
            "EvalDecorator.for_llm_judge() is deprecated. Use QuickEval.for_llm_judge() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor as _PM
        try:
            # verify llm_judge import is available before creating monitor
            from agent_evaluator.integrations.llm_judge import LLMJudge  # noqa: F401
            monitor = _PM(output_dir=output_dir, enable_llm_judge=True, judge_model=model)
        except ImportError:
            # llm extras 미설치 시 judge 없이 생성 (graceful degradation)
            logger.debug("LLMJudge 생성 실패 (llm extras 필요) — enable_llm_judge=False 로 fallback")
            monitor = _PM(output_dir=output_dir)
        return cls(monitor, **kwargs)


# ---------------------------------------------------------------------------
# agent_eval_async — agent_eval 의 alias (sync/async 자동 감지하므로 동일)
# ---------------------------------------------------------------------------

agent_eval_async = agent_eval
"""agent_eval 의 별칭. async 함수에 사용하지만 agent_eval 이 이미 자동 감지하므로 동일하다."""

agent_eval_with_retry = agent_eval
"""agent_eval 의 별칭. max_retries/retry_on/delay/backoff 등 재시도 파라미터를 강조하기 위한 alias."""

