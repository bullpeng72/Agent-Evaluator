"""The 24 framework adapters + auto-detection + metadata registry.

``@agent_eval(framework=...)`` auto-extracts ``tool_calls`` / ``chain_steps`` /
``tokens_used`` / ``agent_interactions`` from a framework's native return object
by pure duck typing (no framework import; junk input returns ``None``).

Extracted verbatim from ``decorators.py``. ``decorators.py`` re-exports every
public name here unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, cast

from agent_evaluator._eval_shared import (
    EvalMetadata,
    _extract_anthropic_tokens,
    _is_anthropic_response,
    _is_cohere_response,
    _is_gemini_response,
    _is_openai_response,
)

logger = logging.getLogger(__name__)

__all__ = [
    "_CHAIN_STEPS_SUPPORTED",
    "_FRAMEWORK_ADAPTERS",
    "_FRAMEWORK_ADAPTER_META",
    "_FRAMEWORK_PACKAGE_MAP_GLOBAL",
    "_FRAMEWORK_SUBMODULE_MAP",
    "_auto_detect_framework",
    "_check_framework_installed",
    "_extract_anthropic_metadata",
    "_extract_autogen_metadata",
    "_extract_bedrock_metadata",
    "_extract_claude_agent_sdk_metadata",
    "_extract_cohere_metadata",
    "_extract_crewai_metadata",
    "_extract_dspy_metadata",
    "_extract_gemini_metadata",
    "_extract_google_adk_metadata",
    "_extract_groq_metadata",
    "_extract_haystack_metadata",
    "_extract_huggingface_metadata",
    "_extract_langchain_agent_executor_metadata",
    "_extract_langchain_ai_message_metadata",
    "_extract_langchain_metadata",
    "_extract_langgraph_metadata",
    "_extract_llamaindex_metadata",
    "_extract_mistral_metadata",
    "_extract_ollama_metadata",
    "_extract_openai_agents_metadata",
    "_extract_openai_metadata",
    "_extract_pydanticai_metadata",
    "_extract_semantic_kernel_metadata",
    "_extract_smolagents_metadata",
    "_extract_vertexai_metadata",
    "_extract_vllm_metadata",
    "_parse_bedrock_mistral",
    "_parse_titan_response",
    "_safe_adapter_call",
    "_step_time",
    "get_framework_info",
]


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
    """F4: vLLM OpenAI-compatible API 응답에서 메타데이터 추출.

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
        "description": "Native Python return value — no adapter (auto-detected)",
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
        "description": "LangGraph invoke — messages → state_transitions + graph_traversal; ToolMessage/AIMessage → chain_steps",
    },
    "crewai": {
        "name": "CrewAI",
        "extras": "crewai",
        "extracts": ["agent_interactions"],
        "async_supported": False,
        "description": "CrewAI kickoff — tasks_output → agent_interactions; output_pydantic/output_format supported",
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
        "description": "DSPy Prediction — _completions → chain_steps; full multi-step extraction from LM history supported",
    },
    "pydanticai": {
        "name": "PydanticAI",
        "extras": "pydanticai",
        "extracts": ["chain_steps", "tokens_used"],
        "async_supported": True,
        "description": "PydanticAI RunResult — .all_messages() first → chain_steps; ToolCallPart/ToolReturnPart broken out",
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
        "description": "LlamaIndex Response — source_nodes → chain_steps + token extraction from metadata",
    },
    "haystack": {
        "name": "Haystack",
        "extras": "llm",
        "extracts": ["chain_steps"],
        "async_supported": True,
        "description": "Haystack Pipeline — component output dict → chain_steps",
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
        "description": "Cohere SDK — tool_calls + meta.tokens; streaming finish_reason detected",
    },
    "groq": {
        "name": "Groq",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Groq SDK (OpenAI-compatible) — tool_calls + usage; cache_creation/read_tokens (v0.9+)",
    },
    "mistral": {
        "name": "Mistral AI",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Mistral AI SDK — tool_calls + usage; legacy function_call compatibility",
    },
    "bedrock": {
        "name": "AWS Bedrock",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Bedrock Converse API — branch by model_id: Titan/Mistral on Bedrock/Claude",
    },
    "smolagents": {
        "name": "HuggingFace smolagents",
        "extras": "llm",
        "extracts": ["tool_calls", "chain_steps"],
        "async_supported": False,
        "description": "smolagents ToolCall steps — success/failure + input normalization",
    },
    "semantic_kernel": {
        "name": "Semantic Kernel",
        "extras": "llm",
        "extracts": ["chain_steps", "tokens_used"],
        "async_supported": True,
        "description": "Semantic Kernel — auto token extraction from inner_content for the OpenAI/Anthropic backend",
    },
    # F4: 신규 어댑터
    "vllm": {
        "name": "vLLM",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "vLLM OpenAI-compatible API — choices[0].message.tool_calls + usage.total_tokens",
    },
    "huggingface": {
        "name": "HuggingFace",
        "extras": "llm",
        "extracts": ["chain_steps", "tool_calls"],
        "async_supported": False,
        "description": "HuggingFace pipeline()/Agent — generated_text chain_steps; tool_calls/actions extracted",
    },
    "openai_agents": {
        "name": "OpenAI Agents SDK",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "OpenAI Agents SDK (the official successor to Swarm) — ToolCallItem in Runner.run() RunResult.new_items → tool_calls; raw_responses[].usage summed → tokens_used",
    },
    "google_adk": {
        "name": "Google ADK",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Google Agent Development Kit — Event.get_function_calls() → tool_calls; Event.usage_metadata (same fields as gemini) → tokens_used. Must return the last Event of the session",
    },
    "claude_agent_sdk": {
        "name": "Claude Agent SDK",
        "extras": "llm",
        "extracts": ["tool_calls", "tokens_used"],
        "async_supported": True,
        "description": "Claude Agent SDK (formerly Claude Code SDK) — ToolUseBlock in AssistantMessage.content → tool_calls; ResultMessage.usage/total_cost_usd → tokens_used/extra",
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
