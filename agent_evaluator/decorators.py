"""
@agent_eval / @agent_eval_async / @agent_eval_with_retry / @conversation_eval
=============================================================================
Opik ``@track`` 스타일로 agent-evaluator를 적용할 수 있는 데코레이터 모음.

데코레이터 목록
---------------
``agent_eval``
    동기 에이전트 함수에 Layer 1+2 평가를 자동 적용.
``agent_eval_async``
    비동기 에이전트 함수용.
``agent_eval_with_retry``
    재시도 로직 내장 + 실제 ``attempts`` 카운트를 정확히 기록.
    동기·비동기 함수를 모두 지원한다.
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
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from agent_evaluator import PerformanceMonitor

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
    """
    return (
        raw is not None
        and hasattr(raw, "meta")
        and hasattr(getattr(raw, "meta", None), "tokens")
        and not hasattr(raw, "choices")  # OpenAI / Mistral 과 구별
    )


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
) -> Tuple[str, str, Optional[str], Optional[List[str]]]:
    """bound arguments 에서 question / ground_truth / context / expected_tools 를 꺼낸다."""
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
) -> Optional[Any]:
    """TaskResult 를 생성·병합·기록하는 공통 로직. sync/async/streaming/Gemini wrapper 양쪽에서 호출."""
    try:
        from agent_evaluator.helpers.taskresult_helpers import (
            create_taskresult_from_execution,
        )

        raw_result, eval_meta = _split_raw(raw)
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
            decorator_framework=framework,
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

        _record_to_monitors(monitor, task_result)  # Gap U: 단일/리스트 모두 지원

        if on_record is not None:
            try:
                on_record(task_result)
            except Exception as cb_exc:
                logger.debug("on_record 콜백 실패 (무시): %s", cb_exc)

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
# 동기 데코레이터
# ---------------------------------------------------------------------------

def agent_eval(
    monitor: "PerformanceMonitor",
    task_type: str = "qa",
    *,
    question_arg: str = "question",
    ground_truth_arg: str = "ground_truth",
    task_id_prefix: str = "task",
    context_arg: Optional[str] = None,
    expected_tools_arg: Optional[str] = None,
    framework: str = "native",
    model_name: str = "",
    score_fn: Optional[Callable] = None,
    completion_fn: Optional[Callable] = None,
    task_id_fn: Optional[Callable] = None,
    task_id_arg: Optional[str] = None,    # Gap AQ
    sample_rate: float = 1.0,
    on_record: Optional[Callable] = None,
    on_error: Optional[Callable] = None,  # Gap AK
    timeout: Optional[float] = None,
    enabled: bool = True,
) -> Callable:
    """동기·비동기 에이전트 함수에 평가를 자동 적용하는 데코레이터 (sync/async 자동 감지).

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
    def decorator(func: Callable) -> Callable:
        if not enabled:
            return func

        sig = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return func(*args, **kwargs)

            question, ground_truth, context, expected_tools = _resolve_args(
                sig, args, kwargs,
                question_arg, ground_truth_arg, context_arg, expected_tools_arg,
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

            try:
                if timeout is not None:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
                        try:
                            raw = _ex.submit(func, *args, **kwargs).result(timeout=timeout)
                        except concurrent.futures.TimeoutError:
                            raise TimeoutError(f"exceeded {timeout}s")
                else:
                    raw = func(*args, **kwargs)
                caller_result, _ = _split_raw(raw)  # EvalMetadata 분리
                return caller_result
            except Exception as exc:
                has_error = True
                error_msg = str(exc)
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)
                _build_and_record(
                    monitor,
                    task_type=task_type,
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
                    on_record=on_record,
                    on_error=on_error,
                )

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return await func(*args, **kwargs)

            question, ground_truth, context, expected_tools = _resolve_args(
                sig, args, kwargs,
                question_arg, ground_truth_arg, context_arg, expected_tools_arg,
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

            try:
                if timeout is not None:
                    raw = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                else:
                    raw = await func(*args, **kwargs)
                caller_result, _ = _split_raw(raw)
                return caller_result
            except Exception as exc:
                has_error = True
                error_msg = str(exc)
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)
                _build_and_record(
                    monitor,
                    task_type=task_type,
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
                    on_record=on_record,
                    on_error=on_error,
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
            eval_ctx, _ctx_token = _push_ctx()

            try:
                for chunk in func(*args, **kwargs):
                    if isinstance(chunk, EvalMetadata):  # Gap AV: intercept, don't yield
                        eval_meta_from_gen = chunk
                    else:
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
                _build_and_record(
                    monitor,
                    task_type=task_type,
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
                    on_record=on_record,
                    on_error=on_error,
                )

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
            eval_ctx, _ctx_token = _push_ctx()

            try:
                async for chunk in func(*args, **kwargs):
                    if isinstance(chunk, EvalMetadata):  # Gap AV: intercept, don't yield
                        eval_meta_from_gen = chunk
                    else:
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
                _build_and_record(
                    monitor,
                    task_type=task_type,
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
                    on_record=on_record,
                    on_error=on_error,
                )

        if inspect.isasyncgenfunction(func):
            return agen_wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        if inspect.isgeneratorfunction(func):
            return gen_wrapper
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# 비동기 데코레이터 — agent_eval 의 별칭 (하위 호환)
# ---------------------------------------------------------------------------

def agent_eval_async(
    monitor: "PerformanceMonitor",
    task_type: str = "qa",
    *,
    question_arg: str = "question",
    ground_truth_arg: str = "ground_truth",
    task_id_prefix: str = "task",
    context_arg: Optional[str] = None,
    expected_tools_arg: Optional[str] = None,
    framework: str = "native",
    model_name: str = "",
    score_fn: Optional[Callable] = None,
    completion_fn: Optional[Callable] = None,
    task_id_fn: Optional[Callable] = None,
    task_id_arg: Optional[str] = None,    # Gap AQ
    sample_rate: float = 1.0,
    on_record: Optional[Callable] = None,
    on_error: Optional[Callable] = None,  # Gap AK
    timeout: Optional[float] = None,
    enabled: bool = True,
) -> Callable:
    """비동기 에이전트 함수용 데코레이터.

    ``agent_eval`` 이 sync/async 를 자동 감지하므로, 이 함수는
    ``agent_eval`` 의 하위 호환 별칭으로 유지된다. 동작이 완전히 동일하다.

    Example::

        @agent_eval_async(monitor, task_type="qa")
        async def async_agent(question: str, ground_truth: str = "") -> str:
            return await llm.apredict(question)
    """
    return agent_eval(
        monitor,
        task_type,
        question_arg=question_arg,
        ground_truth_arg=ground_truth_arg,
        task_id_prefix=task_id_prefix,
        context_arg=context_arg,
        expected_tools_arg=expected_tools_arg,
        framework=framework,
        model_name=model_name,
        score_fn=score_fn,
        completion_fn=completion_fn,
        task_id_fn=task_id_fn,
        task_id_arg=task_id_arg,
        sample_rate=sample_rate,
        on_record=on_record,
        on_error=on_error,
        timeout=timeout,
        enabled=enabled,
    )


# ---------------------------------------------------------------------------
# @agent_eval_with_retry — 재시도 로직 내장
# ---------------------------------------------------------------------------

def agent_eval_with_retry(
    monitor: "PerformanceMonitor",
    task_type: str = "qa",
    *,
    max_retries: int = 3,
    retry_on: Tuple[type, ...] = (Exception,),
    delay: float = 0.0,
    backoff: float = 1.0,
    jitter: bool = False,         # Gap AR
    question_arg: str = "question",
    ground_truth_arg: str = "ground_truth",
    task_id_prefix: str = "task",
    context_arg: Optional[str] = None,
    expected_tools_arg: Optional[str] = None,
    framework: str = "native",
    model_name: str = "",
    score_fn: Optional[Callable] = None,
    completion_fn: Optional[Callable] = None,
    task_id_fn: Optional[Callable] = None,
    task_id_arg: Optional[str] = None,    # Gap AQ
    sample_rate: float = 1.0,
    on_record: Optional[Callable] = None,
    on_error: Optional[Callable] = None,  # Gap AK
    on_retry: Optional[Callable] = None,  # Gap AJ
    timeout: Optional[float] = None,
    enabled: bool = True,
) -> Callable:
    """재시도 로직 내장 + 실제 ``attempts`` 카운트를 정확히 기록하는 데코레이터.

    동기·비동기 함수를 모두 지원한다. 함수 타입은 자동 감지한다.

    Args:
        monitor: :class:`~agent_evaluator.PerformanceMonitor` 인스턴스.
        task_type: Task 유형.
        max_retries: 최대 재시도 횟수 (첫 시도 포함, 기본 3).
        retry_on: 재시도를 트리거할 예외 타입 튜플 (기본: ``(Exception,)``).
        delay: 첫 재시도 전 대기 시간 (초, 기본 0).
        backoff: 지수 백오프 계수 (기본 1.0 = 고정 딜레이).
            ``delay=1.0, backoff=2.0`` 이면 1s → 2s → 4s 로 증가한다.
        question_arg: 질문 파라미터 이름 (기본: ``"question"``).
        ground_truth_arg: 정답 파라미터 이름 (기본: ``"ground_truth"``).
        task_id_prefix: task_id 접두어 (기본: ``"task"``).
        context_arg: RAG context 파라미터 이름.
        expected_tools_arg: expected_tools 파라미터 이름.
        framework: 프레임워크 식별자 (기본: ``"native"``).
        model_name: LLM 모델명.
        score_fn: 커스텀 accuracy 계산 함수.
        completion_fn: 커스텀 completion 계산 함수.
        task_id_fn: task_id 생성 함수 ``(args: tuple, kwargs: dict) -> str``.
            ``None`` 이면 ``{prefix}_{uuid8}`` 로 자동 생성한다.
        sample_rate: 평가 실행 비율 ``[0.0, 1.0]`` (기본: ``1.0`` = 항상 평가).
            샘플링 제외 시 재시도 없이 원본 함수만 1회 실행한다.
        enabled: ``False`` 이면 재시도 없이 원본 함수만 실행한다.

    Example::

        @agent_eval_with_retry(
            monitor,
            task_type="qa",
            max_retries=3,
            retry_on=(ConnectionError, TimeoutError),
            delay=1.0,
            backoff=2.0,
        )
        def fragile_agent(question: str, ground_truth: str = "") -> str:
            return llm.predict(question)   # 실패 시 최대 3회까지 재시도
        # attempts=실제시도횟수, errors=[오류1, 오류2, ...] 로 기록
    """
    def decorator(func: Callable) -> Callable:
        if not enabled:
            return func

        is_async = asyncio.iscoroutinefunction(func)
        sig = inspect.signature(func)

        def _run_sync(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return func(*args, **kwargs)

            question, ground_truth, context, expected_tools = _resolve_args(
                sig, args, kwargs,
                question_arg, ground_truth_arg, context_arg, expected_tools_arg,
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
            errors: List[str] = []
            raw: Any = None
            attempt = 0
            wait = delay
            eval_ctx, _ctx_token = _push_ctx()

            try:
                while attempt < max_retries:
                    attempt += 1
                    try:
                        if timeout is not None:
                            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
                                try:
                                    raw = _ex.submit(func, *args, **kwargs).result(timeout=timeout)
                                except concurrent.futures.TimeoutError:
                                    raise TimeoutError(f"exceeded {timeout}s")
                        else:
                            raw = func(*args, **kwargs)
                        break
                    except retry_on as exc:
                        errors.append(str(exc))
                        # Gap AJ: on_retry 콜백 — 예외 무시
                        if on_retry is not None:
                            try:
                                on_retry(attempt, str(exc))
                            except Exception as e:
                                logger.debug("on_retry 콜백 실패: %s", e)
                        if attempt < max_retries:
                            if wait > 0:
                                # Gap AR: jitter — random delay in [0, wait]
                                actual_wait = random.uniform(0.0, wait) if jitter else wait
                                time.sleep(actual_wait)
                            wait = wait * backoff
                        elif attempt >= max_retries:
                            raise
                caller_result, _ = _split_raw(raw)
                return caller_result
            except Exception:
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)
                has_error = len(errors) >= max_retries
                error_msg = errors[-1] if errors else None
                try:
                    from agent_evaluator.helpers.taskresult_helpers import (
                        create_taskresult_from_execution,
                    )
                    raw_result, eval_meta = _split_raw(raw)
                    response = _extract_response(raw_result) if raw is not None else ""
                    openai_resp = raw_result if _is_openai_response(raw_result) else None
                    anthropic_resp = raw_result if _is_anthropic_response(raw_result) else None
                    lc_resp = raw_result if _is_langchain_response(raw_result) else None
                    gemini_resp = raw_result if _is_gemini_response(raw_result) else None
                    cohere_resp = raw_result if _is_cohere_response(raw_result) else None  # Gap O
                    # Gap J: model_name — EvalMetadata > eval_ctx > decorator
                    effective_model = model_name
                    if eval_ctx is not None and getattr(eval_ctx, "model_name", None):
                        effective_model = eval_ctx.model_name
                    if eval_meta is not None and getattr(eval_meta, "model_name", None):
                        effective_model = eval_meta.model_name

                    task_result = create_taskresult_from_execution(
                        task_id=task_id,
                        question=question,
                        response=response,
                        ground_truth=ground_truth,
                        execution_time=elapsed,
                        openai_response=openai_resp,
                        langchain_result=lc_resp,
                        has_error=has_error,
                        error_message=error_msg,
                        task_type=task_type,
                        context=context,
                        model_name=effective_model,
                    )
                    # Anthropic 응답 토큰 주입 (exact > heuristic)
                    if anthropic_resp is not None:
                        ant_tokens = _extract_anthropic_tokens(anthropic_resp)
                        if ant_tokens is not None:
                            task_result = dataclasses.replace(task_result, tokens_used=ant_tokens)
                    if gemini_resp is not None:
                        gem_tokens = _extract_gemini_tokens(gemini_resp)
                        if gem_tokens is not None:
                            task_result = dataclasses.replace(task_result, tokens_used=gem_tokens)
                    if cohere_resp is not None:  # Gap O
                        coh_tokens = _extract_cohere_tokens(cohere_resp)
                        if coh_tokens is not None:
                            task_result = dataclasses.replace(task_result, tokens_used=coh_tokens)
                    # attempts + errors 주입 (retry 핵심 데이터)
                    task_result = dataclasses.replace(
                        task_result,
                        attempts=attempt,
                        errors=errors if errors else task_result.errors,
                    )
                    if expected_tools is not None and task_result.expected_tools is None:
                        task_result = dataclasses.replace(
                            task_result, expected_tools=expected_tools
                        )
                    task_result = _apply_overrides(
                        task_result,
                        decorator_framework=framework,
                        eval_ctx=eval_ctx,
                        eval_meta=eval_meta,
                        score_fn=score_fn,
                        completion_fn=completion_fn,
                        response=response,
                        ground_truth=ground_truth,
                    )
                    _record_to_monitors(monitor, task_result)  # Gap U
                    if on_record is not None:
                        try:
                            on_record(task_result)
                        except Exception as cb_exc:
                            logger.debug("on_record 콜백 실패 (무시): %s", cb_exc)
                    # Gap AK: on_error 콜백
                    if on_error is not None and has_error:
                        try:
                            on_error(task_result)
                        except Exception as e:
                            logger.debug("on_error 콜백 실패: %s", e)
                except Exception as rec_exc:
                    logger.debug("agent_eval_with_retry: record 실패: %s", rec_exc)

        async def _run_async(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return await func(*args, **kwargs)

            question, ground_truth, context, expected_tools = _resolve_args(
                sig, args, kwargs,
                question_arg, ground_truth_arg, context_arg, expected_tools_arg,
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
            errors: List[str] = []
            raw: Any = None
            attempt = 0
            wait = delay
            eval_ctx, _ctx_token = _push_ctx()

            try:
                while attempt < max_retries:
                    attempt += 1
                    try:
                        if timeout is not None:
                            raw = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                        else:
                            raw = await func(*args, **kwargs)
                        break
                    except retry_on as exc:
                        errors.append(str(exc))
                        # Gap AJ: on_retry 콜백
                        if on_retry is not None:
                            try:
                                on_retry(attempt, str(exc))
                            except Exception as e:
                                logger.debug("on_retry 콜백 실패: %s", e)
                        if attempt < max_retries:
                            if wait > 0:
                                # Gap AR: jitter
                                actual_wait = random.uniform(0.0, wait) if jitter else wait
                                await asyncio.sleep(actual_wait)
                            wait = wait * backoff
                        elif attempt >= max_retries:
                            raise
                caller_result, _ = _split_raw(raw)
                return caller_result
            except Exception:
                raise
            finally:
                elapsed = time.perf_counter() - start
                _pop_ctx(_ctx_token)
                has_error = len(errors) >= max_retries
                error_msg = errors[-1] if errors else None
                try:
                    from agent_evaluator.helpers.taskresult_helpers import (
                        create_taskresult_from_execution,
                    )
                    raw_result, eval_meta = _split_raw(raw)
                    response = _extract_response(raw_result) if raw is not None else ""
                    openai_resp = raw_result if _is_openai_response(raw_result) else None
                    anthropic_resp = raw_result if _is_anthropic_response(raw_result) else None
                    lc_resp = raw_result if _is_langchain_response(raw_result) else None
                    gemini_resp = raw_result if _is_gemini_response(raw_result) else None
                    cohere_resp = raw_result if _is_cohere_response(raw_result) else None  # Gap O
                    # Gap J: model_name — EvalMetadata > eval_ctx > decorator
                    effective_model = model_name
                    if eval_ctx is not None and getattr(eval_ctx, "model_name", None):
                        effective_model = eval_ctx.model_name
                    if eval_meta is not None and getattr(eval_meta, "model_name", None):
                        effective_model = eval_meta.model_name

                    task_result = create_taskresult_from_execution(
                        task_id=task_id,
                        question=question,
                        response=response,
                        ground_truth=ground_truth,
                        execution_time=elapsed,
                        openai_response=openai_resp,
                        langchain_result=lc_resp,
                        has_error=has_error,
                        error_message=error_msg,
                        task_type=task_type,
                        context=context,
                        model_name=effective_model,
                    )
                    # Anthropic 응답 토큰 주입 (exact > heuristic)
                    if anthropic_resp is not None:
                        ant_tokens = _extract_anthropic_tokens(anthropic_resp)
                        if ant_tokens is not None:
                            task_result = dataclasses.replace(task_result, tokens_used=ant_tokens)
                    if gemini_resp is not None:
                        gem_tokens = _extract_gemini_tokens(gemini_resp)
                        if gem_tokens is not None:
                            task_result = dataclasses.replace(task_result, tokens_used=gem_tokens)
                    if cohere_resp is not None:  # Gap O
                        coh_tokens = _extract_cohere_tokens(cohere_resp)
                        if coh_tokens is not None:
                            task_result = dataclasses.replace(task_result, tokens_used=coh_tokens)
                    task_result = dataclasses.replace(
                        task_result,
                        attempts=attempt,
                        errors=errors if errors else task_result.errors,
                    )
                    if expected_tools is not None and task_result.expected_tools is None:
                        task_result = dataclasses.replace(
                            task_result, expected_tools=expected_tools
                        )
                    task_result = _apply_overrides(
                        task_result,
                        decorator_framework=framework,
                        eval_ctx=eval_ctx,
                        eval_meta=eval_meta,
                        score_fn=score_fn,
                        completion_fn=completion_fn,
                        response=response,
                        ground_truth=ground_truth,
                    )
                    _record_to_monitors(monitor, task_result)  # Gap U
                    if on_record is not None:
                        try:
                            on_record(task_result)
                        except Exception as cb_exc:
                            logger.debug("on_record 콜백 실패 (무시): %s", cb_exc)
                    # Gap AK: on_error 콜백
                    if on_error is not None and has_error:
                        try:
                            on_error(task_result)
                        except Exception as e:
                            logger.debug("on_error 콜백 실패: %s", e)
                except Exception as rec_exc:
                    logger.debug("agent_eval_with_retry (async): record 실패: %s", rec_exc)

        if is_async:
            return functools.wraps(func)(_run_async)
        return functools.wraps(func)(_run_sync)

    return decorator


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
        # Gap M: on_flush 콜백 — 예외 무시
        if on_flush_cb is not None:
            try:
                on_flush_cb(session_id)
            except Exception as cb_exc:
                logger.debug("on_flush 콜백 실패 (무시): %s", cb_exc)
    except Exception as exc:
        logger.debug("flush_conversation: 세션 '%s' flush 실패: %s", session_id, exc)


def conversation_eval(
    monitor: "PerformanceMonitor",
    *,
    session_id_arg: str = "session_id",
    user_arg: str = "question",
    ground_truth_arg: str = "ground_truth",
    max_turns: Optional[int] = None,
    flush_on_error: bool = True,
    sample_rate: float = 1.0,
    on_flush: Optional[Callable] = None,              # Gap M: (session_id: str) → None
    on_turn: Optional[Callable] = None,               # Gap Z: (session_id, user, response, metadata) → None
    session_score_fn: Optional[Callable] = None,      # Gap T: (ConversationMetrics) → float
    turn_score_fn: Optional[Callable] = None,         # Gap AX: (user, response, metadata) → float
    max_session_seconds: Optional[float] = None,      # Gap AY: 비활성 세션 자동 flush 타이머
    enabled: bool = True,
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
    def decorator(func: Callable) -> Callable:
        if not enabled:
            return func

        is_async = asyncio.iscoroutinefunction(func)
        sig = inspect.signature(func)

        def _get_or_create_session(session_id: str) -> Dict[str, Any]:
            with _conv_sessions_lock:
                if session_id not in _CONV_SESSIONS:
                    sampled = sample_rate >= 1.0 or random.random() < sample_rate
                    _CONV_SESSIONS[session_id] = {
                        "session_id": session_id,
                        "monitor": monitor,
                        "turns": [],
                        "sampled": sampled,
                        "on_flush": on_flush,           # Gap M
                        "session_score_fn": session_score_fn,  # Gap T
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
            user_msg = all_args.get(user_arg)
            if user_msg is None:
                param_names = list(sig.parameters.keys())
                user_msg = all_args.get(param_names[0], "") if param_names else ""
            # Gap AD: ground_truth 실제 추출 (기존 "현재 미사용" → 턴 metadata에 저장)
            ground_truth_val = str(all_args.get(ground_truth_arg) or "")
            return str(session_id), str(user_msg), ground_truth_val

        def _build_turn_metadata(
            elapsed: float, turn_meta: Optional[TurnMetadata]
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
                if turn_meta.extra:
                    meta.update(turn_meta.extra)
            return meta

        def _reset_timer(session_id: str, entry: Dict[str, Any]) -> None:
            """Gap AY: max_session_seconds 타이머를 재설정한다."""
            if max_session_seconds is None:
                return
            old = entry.get("_timer")
            if old is not None:
                old.cancel()
            t = threading.Timer(max_session_seconds, lambda: flush_conversation(session_id))
            t.daemon = True
            t.start()
            entry["_timer"] = t

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            session_id, user_msg, ground_truth = _extract_session_args(*args, **kwargs)  # Gap AD
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
                    metadata = _build_turn_metadata(elapsed, turn_meta)
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
                        flush_conversation(session_id)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            session_id, user_msg, ground_truth = _extract_session_args(*args, **kwargs)  # Gap AD
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
                    metadata = _build_turn_metadata(elapsed, turn_meta)
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
    on_batch_complete: Optional[Callable] = None,  # Gap AM: (results: List[TaskResult]) → None
    sample_rate: float = 1.0,
    timeout: Optional[float] = None,            # Gap X: 배치 전체 함수 실행 제한 시간(초)
    enabled: bool = True,
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
    def decorator(func: Callable) -> Callable:
        if not enabled:
            return func

        is_async = asyncio.iscoroutinefunction(func)
        sig = inspect.signature(func)

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
        ) -> None:
            if not isinstance(responses, list):
                responses = [responses] if responses is not None else []

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
                    has_error=has_error and i == len(responses) - 1,
                    error_msg=error_msg if has_error else None,
                    model_name=model_name,
                    framework=framework,
                    score_fn=score_fn,
                    completion_fn=completion_fn,
                    eval_ctx=eval_ctx,  # Gap L: 배치 공통 eval_ctx 전달
                    on_record=on_record,
                )
                if tr is not None:
                    batch_results.append(tr)

            # Gap AM: on_batch_complete 콜백
            if on_batch_complete is not None and batch_results:
                try:
                    on_batch_complete(batch_results)
                except Exception as e:
                    logger.debug("on_batch_complete 콜백 실패: %s", e)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if sample_rate < 1.0 and random.random() > sample_rate:
                return func(*args, **kwargs)

            questions, ground_truths, contexts, expected_tools_list = _resolve_batch_args(*args, **kwargs)
            batch_uuid = uuid.uuid4().hex[:8]
            start = time.perf_counter()
            has_error = False
            error_msg: Optional[str] = None
            responses: Any = None
            eval_ctx, _ctx_token = _push_ctx()  # Gap L

            try:
                if timeout is not None:  # Gap X: 배치 전체 timeout
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
                        try:
                            responses = _ex.submit(func, *args, **kwargs).result(timeout=timeout)
                        except concurrent.futures.TimeoutError:
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
                try:
                    _record_batch(
                        questions, ground_truths, responses,
                        elapsed, has_error, error_msg, batch_uuid,
                        eval_ctx=eval_ctx,
                        contexts=contexts,
                        expected_tools_list=expected_tools_list,
                    )
                except Exception as rec_exc:
                    logger.debug("batch_eval: record 실패: %s", rec_exc)

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
                if timeout is not None:  # Gap X: 비동기 배치 timeout
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
                except Exception as rec_exc:
                    logger.debug("batch_eval (async): record 실패: %s", rec_exc)

        return async_wrapper if is_async else wrapper

    return decorator


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
        sample_rate: float = 1.0,  # Gap R: 컨텍스트 매니저 수준 샘플링
        enabled: bool = True,       # Gap R: 컨텍스트 매니저 수준 활성화
    ) -> None:
        self._monitor = monitor
        self._task_type = task_type
        self._context = context
        self._expected_tools = expected_tools
        self._framework = framework
        self._model_name = model_name
        self._score_fn = score_fn
        self._completion_fn = completion_fn
        self._on_record = on_record
        self._sample_rate = sample_rate
        self._enabled = enabled
        # Gap AS: task_id priority: task_id > task_id_fn > auto
        if task_id is not None:
            self._task_id = task_id
            self._task_id_fn: Optional[Callable] = None
        elif task_id_fn is not None:
            self._task_id_fn = task_id_fn
            self._task_id: Optional[str] = None  # will be set in __enter__
        else:
            self._task_id = f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
            self._task_id_fn = None
        self._task_id_prefix = task_id_prefix

        # Gap K: 공개 속성 — with 블록 내에서 자유롭게 재설정 가능
        self.question: str = question
        self.ground_truth: str = ground_truth
        self.response: Any = None          # 사용자가 with 블록 내에서 설정

        self._start: float = 0.0
        self._eval_ctx: Optional[_EvalContext] = None
        self._ctx_token: Any = None
        self._skip: bool = False  # Gap R: True 이면 __exit__ 에서 기록 생략

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
        has_error = exc_type is not None
        error_msg = str(exc_val) if exc_val is not None else None
        # Safety fallback for task_id (should not happen normally)
        task_id = self._task_id or f"{self._task_id_prefix}_{uuid.uuid4().hex[:8]}"
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
        )
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
    # batch_eval 필터링에도 사용 (questions_arg 등 배치 전용 파라미터 제외)
    _COMMON_PARAMS: frozenset = frozenset({
        "framework", "model_name", "sample_rate", "enabled",
        "on_record", "score_fn", "completion_fn", "task_id_prefix",
    })
    # conversation_eval 에는 framework/model_name/score_fn/completion_fn/on_record 미전달
    _CONV_PARAMS: frozenset = frozenset({"sample_rate", "enabled"})

    def __init__(
        self,
        monitor: "Union[PerformanceMonitor, List[PerformanceMonitor]]",
        *,
        framework: str = "native",
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

    def __call__(self, task_type: str = "qa", **kwargs) -> Callable:
        """``@agent_eval`` 데코레이터 반환.

        Example::

            @eval(task_type="qa")
            def agent(question, ground_truth=""): ...
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

    def batch(self, task_type: str = "qa", **kwargs) -> Callable:
        """``@batch_eval`` 데코레이터 반환.

        Example::

            @eval.batch(task_type="qa", task_id_prefix="qa_batch")
            def qa_batch(questions, ground_truths=None): ...
        """
        # batch_eval 은 questions_arg / ground_truths_arg 파라미터 이름이 다름
        batch_defaults = {k: v for k, v in self._defaults.items()
                          if k in self._COMMON_PARAMS}
        merged = {**batch_defaults, **kwargs}
        return batch_eval(self._monitor, task_type, **merged)

    def conversation(self, **kwargs) -> Callable:
        """``@conversation_eval`` 데코레이터 반환.

        Example::

            @eval.conversation(session_id_arg="sid", max_turns=5)
            def chat(question, sid="s1"): ...
        """
        conv_defaults = {k: v for k, v in self._defaults.items()
                         if k in self._CONV_PARAMS}
        merged = {**conv_defaults, **kwargs}
        return conversation_eval(self._monitor, **merged)

    def context(self, task_type: str = "qa", **kwargs) -> "eval_context":
        """``eval_context`` 컨텍스트 매니저 반환 (Gap S).

        Example::

            with eval.context(task_type="qa", question=q, ground_truth=gt) as ctx:
                ctx.response = external_fn(q)
        """
        # eval_context 는 framework / model_name / sample_rate / enabled 사용
        ctx_defaults = {
            "framework": self._defaults.get("framework", "native"),
            "model_name": self._defaults.get("model_name", ""),
            "sample_rate": self._defaults.get("sample_rate", 1.0),
            "enabled": self._defaults.get("enabled", True),
            "score_fn": self._defaults.get("score_fn"),
            "completion_fn": self._defaults.get("completion_fn"),
            "on_record": self._defaults.get("on_record"),
        }
        merged = {k: v for k, v in ctx_defaults.items() if v is not None or k in ("framework", "model_name")}
        merged.update(kwargs)
        return eval_context(self._monitor, task_type, **merged)

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
