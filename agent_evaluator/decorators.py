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
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from agent_evaluator import PerformanceMonitor

# M1: 프레임워크 식별자 Literal — IDE 자동완성 지원 (Python 3.8+ 지원, from __future__ import annotations)
FrameworkLiteral = Literal[
    "native", "langchain", "langgraph", "crewai", "autogen",
    "dspy", "pydanticai", "anthropic", "openai", "gemini",
    "llamaindex", "haystack", "cohere", "groq", "mistral",
    "bedrock", "smolagents", "semantic_kernel", "ollama", "vllm", "huggingface",
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
]


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

    attempts: Optional[int] = None                             # None = 자동 계산 유지 (기본 1)
    framework: Optional[str] = None                            # None = decorator 파라미터 유지
    expected_tools: Optional[List[str]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None         # None = 자동 추출 유지
    agent_interactions: Optional[List[Dict[str, Any]]] = None # CrewAI 멀티에이전트
    chain_steps: Optional[List[Dict[str, Any]]] = None        # LangChain 체인 단계
    graph_traversal: Optional[Dict[str, Any]] = None          # LangGraph 그래프 경로
    state_transitions: Optional[List[Dict[str, Any]]] = None  # LangGraph 상태 전이
    completion_score: Optional[float] = None                   # None = 자동 계산 유지
    accuracy_score: Optional[float] = None                     # None = 자동 계산 유지
    partial_reason: Optional[str] = None
    # Gap J: 비표준 LLM (Mistral 이외) 토큰 수 직접 주입 + 동적 모델명
    tokens_used: Optional[Dict[str, int]] = None               # {"input": n, "output": n, "total": n}
    model_name: Optional[str] = None                           # None = decorator 파라미터 유지
    # Gap P: 평가 시점에 context / ground_truth 를 동적으로 재정의
    context: Optional[str] = None                              # None = _resolve_args 값 유지
    ground_truth: Optional[str] = None                         # None = _resolve_args 값 유지
    # Gap AB: AutoGen conversation_turns 주입
    conversation_turns: Optional[List[Dict[str, Any]]] = None
    # Gap AC: 사전 계산된 LLM Judge 결과 주입
    llm_judge: Optional[Dict[str, Any]] = None
    # Gap AE: 사용자 정의 자유 형식 메타데이터 — TaskResult.extra 에 저장
    extra: Optional[Dict[str, Any]] = None                     # {"intent": "search", "source": "api", ...}
    # Gap AN: 오류 목록 직접 주입
    errors: Optional[List[str]] = None
    # Gap AO: 실행 시간 직접 주입 (자동 측정값 재정의)
    execution_time: Optional[float] = None


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
                model="gpt-4o-mini",
                tokens={"input": result["input_tokens"], "output": result["output_tokens"]},
                tool_calls=result.get("tool_calls"),
            )
    """

    model: Optional[str] = None
    tokens: Optional[Dict[str, int]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    latency: Optional[float] = None      # None = perf_counter 자동 측정값 사용
    ground_truth: Optional[str] = None   # Gap AP: turn별 ground_truth 직접 주입
    extra: Optional[Dict[str, Any]] = None
    participant_id: Optional[str] = None  # A3: 참여자 ID 직접 주입


def _split_turn_raw(raw: Any) -> Tuple[Any, Optional[TurnMetadata]]:
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

    attempts: Optional[int] = None                             # None = 자동 계산 유지
    framework: Optional[str] = None                            # None = decorator 파라미터 유지
    expected_tools: Optional[List[str]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    agent_interactions: Optional[List[Dict[str, Any]]] = None
    chain_steps: Optional[List[Dict[str, Any]]] = None
    graph_traversal: Optional[Dict[str, Any]] = None
    state_transitions: Optional[List[Dict[str, Any]]] = None
    completion_score: Optional[float] = None
    accuracy_score: Optional[float] = None
    partial_reason: Optional[str] = None
    tokens_used: Optional[Dict[str, int]] = None               # Gap J: 비표준 LLM 토큰 주입
    model_name: Optional[str] = None                           # Gap J: 동적 모델명 주입
    context: Optional[str] = None                              # Gap P: RAG context 동적 재정의
    ground_truth: Optional[str] = None                         # Gap P: 정답 동적 재정의
    conversation_turns: Optional[List[Dict[str, Any]]] = None  # Gap AB: AutoGen turns 주입
    llm_judge: Optional[Dict[str, Any]] = None                 # Gap AC: LLM Judge 결과 주입
    extra: Optional[Dict[str, Any]] = None                     # Gap AE: 사용자 정의 메타데이터
    errors: Optional[List[str]] = None                         # Gap AN: 오류 목록 직접 주입
    execution_time: Optional[float] = None                     # Gap AO: 실행 시간 직접 주입
    _active: bool = field(default=False, repr=False)


# Python 3.7+ contextvars.ContextVar — asyncio.create_task() 등 동시 코루틴에서
# 각 태스크가 독립된 컨텍스트 복사본을 가지므로 threading.local 의 ctx 충돌이 없다.
_eval_ctx_var: contextvars.ContextVar[Optional["_EvalContext"]] = contextvars.ContextVar(
    "_eval_ctx", default=None
)

# A4: eval_context 중첩 깊이 추적 — contextvars.Token 기반으로 nested 지원
_NEST_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar("_nest_depth", default=0)
MAX_NESTING_DEPTH: int = 10  # G2: 데코레이터 중첩 경고 임계값

# 항목 F: 이중 데코레이터 스택 감지 — agent_eval wrapper 진입 여부 추적
_eval_active: contextvars.ContextVar[bool] = contextvars.ContextVar("_eval_active", default=False)


# 메서드에 적용 시 self/cls 를 question 으로 오탐하지 않도록 제외
_SKIP_PARAMS: frozenset = frozenset({"self", "cls"})


def get_eval_ctx() -> Optional[_EvalContext]:
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


def _push_ctx() -> Tuple[_EvalContext, "contextvars.Token[Optional[_EvalContext]]"]:
    """새 컨텍스트를 현재 실행 컨텍스트에 설치하고 (ctx, token) 을 반환.

    반환된 token 을 ``_pop_ctx(token)`` 에 전달해야 컨텍스트가 정확히 복원된다.
    """
    ctx = _EvalContext(_active=True)
    token = _eval_ctx_var.set(ctx)
    return ctx, token


def _pop_ctx(token: "contextvars.Token") -> None:
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


def _extract_anthropic_tokens(raw: Any) -> Optional[Dict[str, int]]:
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


def _extract_gemini_tokens(raw: Any) -> Optional[Dict[str, int]]:
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


def _extract_cohere_tokens(raw: Any) -> Optional[Dict[str, int]]:
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


def _split_raw(raw: Any) -> Tuple[Any, Optional[EvalMetadata]]:
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

def _extract_langchain_metadata(raw: Any) -> Optional[EvalMetadata]:
    """LangChain AgentExecutor 결과 dict에서 메타데이터 자동 추출.

    ``intermediate_steps`` → ``tool_calls`` + ``chain_steps`` 자동 변환.
    ``usage_metadata`` / ``response_metadata.token_usage`` 에서 토큰 사용량 추출.
    """
    if not isinstance(raw, dict) or "intermediate_steps" not in raw:
        return None
    steps = raw.get("intermediate_steps") or []
    tool_calls: List[Dict[str, Any]] = []
    chain_steps: List[Dict[str, Any]] = []
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
    tokens_used: Optional[Dict[str, int]] = None
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


def _step_time(msg: Any, idx: int, messages: List[Any]) -> float:
    """메시지 타임스탬프에서 인접 메시지 간 경과 시간(초)을 추정한다 (F1).

    LangGraph 메시지 객체에 ``response_metadata["created_at"]`` 또는
    ``additional_kwargs["created_at"]`` ISO-8601 타임스탬프가 있으면
    앞 메시지와의 차이를 반환한다. 없으면 0.0 반환.
    """
    import re as _re
    _ISO_RE = _re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")

    def _extract_ts(m: Any) -> Optional[float]:
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


def _extract_langgraph_metadata(raw: Any) -> Optional[EvalMetadata]:
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

    state_transitions: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    chain_steps: List[Dict[str, Any]] = []
    nodes_visited: List[str] = []

    # C2: __metadata__ 처리 (LangGraph checkpoint metadata)
    if isinstance(raw_metadata, dict):
        for key, val in raw_metadata.items():
            entry: Dict[str, Any] = {"node": key, "source": "__metadata__"}
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
    _tokens_used: Optional[Dict[str, Any]] = None
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


def _extract_crewai_metadata(raw: Any) -> Optional[EvalMetadata]:
    """CrewAI kickoff 결과에서 메타데이터 자동 추출.

    ``CrewOutput.tasks_output`` → ``agent_interactions`` 변환.
    CrewAI 2.0+: ``output_pydantic`` / ``output_format`` / ``pydantic`` 필드 지원 (C3, E1).
    """
    tasks_output = getattr(raw, "tasks_output", None)
    if tasks_output is None and isinstance(raw, dict):
        tasks_output = raw.get("tasks_output")

    # C3/E1: CrewAI 2.0+ — output_pydantic / pydantic (Pydantic 모델) 또는 output_format 필드 지원
    output_pydantic = getattr(raw, "output_pydantic", None) or getattr(raw, "pydantic", None)
    pydantic_result: Optional[str] = None
    if output_pydantic is not None:
        try:
            pydantic_result = output_pydantic.model_dump_json() if hasattr(output_pydantic, "model_dump_json") else str(output_pydantic)
        except Exception:
            pydantic_result = str(output_pydantic)

    # C3: output_format 필드 (CrewAI v2.x 구조화 출력)
    output_format = getattr(raw, "output_format", None)
    output_format_str: Optional[str] = None
    if output_format is not None:
        try:
            output_format_str = str(output_format)
        except Exception:
            pass

    if not tasks_output:
        fallback_interactions: List[Dict[str, Any]] = []
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

    agent_interactions: List[Dict[str, Any]] = []
    for task_out in tasks_output:
        agent_name = getattr(task_out, "agent", "unknown")
        description = getattr(task_out, "description", "")
        result_raw = getattr(task_out, "raw", None) or str(task_out)
        # C3: output_format per-task (CrewAI v2.x)
        task_format = getattr(task_out, "output_format", None)
        interaction: Dict[str, Any] = {
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
    tokens_used: Optional[Dict[str, int]] = None
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
    tool_calls: List[Dict[str, Any]] = []
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
    state_transitions: List[Dict[str, Any]] = []
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


def _extract_autogen_metadata(raw: Any) -> Optional[EvalMetadata]:
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
    # autogen-agentchat 0.4+ TaskResult
    if messages is None and hasattr(raw, "chat_result"):
        cr = raw.chat_result
        messages = getattr(cr, "chat_history", None)
    if not messages:
        return None
    conversation_turns: List[Dict[str, Any]] = []
    _prev_ts: Optional[float] = None
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
    tokens_used: Optional[Dict[str, int]] = None
    try:
        # autogen ConversableAgent: chat_result.cost["usage_including_cached_inference"]
        cost_src = getattr(raw, "cost", None) or (
            getattr(raw, "chat_result", None) and getattr(raw.chat_result, "cost", None)
        )
        if isinstance(cost_src, dict):
            usage_block = cost_src.get("usage_including_cached_inference") or {}
            # usage_block: {"gpt-4o-mini": {"prompt_tokens": N, "completion_tokens": M, ...}, "total_cost": ...}
            for key, val in usage_block.items():
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
    agent_interactions: List[Dict[str, Any]] = []
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
    state_transitions: List[Dict[str, Any]] = []
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


def _extract_dspy_metadata(raw: Any) -> Optional[EvalMetadata]:
    """DSPy Prediction 결과에서 메타데이터 자동 추출.

    C1: LM `.history` 전체를 순회해 multi-step chain_steps 추출 지원.
    """
    # DSPy Prediction 객체: _completions, rationale, answer, reasoning 등
    has_completions = hasattr(raw, "_completions") or hasattr(raw, "completions")
    has_dspy_fields = hasattr(raw, "answer") or hasattr(raw, "rationale") or hasattr(raw, "reasoning")
    if not (has_completions or has_dspy_fields):
        return None

    chain_steps: List[Dict[str, Any]] = []
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
    tokens_used: Optional[Dict[str, int]] = None
    try:
        import dspy
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
    tool_calls: List[Dict[str, Any]] = []
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
                import dspy
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


def _extract_pydanticai_metadata(raw: Any) -> Optional[EvalMetadata]:
    """PydanticAI RunResult에서 메타데이터 자동 추출.

    C1: `.all_messages()` 기반 전체 메시지 히스토리 추출 지원.
    ToolCallPart / ToolReturnPart 세분화 chain_steps 추출.
    """
    # PydanticAI RunResult: .data, .usage(), .messages, .all_messages()
    if not hasattr(raw, "usage") or not hasattr(raw, "data"):
        return None
    tokens_used: Optional[Dict[str, int]] = None
    try:
        usage = raw.usage()
        if usage:
            inp = getattr(usage, "request_tokens", 0) or getattr(usage, "input_tokens", 0) or 0
            out = getattr(usage, "response_tokens", 0) or getattr(usage, "output_tokens", 0) or 0
            if inp or out:
                tokens_used = {"input": inp, "output": out, "total": inp + out}
    except Exception:
        pass
    chain_steps: List[Dict[str, Any]] = []
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
    tool_calls: List[Dict[str, Any]] = []
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


def _extract_anthropic_metadata(raw: Any) -> Optional[EvalMetadata]:
    """Anthropic Claude Messages API 결과에서 메타데이터 자동 추출.

    ``client.messages.create(tools=[...])`` 결과의 ``content`` 블록에서
    ``tool_use`` 타입 블록을 ``tool_calls`` 로 변환하고 토큰 사용량을 추출한다.
    """
    # Anthropic Message 객체: .content (list[Block]), .usage, .model
    if not hasattr(raw, "content") or not hasattr(raw, "usage"):
        return None
    tool_calls: List[Dict[str, Any]] = []
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
    tokens_used: Optional[Dict[str, int]] = None
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


def _extract_openai_metadata(raw: Any) -> Optional[EvalMetadata]:
    """OpenAI Chat Completions API 결과에서 메타데이터 자동 추출.

    ``client.chat.completions.create(tools=[...])`` 결과의
    ``choices[0].message.tool_calls`` 에서 도구 호출을 추출하고 토큰 사용량을 수집한다.
    Assistants API ``Run`` 객체도 지원한다.
    """
    # OpenAI ChatCompletion 객체: .choices, .usage, .model
    if not hasattr(raw, "choices") and not hasattr(raw, "required_action"):
        return None
    tool_calls: List[Dict[str, Any]] = []
    tokens_used: Optional[Dict[str, int]] = None

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
        usage = getattr(raw, "usage", None)
        if usage:
            inp = getattr(usage, "prompt_tokens", 0) or 0
            out = getattr(usage, "completion_tokens", 0) or 0
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


def _extract_gemini_metadata(raw: Any) -> Optional[EvalMetadata]:
    """Google Gemini API 결과에서 메타데이터 자동 추출.

    ``model.generate_content(tools=[...])`` 결과의 ``candidates[0].content.parts``
    에서 ``function_call`` 타입 파트를 ``tool_calls`` 로 변환하고 토큰 사용량을 추출한다.
    """
    # Gemini GenerateContentResponse: .candidates, .usage_metadata
    if not hasattr(raw, "candidates") and not hasattr(raw, "usage_metadata"):
        return None
    tool_calls: List[Dict[str, Any]] = []
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
    tokens_used: Optional[Dict[str, int]] = None
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


def _extract_llamaindex_metadata(raw: Any) -> Optional[EvalMetadata]:
    """Llama Index QueryEngine / Response 결과에서 메타데이터 자동 추출.

    ``query_engine.query()`` 결과의 ``source_nodes`` 에서 검색 소스를
    ``chain_steps`` 로 변환한다.
    """
    # LlamaIndex Response: .response, .source_nodes, .metadata
    if not hasattr(raw, "source_nodes") and not hasattr(raw, "response"):
        return None
    chain_steps: List[Dict[str, Any]] = []
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
    tokens_used: Optional[Dict[str, int]] = None
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
    tool_calls: List[Dict[str, Any]] = []
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


def _extract_haystack_metadata(raw: Any) -> Optional[EvalMetadata]:
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

    chain_steps: List[Dict[str, Any]] = []
    tokens_used: Optional[Dict[str, int]] = None

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
    tool_calls: List[Dict[str, Any]] = []
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
def _extract_vertexai_metadata(raw: Any) -> Optional[EvalMetadata]:
    """Google Vertex AI SDK 응답에서 메타데이터 자동 추출 (E2).

    ``GenerateContentResponse`` 의 ``candidates[0].content.parts`` 에서
    ``function_call`` 파트와 ``usage_metadata`` 토큰을 자동 추출한다.
    ``google.cloud.aiplatform`` / ``vertexai.generative_models`` 응답 구조와 호환된다.
    """
    # VertexAI GenerateContentResponse — Gemini API 응답과 동일 구조
    tool_calls: List[Dict[str, Any]] = []
    tokens_used: Optional[Dict[str, int]] = None
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


def _extract_ollama_metadata(raw: Any) -> Optional[EvalMetadata]:
    """Ollama API 응답에서 메타데이터 자동 추출 (E3).

    ``ollama.chat()`` / ``ollama.generate()`` 응답 객체 및 ``{"message": ..., "prompt_eval_count": ...}``
    형태의 dict 응답을 지원한다.
    """
    tool_calls: List[Dict[str, Any]] = []
    tokens_used: Optional[Dict[str, int]] = None
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


def _extract_cohere_metadata(raw: Any) -> Optional[EvalMetadata]:
    """C1: Cohere SDK ``NonStreamedChatResponse`` / ``StreamedChatResponse`` / ``ChatResponse`` 메타데이터 추출.

    cohere-python v5+ 응답에서 tool_calls 와 token 사용량을 추출한다.
    C1: ``StreamedChatResponse`` 감지 시 최선 파싱 시도.
    ``pip install cohere`` 필요.
    """
    tool_calls: List[Dict[str, Any]] = []
    tokens_used: Optional[Dict[str, int]] = None

    # C1: 스트리밍 응답 감지
    cls_name = type(raw).__name__
    is_streaming = "Stream" in cls_name or (
        hasattr(raw, "text") and hasattr(raw, "finish_reason") and not hasattr(raw, "meta")
    )

    try:
        if is_streaming:
            logger.debug("Cohere streaming 응답은 실시간 집계가 필요합니다. 기본 토큰 추출만 시도.")
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
    chain_steps: List[Dict[str, Any]] = []
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


def _extract_groq_metadata(raw: Any) -> Optional[EvalMetadata]:
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


def _extract_mistral_metadata(raw: Any) -> Optional[EvalMetadata]:
    """C3: Mistral AI SDK 응답 메타데이터 추출.

    Mistral ``ChatCompletionResponse`` 에서 tool_calls 와 usage 를 추출한다.
    C3: 구버전 ``function_call`` 구조 fallback 지원.
    """
    import json as _json

    tool_calls: List[Dict[str, Any]] = []
    tokens_used: Optional[Dict[str, int]] = None
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
    tool_calls_list: List[Dict[str, Any]],
    tokens_used_ref: List[Optional[Dict[str, int]]],
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
    tool_calls_list: List[Dict[str, Any]],
    tokens_used_ref: List[Optional[Dict[str, int]]],
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


def _extract_bedrock_metadata(raw: Any) -> Optional[EvalMetadata]:
    """C4: AWS Bedrock Converse API / InvokeModel API 응답 메타데이터 추출.

    ``bedrock_runtime.converse()`` 응답 dict 에서 toolUse 와 usage 를 추출한다.
    C4: ``model_id`` 기반 자동 파서 선택 — Amazon Titan, Mistral on Bedrock 지원.
    """
    tool_calls: List[Dict[str, Any]] = []
    tokens_used: Optional[Dict[str, int]] = None
    try:
        if isinstance(raw, dict):
            # C4: model_id 기반 자동 파서 선택
            model_id = raw.get("model_id", raw.get("modelId", "")) or ""

            if "titan" in model_id.lower():
                # Amazon Titan InvokeModel API 형식
                _ref: List[Optional[Dict[str, int]]] = [None]
                _parse_titan_response(raw, tool_calls, _ref)
                tokens_used = _ref[0]
            elif "mistral" in model_id.lower() and "outputs" in raw:
                # Mistral on Bedrock InvokeModel API 형식
                _ref2: List[Optional[Dict[str, int]]] = [None]
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


def _extract_smolagents_metadata(raw: Any) -> Optional[EvalMetadata]:
    """C5: HuggingFace smolagents 응답 메타데이터 추출.

    ``agent.run()`` 결과에서 tool_calls 와 chain_steps 를 추출한다.
    C5: step에서 tool 성공/실패 여부와 입력값 추출 강화.
    """
    chain_steps: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
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
    tokens_used: Optional[Dict[str, int]] = None
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


def _extract_semantic_kernel_metadata(raw: Any) -> Optional[EvalMetadata]:
    """C6: Microsoft Semantic Kernel 응답 메타데이터 추출.

    ``kernel.invoke()`` 결과에서 function_result 및 사용 정보를 추출한다.
    C6: ``inner_content`` 의 추가 정보 추출 — OpenAI/Azure 백엔드 및 Anthropic 백엔드 지원.
    """
    chain_steps: Optional[List[Dict[str, Any]]] = None
    tokens_used: Optional[Dict[str, int]] = None
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
    tool_calls: List[Dict[str, Any]] = []
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


def _auto_detect_framework(raw: Any) -> Optional[str]:
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
) -> "Tuple[Optional[EvalMetadata], Optional[str]]":
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
        logger.debug("프레임워크 어댑터 '%s' 실패: %s", framework_name, err_msg)
        return None, err_msg


def _extract_vllm_metadata(raw: Any) -> Optional[EvalMetadata]:
    """F4: vLLM OpenAI-호환 API 응답에서 메타데이터 추출.

    vLLM은 OpenAI 호환 API를 제공하므로 choices[0].message.tool_calls + usage.total_tokens 패턴 사용.
    RequestOutput (native vLLM) 응답도 지원.
    """
    tool_calls: List[Dict[str, Any]] = []
    tokens_used: Optional[Dict[str, int]] = None
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


def _extract_huggingface_metadata(raw: Any) -> Optional[EvalMetadata]:
    """F4: HuggingFace transformers/trl pipeline 응답에서 메타데이터 추출.

    pipeline() 응답 (list of dicts), Agent (transformers.agents) 응답,
    또는 generate() dict 응답을 지원한다.
    """
    chain_steps: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    tokens_used: Optional[Dict[str, int]] = None
    try:
        # P3-A: 토큰 수 추정 헬퍼 (HuggingFace는 token count API 없는 경우 많음)
        def _estimate_tokens_from_text(text: str) -> int:
            """문자 수 기반 토큰 수 추정 (4자 ≈ 1 토큰 heuristic)."""
            return max(1, len(text) // 4)

        # transformers pipeline: [{"generated_text": "..."}] 또는 [{"label": ..., "score": ...}]
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            total_output_chars = 0
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


_FRAMEWORK_ADAPTERS: Dict[str, Optional[Callable[[Any], Optional[EvalMetadata]]]] = {
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
}


# C6: 프레임워크 어댑터 메타데이터 레지스트리
_FRAMEWORK_ADAPTER_META: Dict[str, Dict[str, Any]] = {
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
_FRAMEWORK_SUBMODULE_MAP: Dict[str, tuple] = {
    "langchain": ("langchain", "langchain.agents"),
    "crewai": ("crewai",),
    "autogen": ("autogen",),
    "dspy": ("dspy",),
    "pydanticai": ("pydantic_ai",),
    "llamaindex": ("llama_index",),
    "haystack": ("haystack",),
}

_FRAMEWORK_PACKAGE_MAP_GLOBAL: Dict[str, str] = {
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


def get_framework_info(framework: str) -> Optional[Dict[str, Any]]:
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
    _lock: "threading.Lock" = field(default_factory=threading.Lock, init=False, repr=False)
    # D3: 클래스 수준 공유 쿨다운 상태 — name → last_fired
    _class_cooldown_state: "Dict[str, float]" = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _class_cooldown_lock: "threading.Lock" = field(
        default_factory=threading.Lock, init=False, repr=False, compare=False
    )

    # D3: 클래스 수준 공유 쿨다운 저장소 (모든 인스턴스 공유)
    _CLASS_COOLDOWN: "Dict[str, float]" = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        # D3: 클래스 수준 공유 쿨다운 dict 는 클래스 변수로 관리
        if not hasattr(SimpleTaskAlertRule, "_SHARED_COOLDOWN"):
            SimpleTaskAlertRule._SHARED_COOLDOWN: Dict[str, float] = {}
            SimpleTaskAlertRule._SHARED_COOLDOWN_LOCK: "threading.Lock" = threading.Lock()
        # E2: alert history 초기화
        self._history: List[Dict[str, Any]] = []
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
            logger.debug("SimpleTaskAlertRule '%s' condition 실패 (무시): %s", self.name, e)
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
            logger.debug("SimpleTaskAlertRule '%s' handler 실패 (무시): %s", self.name, e)
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

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """최근 발동 이력 반환 (최신순)."""
        with self._history_lock:
            return list(reversed(self._history[-limit:]))

    def clear_history(self) -> None:
        """발동 이력 초기화."""
        with self._history_lock:
            self._history.clear()

    def dry_run(self, task_result: Any) -> Dict[str, Any]:
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

        msg: Optional[str] = None
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
        handler: Optional[Callable] = None,
        severity: str = "warning",
        cooldown: float = 0.0,
        name: Optional[str] = None,
    ) -> "SimpleTaskAlertRule":
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
        handler: Optional[Callable] = None,
        severity: str = "warning",
        cooldown: float = 0.0,
        name: Optional[str] = None,
    ) -> "SimpleTaskAlertRule":
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
        handler: Optional[Callable] = None,
        severity: str = "warning",
        cooldown: float = 0.0,
        name: Optional[str] = None,
    ) -> "SimpleTaskAlertRule":
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
        handler: Optional[Callable] = None,
        severity: str = "error",
        cooldown: float = 0.0,
        name: str = "task_error",
    ) -> "SimpleTaskAlertRule":
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
        handler: Optional[Callable] = None,
        severity: str = "warning",
        cooldown: float = 0.0,
        name: Optional[str] = None,
    ) -> "SimpleTaskAlertRule":
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
    alert_rules: List["SimpleTaskAlertRule"],
    existing_on_record: Optional[Callable],
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
                logger.debug("on_record 콜백 실패 (무시): %s", e)
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
    context_arg: Optional[str],
    expected_tools_arg: Optional[str],
    fallback_expected_tools: Optional[List[str]] = None,
) -> Tuple[str, str, Optional[str], Optional[List[str]]]:
    """bound arguments 에서 question / ground_truth / context / expected_tools 를 꺼낸다.

    fallback_expected_tools: 함수 인자에서 expected_tools 를 찾지 못했을 때 사용하는
        데코레이터 수준의 정적 목록 (``@agent_eval(expected_tools=[...])``)。
    """
    try:
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        all_args: Dict[str, Any] = dict(bound.arguments)
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
    eval_ctx: Optional[_EvalContext],
    eval_meta: Optional[EvalMetadata],
    score_fn: Optional[Callable],
    completion_fn: Optional[Callable],
    response: str,
    ground_truth: str,
) -> Any:
    """TaskResult 에 메타데이터를 우선순위 순으로 병합한 새 TaskResult 를 반환.

    우선순위 (높은 순):
      EvalMetadata (tuple return)  >  _EvalContext (thread-local)  >  데코레이터 파라미터  >  자동 계산
    """
    overrides: Dict[str, Any] = {}

    # --- 1단계: 데코레이터 파라미터 (가장 낮은 우선순위) ---
    if decorator_framework and decorator_framework != "native":
        overrides["framework"] = decorator_framework

    # --- 2단계: score_fn / completion_fn ---
    if score_fn is not None and response and ground_truth:
        try:
            overrides["accuracy_score"] = _clamp01(float(score_fn(response, ground_truth)))
        except Exception as e:
            logger.debug("score_fn 실패 (자동 계산 유지): %s", e)
    if completion_fn is not None and response:
        try:
            overrides["completion_score"] = _clamp01(float(completion_fn(response, ground_truth)))
        except Exception as e:
            logger.debug("completion_fn 실패 (자동 계산 유지): %s", e)

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
    monitor_or_list: "Union[PerformanceMonitor, List[PerformanceMonitor]]",
    task_result: Any,
) -> None:
    """단일 monitor 또는 monitor 리스트 모두에 task_result 를 기록한다 (Gap U)."""
    if isinstance(monitor_or_list, list):
        for m in monitor_or_list:
            try:
                m.record_task(task_result)
            except Exception as exc:
                logger.debug("_record_to_monitors: record_task 실패 (무시): %s", exc)
    else:
        monitor_or_list.record_task(task_result)


def _build_and_record(
    monitor: "Union[PerformanceMonitor, List[PerformanceMonitor]]",
    *,
    task_type: str,
    task_id: str,
    question: str,
    ground_truth: str,
    context: Optional[str],
    expected_tools_from_arg: Optional[List[str]],
    elapsed: float,
    raw: Any,
    has_error: bool,
    error_msg: Optional[str],
    model_name: str,
    framework: str,
    score_fn: Optional[Callable],
    completion_fn: Optional[Callable],
    eval_ctx: Optional[_EvalContext],
    on_record: Optional[Callable] = None,
    on_error: Optional[Callable] = None,   # Gap AK
    custom_parser: Optional[Callable[[Any], Optional[EvalMetadata]]] = None,  # A9
    auto_detect_framework: bool = False,  # C7
    extra_override: Optional[Dict[str, Any]] = None,  # A2: chunk-level extras를 TaskResult.extra에 병합
    allow_duplicate_task_ids: bool = True,  # A5: False이면 중복 task_id 감지 시 UserWarning
    enable_hallucination: bool = False,  # G4: 이 호출에서만 hallucination detection 강제 활성화
    enable_llm_judge: bool = False,        # E1: 이 호출에서만 LLM Judge 강제 활성화
    judge_model: Optional[str] = None,     # E1: LLM Judge 모델 임시 지정
    judge_criteria: Optional[List[str]] = None,  # J1: G-Eval 기준 임시 지정 (DeepEval 대체)
    security_mode: bool = False,           # E3: 이 호출에서만 security metrics 강제 활성화
    allowed_tools: Optional[List[str]] = None,  # E3: 허용된 도구 목록 임시 주입
    enable_anomaly_detection: bool = False,  # A2: 이 호출에서만 anomaly detection 임시 활성화
    enable_quality_evaluation: bool = False,  # P2-B: 이 호출에서만 품질 평가 강제 활성화
) -> Optional[Any]:
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
                    logger.debug("custom_parser 적용 완료")
            except Exception as _cp_exc:
                logger.debug("custom_parser 실패 (무시): %s", _cp_exc)

        # C7: auto_detect_framework — framework="native"/"auto"/None 이고 auto_detect_framework=True 이면
        # 응답 객체 타입/속성으로 프레임워크 자동 감지
        effective_framework = framework if framework not in (None, "auto") else "native"
        if auto_detect_framework and framework in ("native", "auto", None) and not has_error:
            _detected = _auto_detect_framework(raw_result)
            if _detected:
                effective_framework = _detected
                logger.debug("자동 감지된 프레임워크: %s", _detected)

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
                    logger.debug("프레임워크 어댑터 '%s' 자동 적용 완료", effective_framework)
                elif _adapter_err is not None:
                    logger.debug("프레임워크 어댑터 '%s' 실패: %s", effective_framework, _adapter_err)
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
                from .plugin_registry import PluginRegistry as _PR
                if _PR.list_framework_plugins():
                    _plg_fw, _plg_meta = _PR.detect_and_extract(raw_result)
                    if _plg_meta is not None:
                        eval_meta = _plg_meta
                        if effective_framework in (None, "native", "auto"):
                            effective_framework = _plg_fw
                        logger.debug("PluginRegistry 프레임워크 어댑터 '%s' 적용", _plg_fw)
            except Exception as _pr_exc:
                logger.debug("PluginRegistry 프레임워크 어댑터 실패 (무시): %s", _pr_exc)

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
        _partial_reason: Optional[str] = None
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
        _valid_cs: List[Dict[str, Any]] = []
        for _step in _cs:
            if not isinstance(_step, dict):
                logger.warning("chain_steps 항목이 dict가 아닙니다(무시): %s", type(_step).__name__)
                continue
            if "name" not in _step:
                logger.warning("chain_steps 항목에 'name' 필드 없음(무시): %s", list(_step.keys()))
                continue
            _valid_cs.append(_step)
        _cs = _valid_cs
        if _cs != task_result.chain_steps:
            task_result = dataclasses.replace(task_result, chain_steps=_cs)

        # A2: extra_override — chunk-level streaming metrics 등 caller-side extras를 TaskResult.extra에 병합
        if extra_override:
            _existing_extra: Dict[str, Any] = dict(task_result.extra) if task_result.extra else {}
            _existing_extra.update(extra_override)
            task_result = dataclasses.replace(task_result, extra=_existing_extra)

        # Phase 2: Plugin Registry — MetricPlugin 실행
        # extra_override 병합 후, 최종 extra에 plugin_metrics 추가
        try:
            from .plugin_registry import PluginRegistry as _PR2
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
                    _pm_extra: Dict[str, Any] = dict(task_result.extra) if task_result.extra else {}
                    _pm_extra["plugin_metrics"] = _plugin_scores
                    task_result = dataclasses.replace(task_result, extra=_pm_extra)
                    logger.debug("MetricPlugin 결과 적용: %s", list(_plugin_scores.keys()))
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
                            _lj_kwargs: Dict[str, Any] = {}
                            if judge_model:
                                _lj_kwargs["model"] = judge_model
                            if judge_criteria is not None:
                                _lj_kwargs["judge_criteria"] = judge_criteria
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

        # E3: security_mode — 이 호출 동안만 security metrics 임시 활성화
        _security_restored: list = []
        if security_mode:
            _monitors_e3 = monitor if isinstance(monitor, list) else [monitor]
            for _m in _monitors_e3:
                if hasattr(_m, "enable_security_metrics") and not _m.enable_security_metrics:
                    _m.enable_security_metrics = True
                    _security_restored.append(_m)
            # allowed_tools → security_config 임시 주입
            if allowed_tools:
                for _m in _monitors_e3:
                    if hasattr(_m, "security_config"):
                        _new_cfg = dict(getattr(_m, "security_config", None) or {})
                        _new_cfg["allowed_tools"] = allowed_tools
                        _m.security_config = _new_cfg

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
                logger.debug("on_record 콜백 실패 (무시): %s", cb_exc)

        # D3: on_error 는 _record_to_monitors() 이후에 호출됨 — 태스크는 이미 기록 완료
        # Gap AK: on_error 콜백 — has_error 시에만 호출
        if on_error is not None and has_error:
            try:
                on_error(task_result)
            except Exception as e:
                logger.debug("on_error 콜백 실패: %s", e)

        return task_result  # Gap AM: 호출자가 수집할 수 있도록 반환

    except Exception as exc:
        logger.debug(
            "_build_and_record 실패 (평가 생략, 원본 실행 결과는 정상): %s", exc
        )
        return None  # Gap AM


# ---------------------------------------------------------------------------
# H1: Agent eval parameter presets — 공통 파라미터 묶음
# ---------------------------------------------------------------------------

AGENT_EVAL_PRESETS: Dict[str, Dict[str, Any]] = {
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


def register_preset(name: str, config: Dict[str, Any]) -> None:
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
        _decorator_fn: "Callable",   # agent_eval 내부 decorator 함수
        _ctx_factory: "Callable",    # eval_context 생성용 팩토리 (callable)
    ) -> None:
        self._decorator_fn = _decorator_fn
        self._ctx_factory = _ctx_factory
        # context manager 모드에서 활성화되는 eval_context 인스턴스
        self._ctx_instance: "Optional[eval_context]" = None

    # ── 데코레이터 모드 ──────────────────────────────────────────────────

    def __call__(self, func: "Callable") -> "Callable":
        """데코레이터로 사용: @agent_eval(monitor, ...)"""
        return self._decorator_fn(func)

    # ── 컨텍스트 매니저 모드 ─────────────────────────────────────────────

    def __enter__(self) -> "eval_context":
        self._ctx_instance = self._ctx_factory()
        return self._ctx_instance.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if self._ctx_instance is not None:
            return self._ctx_instance.__exit__(exc_type, exc_val, exc_tb)
        return False

    async def __aenter__(self) -> "eval_context":
        self._ctx_instance = self._ctx_factory()
        return self._ctx_instance.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if self._ctx_instance is not None:
            return self._ctx_instance.__exit__(exc_type, exc_val, exc_tb)
        return False


def agent_eval(
    monitor_or_fn: "Any" = None,
    task_type: "Union[str, Any]" = "qa",
    *,
    profile: Optional[str] = None,
    question_arg: str = "question",
    ground_truth_arg: str = "ground_truth",
    task_id_prefix: str = "task",
    context_arg: Optional[str] = None,
    expected_tools_arg: Optional[str] = None,
    framework: "Union[FrameworkLiteral, str]" = "native",
    model_name: str = "",
    score_fn: Optional[Callable[[str, str], float]] = None,
    completion_fn: Optional[Callable[[str, str], float]] = None,
    task_id_fn: Optional[Callable] = None,
    task_id_arg: Optional[str] = None,    # Gap AQ
    sample_rate: float = 1.0,
    sample_condition: Optional[Callable] = None,  # Gap BA: (args, kwargs) → bool 조건부 샘플링
    on_record: Optional[Callable] = None,
    on_error: Optional[Callable] = None,  # Gap AK
    timeout: Optional[float] = None,
    enabled: bool = True,
    alert_rules: Optional[List["SimpleTaskAlertRule"]] = None,  # Task 5
    alert_error_mode: str = "log",        # 항목 S: alert_rules 예외 처리 방식 ("log"|"strict"|"ignore")
    flush_every: Optional[int] = None,    # Task 2: N건마다 save_to_file 자동 호출
    flush_filename: str = "auto_save",    # Task 2: flush 시 파일명
    # 재시도 파라미터 — max_retries > 1 이면 활성화 (기본: 1 = 재시도 없음)
    max_retries: int = 1,
    retry_on: Tuple[type, ...] = (Exception,),
    delay: float = 0.0,
    backoff: float = 1.0,
    jitter: bool = False,
    jitter_type: str = "full",
    max_delay: float = 60.0,
    should_retry: Optional[Callable[[Exception], bool]] = None,
    on_retry: Optional[Callable[[int, str], None]] = None,
    # A9: custom_parser — framework adapter보다 낮은 우선순위로 EvalMetadata 생성
    custom_parser: Optional[Callable[[Any], Optional[EvalMetadata]]] = None,
    # C7: auto_detect_framework — True 이면 응답 객체 타입으로 프레임워크 자동 감지
    # E5: 기본값 True — 명시적 framework= 지정이 없을 때 반환값 타입으로 자동 감지
    auto_detect_framework: bool = True,
    # H1: preset — 사전 정의된 파라미터 묶음 ("production" | "development" | "testing" | "canary")
    preset: Optional[str] = None,
    # A5: allow_duplicate_task_ids — False이면 중복 task_id 시 UserWarning
    allow_duplicate_task_ids: bool = True,
    # G4: 이 데코레이터에서만 hallucination detection 활성화 (monitor 전역 설정 우선)
    enable_hallucination: bool = False,
    # E2: RAG 단축 — context_arg + hallucination + task_type 자동 설정
    rag_mode: bool = False,
    # E3: 보안 단축 — enable_security_metrics 임시 활성화
    security_mode: bool = False,
    allowed_tools: Optional[List[str]] = None,
    # E1: PerformanceMonitor 고급 기능 직접 노출 (모니터 전역 설정 우선)
    enable_llm_judge: bool = False,
    judge_model: Optional[str] = None,
    # J1: G-Eval 스타일 커스텀 평가 기준 (DeepEval 대체)
    # 예: judge_criteria=["medical_accuracy", "citation_quality"]
    # rag_mode=True와 함께 사용 시 faithfulness 차원 자동 추가 (Ragas 대체)
    judge_criteria: Optional[List[str]] = None,
    enable_anomaly_detection: bool = False,
    # P2-B: 이 데코레이터에서만 품질 평가 강제 활성화
    enable_quality_evaluation: bool = False,
    # D5: dry_run — True이면 설정 검증만 하고 실제 평가 기록 안 함
    dry_run: bool = False,
    # ── 컨텍스트 매니저 모드 전용 (with agent_eval(...) as ctx:) ──────────
    question: str = "",
    ground_truth: str = "",
    context: Optional[str] = None,
    expected_tools: Optional[List[str]] = None,
    task_id: Optional[str] = None,
    task_id_prefix_cm: str = "eval",
    auto_task_id: bool = False,
    ttft_seconds: Optional[float] = None,
) -> "Any":
    """동기·비동기 에이전트 함수에 평가를 자동 적용하는 데코레이터 (sync/async 자동 감지).

    **Quick Start — 90% 사용 사례를 커버하는 핵심 5개 파라미터**::

        @agent_eval(
            monitor,                      # 1. PerformanceMonitor 인스턴스 (필수)
            task_type="qa",               # 2. 태스크 유형
            framework="langchain",        # 3. 프레임워크 식별자 (대시보드 분류)
            model_name="gpt-4o-mini",     # 4. LLM 모델명 (Phoenix 차트)
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
        from .eval_config import get_active_config as _get_cfg, get_or_create_monitor as _get_mon
        _cfg = _get_cfg(profile=profile)
        monitor = _get_mon(profile=profile, config=_cfg)
        # Apply config values conservatively: only when param is still at its SDK default
        if task_type == "qa":
            task_type = _cfg.task_type
        if framework == "native":
            framework = _cfg.framework
        if model_name == "":
            model_name = _cfg.model_name
        if sample_rate == 1.0:
            sample_rate = _cfg.sample_rate
        if not rag_mode:
            rag_mode = _cfg.rag_mode
        if not enable_hallucination:
            enable_hallucination = _cfg.enable_hallucination
        if not security_mode:
            security_mode = _cfg.security_mode
        if not enable_llm_judge:
            enable_llm_judge = _cfg.judge.enabled
        if judge_model is None:
            judge_model = _cfg.judge.model
        if judge_criteria is None:
            judge_criteria = _cfg.judge.criteria
        if not enable_anomaly_detection:
            enable_anomaly_detection = _cfg.enable_anomaly_detection or _cfg.anomaly.enabled
        if not enable_quality_evaluation:
            enable_quality_evaluation = _cfg.enable_quality_evaluation
        if flush_every is None:
            flush_every = _cfg.flush_every
        if flush_filename == "auto_save":
            flush_filename = _cfg.flush_filename
        if max_retries == 1:
            max_retries = _cfg.max_retries
        if not dry_run:
            dry_run = _cfg.dry_run
    else:
        monitor = monitor_or_fn
    # ── End Phase 1 ─────────────────────────────────────────────────────────

    # 항목 D: rag_mode + security_mode 동시 사용 경고
    if rag_mode and security_mode:
        import warnings as _warnings_d
        _warnings_d.warn(
            "agent_eval: rag_mode=True와 security_mode=True를 동시에 지정했습니다. "
            "task_type은 'information_retrieval'로 설정됩니다. "
            "보안 메트릭은 정상 적용됩니다.",
            UserWarning,
            stacklevel=2,
        )

    # E2: rag_mode — context_arg + hallucination + task_type 자동 설정
    if rag_mode:
        if context_arg is None:
            context_arg = "context"
        enable_hallucination = True
        if task_type == "qa":
            task_type = "information_retrieval"

    # H1: preset — 사전 정의된 파라미터 묶음 적용 (명시적 파라미터가 preset보다 우선)
    # NOTE: Python에서 기본값과 명시적 지정을 구분하기 어려우므로
    # preset은 전역 변수를 nonlocal로 수정하는 대신 내부 변수로 처리
    _preset_vals: Dict[str, Any] = {}
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
    # preset 값 적용 (기본값인 경우에만)
    _effective_sample_rate = sample_rate if sample_rate != 1.0 else _preset_vals.get("sample_rate", sample_rate)
    _effective_timeout = timeout if timeout is not None else _preset_vals.get("timeout", timeout)
    _effective_flush_every = flush_every if flush_every is not None else _preset_vals.get("flush_every", flush_every)
    _effective_enabled = enabled if not enabled else _preset_vals.get("enabled", enabled)
    _effective_allow_dup = allow_duplicate_task_ids if not allow_duplicate_task_ids else _preset_vals.get("allow_duplicate_task_ids", allow_duplicate_task_ids)
    # E1/E5: preset에서 enable_llm_judge / enable_anomaly_detection 적용 (기본값인 경우에만)
    _effective_enable_llm_judge = enable_llm_judge or _preset_vals.get("enable_llm_judge", False)
    _effective_judge_model = judge_model or _preset_vals.get("judge_model", None)
    _effective_enable_anomaly = enable_anomaly_detection or _preset_vals.get("enable_anomaly_detection", False)

    # 재시도 횟수 정규화 (0 이하는 1회 시도로 처리)
    _n_tries = max(1, max_retries)

    # 데코레이터 수준의 static expected_tools 를 closure 변수로 캡처한다.
    # wrapper 내부에서 _resolve_args() 결과를 'expected_tools' 이름으로 재바인딩하면
    # Python 이 wrapper 스코프 전체에서 'expected_tools' 를 로컬로 간주해
    # UnboundLocalError 가 발생하므로, 다른 이름의 closure 변수를 사용한다.
    _static_expected_tools: Optional[List[str]] = expected_tools

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
        _flush_counter: List[int] = [0]
        _flush_lock = threading.Lock()

        def _maybe_flush(task_result: Any) -> None:
            if flush_every is None or flush_every <= 0:
                return
            with _flush_lock:
                _flush_counter[0] += 1
                if _flush_counter[0] % flush_every == 0:
                    try:
                        _mon = monitor if not isinstance(monitor, list) else monitor[0]
                        _mon.save_to_file(flush_filename)
                        logger.debug("flush_every=%d 조건 충족 — '%s' 저장", flush_every, flush_filename)
                    except Exception as _fe:
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
            # Gap BA: sample_condition — False 반환 시 평가 생략
            if sample_condition is not None:
                try:
                    if not sample_condition(args, kwargs):
                        return func(*args, **kwargs)
                except Exception:
                    pass

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

            question, ground_truth, context, expected_tools = _resolve_args(
                sig, args, kwargs,
                question_arg, ground_truth_arg, context_arg, expected_tools_arg,
                fallback_expected_tools=_static_expected_tools,
            )
            # Gap AQ: task_id_arg > task_id_fn > auto
            task_id: Optional[str] = None
            if task_id_arg:
                try:
                    _bound = sig.bind(*args, **kwargs)
                    _bound.apply_defaults()
                    _tid = _bound.arguments.get(task_id_arg)
                    if _tid:
                        task_id = str(_tid)
                except Exception:
                    pass
            if task_id is None:
                task_id = (
                    task_id_fn(args, kwargs)
                    if task_id_fn is not None
                    else f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
                )

            start = time.perf_counter()
            has_error = False
            error_msg: Optional[str] = None
            raw: Any = None          # 함수 반환값 전체 (EvalMetadata 포함 가능)
            caller_result: Any = None  # 호출자에게 반환할 값 (EvalMetadata 제거)
            eval_ctx, _ctx_token = _push_ctx()
            _attempt = 0
            _errors: List[str] = []
            _wait = delay

            try:
                while _attempt < _n_tries:
                    _attempt += 1
                    try:
                        if timeout is not None:
                            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
                                try:
                                    raw = _ex.submit(func, *args, **kwargs).result(timeout=timeout)
                                except concurrent.futures.TimeoutError:
                                    raise TimeoutError(f"exceeded {timeout}s")
                        else:
                            raw = func(*args, **kwargs)
                        break  # 성공 — retry 루프 탈출
                    except Exception as _exc:
                        # 재시도 없는 경우 또는 retry_on에 해당하지 않으면 즉시 전파
                        if _n_tries == 1 or not isinstance(_exc, retry_on):
                            has_error = True
                            error_msg = str(_exc)
                            raise
                        _errors.append(str(_exc))
                        # should_retry 콜백 — False 반환 시 즉시 중단
                        if should_retry is not None:
                            try:
                                if not should_retry(_exc):
                                    has_error = True
                                    error_msg = str(_exc)
                                    raise
                            except Exception as _sre:
                                if not isinstance(_sre, retry_on):
                                    pass
                        if on_retry is not None:
                            try:
                                on_retry(_attempt, str(_exc))
                            except Exception:
                                pass
                        if _attempt >= _n_tries:
                            has_error = True
                            error_msg = _errors[-1]
                            raise
                        # 지수 백오프 + jitter
                        if _wait > 0 or jitter_type in ("full", "decorrelated"):
                            _base = delay * (backoff ** (_attempt - 1))
                            if jitter_type == "decorrelated":
                                _actual = min(max_delay, random.uniform(delay, max(delay, _wait * 3)))
                            elif jitter_type == "none":
                                _actual = _wait
                            else:  # "full" 또는 legacy jitter=True
                                _actual = random.uniform(0.0, _base) if (jitter_type == "full" or jitter) else _wait
                            if _actual > 0:
                                time.sleep(_actual)
                        _wait = _wait * backoff
                caller_result, _ = _split_raw(raw)  # EvalMetadata 분리
                return caller_result
            except Exception:
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)
                _eval_active.reset(_eval_active_token)  # 항목 F: 이중 감지 토큰 복원
                # 재시도 데이터를 eval_ctx에 주입 (attempts, errors)
                if eval_ctx is not None and _n_tries > 1:
                    eval_ctx.attempts = _attempt
                    if _errors:
                        eval_ctx.errors = _errors
                if dry_run:
                    logger.debug("dry_run=True: 실제 평가 기록 건너뜀 (task_id=%s)", task_id)
                else:
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
                        custom_parser=custom_parser,  # A9
                        auto_detect_framework=auto_detect_framework,  # C7
                        enable_hallucination=enable_hallucination,  # G4
                        enable_llm_judge=_effective_enable_llm_judge,  # E1
                        judge_model=_effective_judge_model,           # E1
                        judge_criteria=judge_criteria,                # J1
                        security_mode=security_mode,                  # E3
                        allowed_tools=allowed_tools,                  # E3
                        enable_anomaly_detection=_effective_enable_anomaly,  # A2
                        enable_quality_evaluation=enable_quality_evaluation,  # P2-B
                    )

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return await func(*args, **kwargs)
            # Gap BA: sample_condition — False 반환 시 평가 생략
            if sample_condition is not None:
                try:
                    if not sample_condition(args, kwargs):
                        return await func(*args, **kwargs)
                except Exception:
                    pass

            question, ground_truth, context, expected_tools = _resolve_args(
                sig, args, kwargs,
                question_arg, ground_truth_arg, context_arg, expected_tools_arg,
                fallback_expected_tools=_static_expected_tools,
            )
            # Gap AQ: task_id_arg > task_id_fn > auto
            task_id: Optional[str] = None
            if task_id_arg:
                try:
                    _bound = sig.bind(*args, **kwargs)
                    _bound.apply_defaults()
                    _tid = _bound.arguments.get(task_id_arg)
                    if _tid:
                        task_id = str(_tid)
                except Exception:
                    pass
            if task_id is None:
                task_id = (
                    task_id_fn(args, kwargs)
                    if task_id_fn is not None
                    else f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
                )

            start = time.perf_counter()
            has_error = False
            error_msg: Optional[str] = None
            raw: Any = None
            eval_ctx, _ctx_token = _push_ctx()
            _attempt = 0
            _errors: List[str] = []
            _wait = delay

            try:
                while _attempt < _n_tries:
                    _attempt += 1
                    try:
                        if timeout is not None:
                            raw = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                        else:
                            raw = await func(*args, **kwargs)
                        break  # 성공
                    except Exception as _exc:
                        if _n_tries == 1 or not isinstance(_exc, retry_on):
                            has_error = True
                            error_msg = str(_exc)
                            raise
                        _errors.append(str(_exc))
                        if should_retry is not None:
                            try:
                                if not should_retry(_exc):
                                    has_error = True
                                    error_msg = str(_exc)
                                    raise
                            except Exception as _sre:
                                if not isinstance(_sre, retry_on):
                                    pass
                        if on_retry is not None:
                            try:
                                on_retry(_attempt, str(_exc))
                            except Exception:
                                pass
                        if _attempt >= _n_tries:
                            has_error = True
                            error_msg = _errors[-1]
                            raise
                        if _wait > 0 or jitter_type in ("full", "decorrelated"):
                            _base = delay * (backoff ** (_attempt - 1))
                            if jitter_type == "decorrelated":
                                _actual = min(max_delay, random.uniform(delay, max(delay, _wait * 3)))
                            elif jitter_type == "none":
                                _actual = _wait
                            else:
                                _actual = random.uniform(0.0, _base) if (jitter_type == "full" or jitter) else _wait
                            if _actual > 0:
                                await asyncio.sleep(_actual)
                        _wait = _wait * backoff
                caller_result, _ = _split_raw(raw)
                return caller_result
            except Exception:
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)
                if eval_ctx is not None and _n_tries > 1:
                    eval_ctx.attempts = _attempt
                    if _errors:
                        eval_ctx.errors = _errors
                if dry_run:
                    logger.debug("dry_run=True: 실제 평가 기록 건너뜀 (task_id=%s)", task_id)
                else:
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
                        custom_parser=custom_parser,  # A9
                        auto_detect_framework=auto_detect_framework,  # C7
                        enable_hallucination=enable_hallucination,  # G4
                        enable_llm_judge=_effective_enable_llm_judge,  # E1
                        judge_model=_effective_judge_model,           # E1
                        judge_criteria=judge_criteria,                # J1
                        security_mode=security_mode,                  # E3
                        allowed_tools=allowed_tools,                  # E3
                        enable_anomaly_detection=_effective_enable_anomaly,  # A2
                        enable_quality_evaluation=enable_quality_evaluation,  # P2-B
                    )

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
            # Gap AQ: task_id_arg > task_id_fn > auto
            task_id: Optional[str] = None
            if task_id_arg:
                try:
                    _bound = sig.bind(*args, **kwargs)
                    _bound.apply_defaults()
                    _tid = _bound.arguments.get(task_id_arg)
                    if _tid:
                        task_id = str(_tid)
                except Exception:
                    pass
            if task_id is None:
                task_id = (
                    task_id_fn(args, kwargs)
                    if task_id_fn is not None
                    else f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
                )
            start = time.perf_counter()
            has_error = False
            error_msg: Optional[str] = None
            chunks: List[str] = []
            eval_meta_from_gen: Optional[EvalMetadata] = None  # Gap AV
            _first_yield_time: Optional[float] = None           # D6: 첫 청크 시간
            eval_ctx, _ctx_token = _push_ctx()

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
                raw_str = "".join(chunks)
                # Gap AV: pass EvalMetadata from generator as (raw, eval_meta) tuple
                raw_to_record = (raw_str, eval_meta_from_gen) if eval_meta_from_gen else raw_str
                if dry_run:
                    logger.debug("dry_run=True: 실제 평가 기록 건너뜀 (task_id=%s)", task_id)
                else:
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
                        custom_parser=custom_parser,  # A9
                        auto_detect_framework=auto_detect_framework,  # C7
                        enable_hallucination=enable_hallucination,  # G4
                        enable_llm_judge=_effective_enable_llm_judge,  # E1
                        judge_model=_effective_judge_model,           # E1
                        judge_criteria=judge_criteria,                # J1
                        security_mode=security_mode,                  # E3
                        allowed_tools=allowed_tools,                  # E3
                        enable_anomaly_detection=_effective_enable_anomaly,  # A2
                        enable_quality_evaluation=enable_quality_evaluation,  # P2-B
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
            # Gap AQ: task_id_arg > task_id_fn > auto
            task_id: Optional[str] = None
            if task_id_arg:
                try:
                    _bound = sig.bind(*args, **kwargs)
                    _bound.apply_defaults()
                    _tid = _bound.arguments.get(task_id_arg)
                    if _tid:
                        task_id = str(_tid)
                except Exception:
                    pass
            if task_id is None:
                task_id = (
                    task_id_fn(args, kwargs)
                    if task_id_fn is not None
                    else f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
                )
            start = time.perf_counter()
            has_error = False
            error_msg: Optional[str] = None
            chunks: List[str] = []
            eval_meta_from_gen: Optional[EvalMetadata] = None  # Gap AV
            _first_yield_time: Optional[float] = None           # D6: 첫 청크 시간
            eval_ctx, _ctx_token = _push_ctx()

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
                raw_str = "".join(chunks)
                # Gap AV: pass EvalMetadata from generator as (raw, eval_meta) tuple
                raw_to_record = (raw_str, eval_meta_from_gen) if eval_meta_from_gen else raw_str
                if dry_run:
                    logger.debug("dry_run=True: 실제 평가 기록 건너뜀 (task_id=%s)", task_id)
                else:
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
                        custom_parser=custom_parser,  # A9
                        auto_detect_framework=auto_detect_framework,  # C7
                        enable_hallucination=enable_hallucination,  # G4
                        enable_llm_judge=_effective_enable_llm_judge,  # E1
                        judge_model=_effective_judge_model,           # E1
                        judge_criteria=judge_criteria,                # J1
                        security_mode=security_mode,                  # E3
                        allowed_tools=allowed_tools,                  # E3
                        enable_anomaly_detection=_effective_enable_anomaly,  # A2
                        enable_quality_evaluation=enable_quality_evaluation,  # P2-B
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

        if inspect.isasyncgenfunction(func):
            return agen_wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        if inspect.isgeneratorfunction(func):
            return gen_wrapper
        return wrapper

    def _ctx_factory() -> "eval_context":
        return eval_context(
            monitor,
            task_type,
            question=question,
            ground_truth=ground_truth,
            context=context,
            expected_tools=expected_tools,
            framework=framework,
            model_name=model_name,
            task_id=task_id,
            task_id_prefix=task_id_prefix_cm,
            auto_task_id=auto_task_id,
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
_CONV_SESSIONS: Dict[str, Dict[str, Any]] = {}
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


def _do_flush(entry: Dict[str, Any]) -> None:
    """실제 flush 로직 — with monitor.conversation() 컨텍스트 매니저 활용."""
    # Gap AY: 타이머 취소
    timer = entry.get("_timer")
    if timer is not None:
        timer.cancel()

    session_id: str = entry["session_id"]
    turns: List[Dict[str, Any]] = entry["turns"]   # [{user, agent, metadata}]
    stored_monitor = entry["monitor"]

    if not turns:
        logger.debug("flush_conversation: 세션 '%s' 턴 없음 — skip", session_id)
        return

    on_flush_cb: Optional[Callable] = entry.get("on_flush")
    session_score_fn_cb: Optional[Callable] = entry.get("session_score_fn")  # Gap T
    on_record_cb: Optional[Callable] = entry.get("on_record")  # C: on_record 콜백

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
                logger.debug("conversation_eval on_record 콜백 실패 (무시): %s", _orec_exc)
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


def conversation_eval(
    monitor: "PerformanceMonitor",
    *,
    session_id_arg: str = "session_id",
    user_arg: str = "question",
    question_arg: Optional[str] = None,  # A2: user_arg의 alias — 지정 시 user_arg 대신 사용
    ground_truth_arg: str = "ground_truth",
    max_turns: Optional[int] = None,
    flush_on_error: bool = True,
    sample_rate: float = 1.0,
    on_flush: Optional[Callable] = None,              # Gap M: (metrics, session_id: str) → None
    on_turn: Optional[Callable] = None,               # Gap Z: (session_id, user, response, metadata) → None
    on_record: Optional[Callable[["TaskResult"], Optional["TaskResult"]]] = None,  # C: (TaskResult) → Optional[TaskResult]
    session_score_fn: Optional[Callable] = None,      # Gap T: (ConversationMetrics) → float
    turn_score_fn: Optional[Callable] = None,         # Gap AX: (user, response, metadata) → float
    max_session_seconds: Optional[float] = None,      # Gap AY: 비활성 세션 자동 flush 타이머
    on_session_timeout: Optional[Callable] = None,    # Gap J: (session_id: str) → None — 타임아웃 시 호출
    alert_rules: Optional[List[Any]] = None,          # SimpleTaskAlertRule 리스트 — 세션 flush 후 발동
    flush_every: int = 0,                             # A3: N 세션마다 save_to_file() 자동 실행
    flush_filename: str = "conv_eval_auto",           # A3: flush_every 저장 파일명
    participant_id_arg: Optional[str] = None,         # A3: participant_id 파라미터 이름 — turn metadata에 저장
    max_turns_exceeded_action: str = "flush",         # A10: "flush" | "warn" | "error"
    load_previous_session: bool = False,              # A7: True이면 flush_filename 파일에서 이전 세션 로드
    enabled: bool = True,
    # A1: preset — AGENT_EVAL_PRESETS 키로 공통 파라미터 적용
    preset: Optional[str] = None,
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
    # A1: preset — conversation_eval도 동일한 preset 시스템 지원
    if preset is not None:
        if preset in AGENT_EVAL_PRESETS:
            _cp = AGENT_EVAL_PRESETS[preset]
            sample_rate = sample_rate if sample_rate != 1.0 else _cp.get("sample_rate", sample_rate)
            flush_every = flush_every if flush_every else _cp.get("flush_every", flush_every)
            enabled = enabled if not enabled else _cp.get("enabled", enabled)
        else:
            import warnings as _w
            _w.warn(
                f"conversation_eval: 알 수 없는 preset '{preset}'. 사용 가능: {list(AGENT_EVAL_PRESETS.keys())}",
                UserWarning, stacklevel=2,
            )

    def decorator(func: Callable) -> Callable:
        if not enabled:
            return func

        is_async = asyncio.iscoroutinefunction(func)
        sig = inspect.signature(func)

        # A3: flush_every 카운터 (session flush 단위)
        _conv_flush_counter: List[int] = [0]
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
                    _mon.save_to_file(flush_filename)
                except Exception as _fe:
                    logger.debug("conversation_eval flush_every 저장 실패 (무시): %s", _fe)

        def _load_previous_session_turns(session_id: str) -> List[Dict[str, Any]]:
            """A7: flush_filename 파일에서 이전 세션 턴을 로드."""
            if not load_previous_session:
                return []
            try:
                _out_dir = getattr(monitor, "output_dir", None) or "results"
                _fpath = str(_out_dir).rstrip("/") + f"/{flush_filename}.json"
                import os, json as _json
                if not os.path.exists(_fpath):
                    logger.warning("load_previous_session: 파일을 찾을 수 없음: %s", _fpath)
                    return []
                with open(_fpath, "r", encoding="utf-8") as _f:
                    _data = _json.load(_f)
                # Look for session data in conversation_sessions key
                _sessions = _data.get("conversation_sessions", [])
                for _sess in _sessions:
                    if _sess.get("session_id") == session_id:
                        _turns = _sess.get("turns", [])
                        logger.debug("load_previous_session: '%s' 세션에서 %d턴 로드", session_id, len(_turns))
                        return _turns
            except Exception as _lpe:
                logger.warning("load_previous_session 실패 (무시): %s", _lpe)
            return []

        def _get_or_create_session(session_id: str) -> Dict[str, Any]:
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
                    }
                return _CONV_SESSIONS[session_id]

        def _add_turn(
            session_id: str,
            user: str,
            agent_resp: str,
            metadata: Dict[str, Any],
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
            effective_user_arg = question_arg or user_arg  # A2: question_arg가 지정되면 우선 사용
            user_msg = all_args.get(effective_user_arg)
            if user_msg is None:
                param_names = list(sig.parameters.keys())
                user_msg = all_args.get(param_names[0], "") if param_names else ""
            # Gap AD: ground_truth 실제 추출 (기존 "현재 미사용" → 턴 metadata에 저장)
            ground_truth_val = str(all_args.get(ground_truth_arg) or "")
            # A3: participant_id 추출
            participant_id_val: Optional[str] = None
            if participant_id_arg:
                _pid = all_args.get(participant_id_arg)
                if _pid is not None:
                    participant_id_val = str(_pid)
            return str(session_id), str(user_msg), ground_truth_val, participant_id_val

        def _build_turn_metadata(
            elapsed: float,
            turn_meta: Optional[TurnMetadata],
            participant_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            """elapsed(자동 측정)과 TurnMetadata 를 합쳐 metadata dict 를 생성."""
            latency = (
                turn_meta.latency if (turn_meta and turn_meta.latency is not None) else elapsed
            )
            meta: Dict[str, Any] = {"latency": latency}
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

        def _reset_timer(session_id: str, entry: Dict[str, Any]) -> None:
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
                        # A10: max_turns_exceeded_action 분기
                        if max_turns_exceeded_action == "error":
                            raise ValueError(
                                f"conversation_eval: max_turns={max_turns} 초과"
                            )
                        elif max_turns_exceeded_action == "warn":
                            logger.warning(
                                "conversation_eval: max_turns=%d 초과, 자동 flush", max_turns
                            )
                        flush_conversation(session_id)
                        _maybe_flush_conv()  # A3

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
                        # A10: max_turns_exceeded_action 분기
                        if max_turns_exceeded_action == "error":
                            raise ValueError(
                                f"conversation_eval: max_turns={max_turns} 초과"
                            )
                        elif max_turns_exceeded_action == "warn":
                            logger.warning(
                                "conversation_eval: max_turns=%d 초과, 자동 flush", max_turns
                            )
                        flush_conversation(session_id)
                        _maybe_flush_conv()  # A3

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
            chunks: List[str] = []
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
                    metadata: Dict[str, Any] = {"latency": elapsed}
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
                        # A10: max_turns_exceeded_action 분기
                        if max_turns_exceeded_action == "error":
                            raise ValueError(
                                f"conversation_eval: max_turns={max_turns} 초과"
                            )
                        elif max_turns_exceeded_action == "warn":
                            logger.warning(
                                "conversation_eval: max_turns=%d 초과, 자동 flush", max_turns
                            )
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
    monitor: "Union[PerformanceMonitor, List[PerformanceMonitor]]",
    task_type: str = "qa",
    *,
    questions_arg: str = "questions",
    ground_truths_arg: str = "ground_truths",
    contexts_arg: Optional[str] = None,         # Gap Q: RAG context 리스트 파라미터 이름
    expected_tools_arg: Optional[str] = None,   # Gap W: expected_tools 리스트(List[List[str]]) 파라미터 이름
    task_id_prefix: str = "batch",
    task_id_fn: Optional[Callable] = None,      # Gap V: (index, question, ground_truth) -> str
    framework: str = "native",
    model_name: str = "",
    score_fn: Optional[Callable] = None,
    completion_fn: Optional[Callable] = None,
    on_record: Optional[Callable] = None,
    on_error: Optional[Callable] = None,        # (task_result: TaskResult) → None — 오류 항목 기록 후 호출
    on_batch_complete: Optional[Callable] = None,  # Gap AM: (results: List[TaskResult]) → None
    on_batch_progress: Optional[Callable] = None,  # Gap I: (completed: int, total: int) → None
    alert_rules: Optional[List[Any]] = None,    # SimpleTaskAlertRule 리스트 — 항목별 평가 후 자동 발동
    flush_every: int = 0,                       # N 배치 호출마다 monitor.save_to_file() 자동 실행
    flush_filename: str = "batch_eval_auto",    # flush_every 저장 파일명
    sample_rate: float = 1.0,
    sample_condition: Optional[Callable] = None,  # Gap BA: (args, kwargs) → bool 조건부 샘플링
    timeout: Optional[float] = None,            # Gap X: 배치 전체 함수 실행 제한 시간(초)
    enabled: bool = True,
    concurrent: bool = False,                   # async 함수를 항목별로 병렬 실행 (asyncio.gather)
    max_concurrent: int = 0,                    # 동시 실행 상한 (0 = 무제한); concurrent=True 일 때만 사용
    shuffle: bool = False,                      # B3: 배치 평가 전 항목 순서 섞기
    shuffle_seed: Optional[int] = None,         # B3: 재현 가능한 셔플 시드
    on_item_error: Optional[Callable] = None,   # A1: concurrent 실행 시 개별 아이템 실패 콜백
                                                #     시그니처: (index: int, question: str, error: Exception) -> None
    strict_types: bool = False,                 # A2: True이면 questions가 List[str]인지 타입 검사
    item_timeout: Optional[float] = None,       # A1: 개별 아이템 실행 제한 시간(초)
    return_format: str = "list",                # A8: 반환 형식 — "list" | "tuple" | "dataframe"
                                                #     "list": 응답 리스트 (기본)
                                                #     "tuple": (responses, task_results) 튜플
                                                #     "dataframe": pandas DataFrame
    streaming_mode: bool = False,               # G1: True이면 응답을 generator로 yield (메모리 효율)
    # A1: preset — AGENT_EVAL_PRESETS 키로 공통 파라미터 묶음 적용 (agent_eval과 동일)
    preset: Optional[str] = None,
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
    # A1: preset — batch_eval도 agent_eval과 동일한 preset 시스템 지원
    if preset is not None:
        if preset in AGENT_EVAL_PRESETS:
            _bp = AGENT_EVAL_PRESETS[preset]
            # 기본값인 경우에만 preset 값으로 덮어씀
            sample_rate = sample_rate if sample_rate != 1.0 else _bp.get("sample_rate", sample_rate)
            timeout = timeout if timeout is not None else _bp.get("timeout", timeout)
            flush_every = flush_every if flush_every else _bp.get("flush_every", flush_every)
            enabled = enabled if not enabled else _bp.get("enabled", enabled)
        else:
            import warnings as _w
            _w.warn(
                f"batch_eval: 알 수 없는 preset '{preset}'. 사용 가능: {list(AGENT_EVAL_PRESETS.keys())}",
                UserWarning, stacklevel=2,
            )

    def decorator(func: Callable) -> Callable:
        if not enabled:
            return func

        is_async = asyncio.iscoroutinefunction(func)
        sig = inspect.signature(func)

        # alert_rules → per-item on_record 통합
        _effective_on_record = on_record
        if alert_rules:
            _effective_on_record = _make_alert_on_record(alert_rules, on_record)

        # A8: return_format — mutable holder shared between wrapper and wrapper_with_format
        _last_batch_results_holder: List[List[Any]] = [[]]

        # flush_every 카운터 (thread-safe)
        _flush_counter: List[int] = [0]
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
                    _mon.save_to_file(flush_filename)
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

            questions: List[str] = all_args.get(questions_arg)
            if questions is None:
                param_names = list(sig.parameters.keys())
                questions = all_args.get(param_names[0], []) if param_names else []
            # A2: strict_types — questions 가 List[str] 인지 타입 검사
            if strict_types:
                if not isinstance(questions, list) or not all(isinstance(q, str) for q in questions):
                    raise TypeError(
                        f"questions must be List[str], got {type(questions).__name__}"
                    )
            if not isinstance(questions, list):
                questions = list(questions)

            ground_truths: List[str] = all_args.get(ground_truths_arg) or []
            if not isinstance(ground_truths, list):
                ground_truths = list(ground_truths)

            # Gap Q: contexts 리스트 추출 (List[str])
            contexts: Optional[List[str]] = None
            if contexts_arg:
                raw_ctx = all_args.get(contexts_arg)
                if raw_ctx is not None:
                    contexts = [str(c) for c in (raw_ctx if isinstance(raw_ctx, list) else list(raw_ctx))]

            # Gap W: expected_tools_list 추출 (List[List[str]])
            expected_tools_list: Optional[List[Optional[List[str]]]] = None
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
            questions: List[str],
            ground_truths: List[str],
            responses: Any,
            elapsed: float,
            has_error: bool,
            error_msg: Optional[str],
            batch_uuid: str,
            eval_ctx: Optional[_EvalContext] = None,                           # Gap L
            contexts: Optional[List[str]] = None,                              # Gap Q
            expected_tools_list: Optional[List[Optional[List[str]]]] = None,  # Gap W
        ) -> List[Any]:  # A8: returns list of TaskResult objects
            if not isinstance(responses, list):
                responses = [responses] if responses is not None else []

            # B3: shuffle 항목 순서 — questions/ground_truths/contexts/expected_tools 동기화
            if shuffle:
                _rng = random.Random(shuffle_seed)
                _indices = list(range(len(questions)))
                _rng.shuffle(_indices)
                questions = [questions[j] for j in _indices]
                ground_truths = [ground_truths[j] if j < len(ground_truths) else "" for j in _indices]
                if responses:
                    responses = [responses[j] if j < len(responses) else "" for j in _indices]
                if contexts:
                    contexts = [contexts[j] if j < len(contexts) else None for j in _indices]
                if expected_tools_list:
                    expected_tools_list = [expected_tools_list[j] if j < len(expected_tools_list) else None for j in _indices]

            n = max(len(questions), 1)
            per_item_time = elapsed / n

            # Gap AM: collect results for on_batch_complete
            batch_results: List[Any] = []

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
            # Gap BA: sample_condition — False 반환 시 평가 생략
            if sample_condition is not None:
                try:
                    if not sample_condition(args, kwargs):
                        return func(*args, **kwargs)
                except Exception:
                    pass

            questions, ground_truths, contexts, expected_tools_list = _resolve_batch_args(*args, **kwargs)
            batch_uuid = uuid.uuid4().hex[:8]
            start = time.perf_counter()
            has_error = False
            error_msg: Optional[str] = None
            responses: Any = None
            eval_ctx, _ctx_token = _push_ctx()  # Gap L

            # A1: _item_failures 리스트 초기화 (concurrent 실행 시 개별 실패 추적)
            _item_failures: List[Dict[str, Any]] = []

            try:
                # A1: sync concurrent — 항목별 ThreadPoolExecutor 병렬 실행
                # NOTE: 'concurrent' param shadows the module; use _futures_mod alias
                if concurrent and not is_async and len(questions) > 0:
                    import concurrent.futures as _futures_mod
                    _max_w = max_concurrent if max_concurrent > 0 else len(questions)

                    def _call_one_sync(i: int) -> Any:
                        _kw = dict(kwargs)
                        _kw[questions_arg] = [questions[i]]
                        _kw[ground_truths_arg] = [ground_truths[i]] if i < len(ground_truths) else []
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
                wrapper._last_failures = list(_item_failures)
                try:
                    _batch_task_results = _record_batch(
                        questions, ground_truths, responses,
                        elapsed, has_error, error_msg, batch_uuid,
                        eval_ctx=eval_ctx,
                        contexts=contexts,
                        expected_tools_list=expected_tools_list,
                    )
                    wrapper._last_task_results = _batch_task_results or []
                    _last_batch_results_holder[0] = _batch_task_results or []  # A8: shared holder
                    _maybe_flush_batch()
                except Exception as rec_exc:
                    logger.debug("batch_eval: record 실패: %s", rec_exc)
                    wrapper._last_task_results = []
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
                        logger.warning("return_format='dataframe' requires pandas")
                        return _resp
                return _resp
            wrapper_with_format._last_failures = []
            wrapper_with_format._last_task_results = []
            wrapper = wrapper_with_format  # type: ignore[assignment]

        wrapper._last_failures = []  # A1: 초기화 (첫 호출 전 속성 존재 보장)
        wrapper._last_task_results = []  # A8: 초기화

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return await func(*args, **kwargs)

            questions, ground_truths, contexts, expected_tools_list = _resolve_batch_args(*args, **kwargs)
            batch_uuid = uuid.uuid4().hex[:8]
            start = time.perf_counter()
            has_error = False
            error_msg: Optional[str] = None
            responses: Any = None
            eval_ctx, _ctx_token = _push_ctx()  # Gap L

            try:
                if concurrent and questions_arg in kwargs and len(questions) > 0:
                    # 항목별 병렬 실행 — asyncio.gather
                    _sem: Optional[asyncio.Semaphore] = (
                        asyncio.Semaphore(max_concurrent) if max_concurrent > 0 else None
                    )

                    async def _call_one(i: int) -> Any:
                        _kw = {**kwargs, questions_arg: [questions[i]]}
                        _kw[ground_truths_arg] = [ground_truths[i]] if i < len(ground_truths) else []
                        if _sem:
                            async with _sem:
                                _r = await (
                                    asyncio.wait_for(func(*args, **_kw), timeout=timeout)
                                    if timeout else func(*args, **_kw)
                                )
                        else:
                            _r = await (
                                asyncio.wait_for(func(*args, **_kw), timeout=timeout)
                                if timeout else func(*args, **_kw)
                            )
                        return _r[0] if isinstance(_r, list) and _r else _r

                    gathered = await asyncio.gather(
                        *[_call_one(i) for i in range(len(questions))],
                        return_exceptions=True,
                    )
                    responses = []
                    for _r in gathered:
                        if isinstance(_r, BaseException):
                            responses.append("")
                            if not has_error:
                                has_error = True
                                error_msg = str(_r)
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
                    _record_batch(
                        questions, ground_truths, responses,
                        elapsed, has_error, error_msg, batch_uuid,
                        eval_ctx=eval_ctx,
                        contexts=contexts,
                        expected_tools_list=expected_tools_list,
                    )
                    _maybe_flush_batch()
                except Exception as rec_exc:
                    logger.debug("batch_eval (async): record 실패: %s", rec_exc)

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
        monitor: "PerformanceMonitor",
        task_type: str = "qa",
        *,
        question: str = "",
        ground_truth: str = "",
        context: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        framework: str = "native",
        model_name: str = "",
        task_id: Optional[str] = None,
        task_id_prefix: str = "eval",
        task_id_fn: Optional[Callable] = None,  # Gap AS
        score_fn: Optional[Callable] = None,
        completion_fn: Optional[Callable] = None,
        on_record: Optional[Callable] = None,
        on_error: Optional[Callable] = None,      # (task_result) → None — 오류 시 호출
        alert_rules: Optional[List[Any]] = None,  # SimpleTaskAlertRule 리스트
        sample_rate: float = 1.0,  # Gap R: 컨텍스트 매니저 수준 샘플링
        enabled: bool = True,       # Gap R: 컨텍스트 매니저 수준 활성화
        timeout: Optional[float] = None,  # with 블록 최대 허용 시간(초); 초과 시 has_error=True 기록
        auto_task_id: bool = False,       # A8: True이면 UUID prefix를 "auto"로 변경 (명시적 자동 생성)
        ttft_seconds: Optional[float] = None,  # E4: 외부에서 측정한 TTFT 값 직접 주입 (chunk_step 없이 사용)
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
            self._task_id_fn: Optional[Callable] = None
        elif task_id_fn is not None:
            self._task_id_fn = task_id_fn
            self._task_id: Optional[str] = None  # will be set in __enter__
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
        self._eval_ctx: Optional[_EvalContext] = None
        self._ctx_token: Any = None
        self._skip: bool = False  # Gap R: True 이면 __exit__ 에서 기록 생략
        # A4: nested depth 추적
        self._depth_val: int = 1
        self._prev_depth_token: Any = None
        # A2: chunk-level streaming metrics
        self._chunk_steps: List[Dict[str, Any]] = []
        # G1: 첫 청크 TTFT (None = 미기록); E4: 외부 주입값 있으면 사전 설정
        self._ttft_seconds: Optional[float] = ttft_seconds

    def chunk_step(self, content: str = "", metadata: Optional[Dict[str, Any]] = None) -> "eval_context":
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
        step: Dict[str, Any] = {
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
        duration_s: Optional[float] = None,
        step_type: str = "step",
        success: bool = True,
        output: Optional[str] = None,
    ) -> "eval_context":
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
            self._named_steps: List[Dict[str, Any]] = []
        step: Dict[str, Any] = {
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

    def __enter__(self) -> "eval_context":
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
        _extra_override: Optional[Dict[str, Any]] = None
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

    async def __aenter__(self) -> "eval_context":
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

    def __init__(self, eval_dec: "EvalDecorator") -> None:
        self._eval_dec = eval_dec
        self._ctx: Optional["eval_context"] = None

    def __call__(self, task_type: Optional[str] = None, **kwargs) -> "eval_context":
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
        merged = {k: v for k, v in ctx_defaults.items() if v is not None or k in ("framework", "model_name")}
        merged.update(kwargs)
        _task_type = task_type if task_type is not None else self._eval_dec._defaults.get("task_type", "qa")
        return eval_context(self._eval_dec._monitor, _task_type, **merged)

    def __enter__(self) -> "eval_context":
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

    def __init__(self, eval_dec: "EvalDecorator", task_type: str, **base_kwargs: Any) -> None:
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
        eval = EvalDecorator(monitor, framework="langchain", model_name="gpt-4o-mini")

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
        "alert_rules", "flush_every", "flush_filename",
        "sample_condition",  # Gap BA
        "custom_parser",     # A9
        "allow_duplicate_task_ids",  # A5: task_id 중복 감지
        "enable_hallucination",      # G4: per-call hallucination detection
        "rag_mode",                  # E2: RAG 단축
        "security_mode",             # E3: 보안 단축
        "allowed_tools",             # E3: 허용된 도구 목록
        "enable_llm_judge",          # E1: per-call LLM Judge
        "judge_model",               # E1: LLM Judge 모델
        "judge_criteria",            # J1: G-Eval 스타일 커스텀 평가 기준
        "enable_anomaly_detection",  # E1: per-call anomaly detection
        "enable_quality_evaluation", # P2-B: per-call quality evaluation
        "timeout",                   # A: 함수 실행 최대 허용 시간(초)
    })
    # batch_eval 이 지원하는 _defaults 파라미터 — _COMMON_PARAMS 초과분 포함
    # NOTE: 새 파라미터 추가 시 batch_eval 시그니처와 함께 이 frozenset도 업데이트 필요  # A5
    _BATCH_PARAMS: frozenset = frozenset({
        "framework", "model_name", "sample_rate", "enabled",
        "on_record", "on_error", "score_fn", "completion_fn",
        "task_id_prefix", "task_id_fn",
        "alert_rules", "flush_every", "flush_filename",
        "timeout", "context_arg", "expected_tools_arg",
        "sample_condition", "on_batch_progress",  # Gap BA / Gap I
        "on_batch_complete",  # AM: 배치 전체 완료 콜백
        "item_timeout",       # A1: 개별 아이템 타임아웃
        "return_format",      # A8: 반환 형식 (list/tuple/dataframe)
        "allow_duplicate_task_ids",  # A5: task_id 중복 감지
        "streaming_mode",     # G1: 메모리 효율적 스트리밍 모드
        "preset",             # A1: 사전 정의 파라미터 묶음
    })
    # conversation_eval 에는 framework/model_name/score_fn/completion_fn 미전달
    _CONV_PARAMS: frozenset = frozenset({
        "sample_rate", "enabled", "alert_rules", "on_session_timeout",  # Gap J
        # A4/D9: 추가 conversation_eval 파라미터
        "on_flush", "on_turn", "session_score_fn", "turn_score_fn",
        "max_turns", "flush_on_error", "max_session_seconds",
        "flush_every", "flush_filename",
        "load_previous_session",  # A7: 이전 세션 이력 로드
        "participant_id_arg",     # A3: 참여자 ID 추적
        "max_turns_exceeded_action",  # A10: 최대 턴 초과 액션
        "on_error",               # Gap A2: 오류 태스크 기록 후 호출되는 콜백
        "preset",                 # A1: 사전 정의 파라미터 묶음
        "on_record",              # C: 세션 flush 후 마지막 TaskResult에 호출되는 콜백
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
        monitor: "Union[PerformanceMonitor, List[PerformanceMonitor]]",
        *,
        framework: "Union[FrameworkLiteral, str]" = "native",
        model_name: str = "",
        sample_rate: float = 1.0,
        enabled: bool = True,
        score_fn: Optional[Callable] = None,
        completion_fn: Optional[Callable] = None,
        on_record: Optional[Callable] = None,
        on_error: Optional[Callable] = None,      # Gap AK
        task_id_prefix: str = "task",
        # Gap AI: agent_eval 파라미터 기본값 — 반복 지정 불필요
        question_arg: str = "question",
        ground_truth_arg: str = "ground_truth",
        context_arg: Optional[str] = None,
        expected_tools_arg: Optional[str] = None,
        task_id_fn: Optional[Callable] = None,
        task_id_arg: Optional[str] = None,        # Gap AQ
        timeout: Optional[float] = None,
        alert_rules: Optional[List[Any]] = None,  # SimpleTaskAlertRule 리스트 기본값
        flush_every: int = 0,                      # N 태스크마다 자동 save_to_file
        flush_filename: str = "eval_auto",         # flush_every 저장 파일명
        sample_condition: Optional[Callable] = None,  # (args, kwargs) → bool 조건부 샘플링
        custom_parser: Optional[Callable] = None,     # A9: framework adapter 전 EvalMetadata 생성
        # H4: 단축 속성에서 자동 전파되는 eval 모드 플래그
        rag_mode: bool = False,
        security_mode: bool = False,
        enable_llm_judge: bool = False,
        judge_model: Optional[str] = None,
        judge_criteria: Optional[List[str]] = None,  # J1: G-Eval 스타일 커스텀 평가 기준
        enable_anomaly_detection: bool = False,
        # P2-B: per-call 품질 평가 강제 활성화
        enable_quality_evaluation: bool = False,
    ) -> None:
        self._monitor = monitor
        self._defaults: Dict[str, Any] = {
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
            "task_id_arg": task_id_arg,           # Gap AQ
            "timeout": timeout,
            "alert_rules": alert_rules,
            "flush_every": flush_every,
            "flush_filename": flush_filename,
            "sample_condition": sample_condition,
            "custom_parser": custom_parser,        # A9
            # H4: eval 모드 플래그
            "rag_mode": rag_mode,
            "security_mode": security_mode,
            "enable_llm_judge": enable_llm_judge,
            "judge_model": judge_model,
            "judge_criteria": judge_criteria,      # J1
            "enable_anomaly_detection": enable_anomaly_detection,
            "enable_quality_evaluation": enable_quality_evaluation,  # P2-B
        }

    @property
    def monitor(self) -> "Union[PerformanceMonitor, List[PerformanceMonitor]]":
        """기저 :class:`~agent_evaluator.PerformanceMonitor` 인스턴스 반환 (Gap AA).

        ``for_rag()`` / ``for_security()`` 로 생성한 경우에도 동일하게 접근한다.

        Example::

            eval = EvalDecorator.for_rag("results/")
            eval.monitor.save_to_file("rag_results")
        """
        return self._monitor

    def inspect(self) -> Dict[str, Any]:
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
        return agent_eval(self._monitor, task_type, **merged)

    def with_retry(self, task_type: str = "qa", **kwargs) -> Callable:
        """``@agent_eval_with_retry`` 데코레이터 반환.

        Example::

            @eval.with_retry(task_type="qa", max_retries=3, retry_on=(ConnectionError,))
            def fragile(question, ground_truth=""): ...
        """
        merged = {**self._defaults, **kwargs}
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
        return conversation_eval(self._monitor, **merged)

    @property
    def context(self) -> "_ContextShortcut":  # 항목 E: 양방향 호출 지원 — with eval.context(...) / with eval.context as ctx
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
    def for_rag(cls, output_dir: str = "results/", **kwargs) -> "EvalDecorator":
        """RAG 평가에 최적화된 ``EvalDecorator`` 팩토리 메서드 (Gap S).

        ``PerformanceMonitor.for_rag_evaluation()`` 로 monitor 를 생성하고
        기본값으로 ``framework="native"`` 를 적용한다.
        hallucination 감지가 기본 활성화된다.

        Example::

            eval = EvalDecorator.for_rag("results/")

            @eval(task_type="information_retrieval", context_arg="ctx")
            def rag_agent(question, ctx="", ground_truth=""): ...
        """
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor as _PM
        monitor = _PM.for_rag_evaluation(output_dir=output_dir)
        return cls(monitor, **kwargs)

    @classmethod
    def for_security(cls, output_dir: str = "results/", **kwargs) -> "EvalDecorator":
        """보안 평가에 최적화된 ``EvalDecorator`` 팩토리 메서드 (Gap S).

        ``PerformanceMonitor.for_secure_agents()`` 로 monitor 를 생성한다.
        보안 지표(InputSanitization, OutputLeakage, ToolAuth 등)가 기본 활성화된다.

        Example::

            eval = EvalDecorator.for_security("results/")

            @eval(task_type="tool_use")
            def secure_agent(question, ground_truth=""): ...
        """
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor as _PM
        monitor = _PM.for_secure_agents(output_dir=output_dir)
        return cls(monitor, **kwargs)

    def update_defaults(self, **kwargs) -> "EvalDecorator":
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
    def qa(self) -> "_ShortcutCallable":
        """``@eval.qa`` 또는 ``@eval.qa(score_fn=...)`` 단축키 (D1)."""
        return _ShortcutCallable(self, "qa")

    @property
    def tool_use(self) -> "_ShortcutCallable":
        """``@eval.tool_use`` 또는 ``@eval.tool_use(timeout=5.0)`` 단축키 (D1)."""
        return _ShortcutCallable(self, "tool_use")

    @property
    def rag(self) -> "_ShortcutCallable":
        """``@eval.rag`` 또는 ``@eval.rag(score_fn=...)`` 단축키 (D1/H4).

        ``rag_mode=True`` + ``context_arg="context"`` 자동 설정.
        """
        return _ShortcutCallable(
            self, "information_retrieval",
            context_arg=self._defaults.get("context_arg") or "context",
            rag_mode=True,
        )

    @property
    def code(self) -> "_ShortcutCallable":
        """``@eval.code`` 또는 ``@eval.code(score_fn=...)`` 단축키 (D1)."""
        return _ShortcutCallable(self, "code_generation")

    @property
    def reasoning(self) -> "_ShortcutCallable":
        """``@eval.reasoning`` 단축키 (D1)."""
        return _ShortcutCallable(self, "reasoning")

    @property
    def planning(self) -> "_ShortcutCallable":
        """``@eval.planning`` 단축키 (D1)."""
        return _ShortcutCallable(self, "planning")

    @property
    def data_analysis(self) -> "_ShortcutCallable":
        """``@eval.data_analysis`` 단축키 (D1)."""
        return _ShortcutCallable(self, "data_analysis")

    @property
    def creative(self) -> "_ShortcutCallable":
        """``@eval.creative`` 단축키 (D1)."""
        return _ShortcutCallable(self, "creative")

    @property
    def multi_agent(self) -> "_ShortcutCallable":
        """``@eval.multi_agent`` 단축키 (D1)."""
        return _ShortcutCallable(self, "tool_use")

    @property
    def secure(self) -> "_ShortcutCallable":
        """``@eval.secure`` 또는 ``@eval.secure(allowed_tools=[...])`` 단축키 (D1/H4).

        ``security_mode=True`` 자동 설정.
        """
        return _ShortcutCallable(self, "tool_use", security_mode=True)

    @property
    def streaming(self) -> "_ShortcutCallable":
        """``@eval.streaming`` 또는 ``@eval.streaming(score_fn=...)`` 단축키 (D1/D4).

        generator/async generator 함수 평가용. task_type은 agent_eval이 자동 처리.
        """
        return _ShortcutCallable(self, "qa")

    @classmethod
    def for_llm_judge(cls, output_dir: str = "results/", model: str = "gpt-4o-mini", **kwargs) -> "EvalDecorator":
        """LLM Judge 평가에 최적화된 ``EvalDecorator`` 팩토리 메서드.

        ``LLMJudge`` 와 ``enable_llm_judge=True`` 를 자동 설정한다.
        ``[llm]`` extras 필요: ``pip install "agent-evaluator[llm]"``.

        Example::

            eval = EvalDecorator.for_llm_judge("results/", model="gpt-4o-mini")

            @eval(task_type="qa")
            def agent(question, ground_truth=""): ...
        """
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

