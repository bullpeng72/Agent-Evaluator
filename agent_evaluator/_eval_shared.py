"""Shared low-level eval plumbing — the value types a decorator/adapter produces
and the primitives for reading a framework's native response object.

Extracted verbatim from ``decorators.py`` (module size reduction). No behaviour
change. ``decorators.py`` re-exports every name here, so
``from agent_evaluator.decorators import EvalMetadata`` stays the public path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

__all__ = [
    "EvalMetadata", "TurnMetadata", "_split_turn_raw",
    "_extract_response", "_is_openai_response", "_is_anthropic_response",
    "_extract_anthropic_tokens", "_is_gemini_response", "_extract_gemini_tokens",
    "_is_cohere_response", "_extract_cohere_tokens", "_is_langchain_response",
    "_split_raw", "_normalize_task_type",
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
