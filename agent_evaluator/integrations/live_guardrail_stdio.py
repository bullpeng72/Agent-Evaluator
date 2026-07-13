"""
agent_evaluator.integrations.live_guardrail_stdio
====================================================
SPEC-019 Rollout 6단계: ``LiveGuardrail``(``gates/live_guardrail.py``)을 서브프로세스
stdio(JSON Lines) 프로토콜로 노출하는 브리지.

Agent-Evaluator는 Python SDK이므로, Node/Bun 등 비-Python 런타임(예: OpenCode 플러그인)이
``LiveGuardrail`` 세션 하나를 구동하려면 프로세스 경계를 넘어야 한다. 이 모듈은 OpenCode
전용이 아니다 — stdin/stdout으로 줄바꿈 구분 JSON을 주고받을 수 있는 어떤 프로세스에서도
쓸 수 있는 범용 브리지다.

실행::

    python -m agent_evaluator.integrations.live_guardrail_stdio

프로토콜 (요청 1줄 → 응답 1줄, 파이프라이닝 없음):

    첫 요청은 반드시 ``{"op": "init", ...}`` — LiveGuardrail 생성자 인자를 JSON으로:

        {"op": "init",
         "loop_detection": {"consecutive_repeat_threshold": 3, "on_loop_detected": "fail"},
         "scope": {"forbidden_tools": ["shell_exec"], "fail_on_violation": true},
         "tool_authorization": {"restricted_tools": ["rm", "shell_exec"]},
         "max_tool_output_chars": 2000}
        → {"ok": true}

    이후:

        {"op": "check", "task_id": "...", "tool_name": "...", "parameters": {...}}
        → {"block": bool, "gate": str|null, "reason": str|null, "detail": {...}}

        {"op": "record", "task_id": "...", "tool_name": "...", "parameters": {...},
         "output": {"success": bool, "exit_code": int, "stdout": "...", "stderr": "..."}}
        → {"ok": true}  # "output"은 선택 — SPEC-031, 생략하면 이전과 동일하게 동작

        {"op": "record_blocked", "task_id": "...", "tool_name": "...",
         "gate": "B"|"E"|null, "reason": "..."}
        → {"ok": true}  # SPEC-030 REQ-6 — check()가 block=true를 반환했고 호출자가
                         # 실제로 그 도구를 실행하지 않기로 했을 때만 보낸다.

        {"op": "snapshot"}
        → {"extra": {...}}  # TaskResult(extra=...)에 그대로 대입 가능 (SPEC-019 REQ-6)

        {"op": "shutdown"}
        → {"ok": true}  (이후 루프 종료)

요청 처리 중 예외는 그 요청 하나만 ``{"error": "..."}``로 응답하고 루프는 계속된다 —
브리지 프로세스는 세션 전체 동안 살아있어야 하므로, 잘못된 요청 하나 때문에 죽으면
안 된다(``core/trackers/monitor.py``의 보안 트래커 enrichment가 트래커별로 예외를
격리하는 것과 동일한 원칙).
"""
from __future__ import annotations

import dataclasses
import json
import sys
from typing import Any, TextIO

from agent_evaluator.core.trackers.security import (
    PrivilegeEscalationDetector,
    ToolAuthorizationTracker,
    ToolChainAttackDetector,
)
from agent_evaluator.gates.gate_b_behavioral.configs import (
    DeadlockConfig,
    LoopDetectionConfig,
    ScopeConfig,
    ToolParameterSafetyConfig,
)
from agent_evaluator.gates.live_guardrail import LiveGuardrail, LiveVerdict

_CONFIG_CLASSES: dict[str, type] = {
    "loop_detection": LoopDetectionConfig,
    "deadlock": DeadlockConfig,
    "scope": ScopeConfig,
    "tool_parameter_safety": ToolParameterSafetyConfig,
}
_TRACKER_CLASSES: dict[str, type] = {
    "tool_authorization": ToolAuthorizationTracker,
    "privilege_escalation": PrivilegeEscalationDetector,
    "tool_chain_attack": ToolChainAttackDetector,
}


def build_guardrail(init_msg: dict[str, Any]) -> LiveGuardrail:
    """``{"op": "init", ...}`` 메시지를 ``LiveGuardrail`` 인스턴스로 변환한다."""
    kwargs: dict[str, Any] = {}
    for key, cls in _CONFIG_CLASSES.items():
        if init_msg.get(key) is not None:
            kwargs[key] = cls(**init_msg[key])
    for key, cls in _TRACKER_CLASSES.items():
        if init_msg.get(key) is not None:
            kwargs[key] = cls(**init_msg[key])
    # SPEC-031: 생략하면 LiveGuardrail의 기본값(2000)을 그대로 쓴다.
    if init_msg.get("max_tool_output_chars") is not None:
        kwargs["max_tool_output_chars"] = init_msg["max_tool_output_chars"]
    return LiveGuardrail(**kwargs)


def _verdict_to_dict(v: LiveVerdict) -> dict[str, Any]:
    return dataclasses.asdict(v)


def _write(outstream: TextIO, payload: dict[str, Any]) -> None:
    outstream.write(json.dumps(payload) + "\n")
    outstream.flush()


def run(instream: TextIO = sys.stdin, outstream: TextIO = sys.stdout) -> None:
    """stdio 요청-응답 루프. ``{"op": "shutdown"}``을 받거나 입력이 끝나면 반환한다."""
    guardrail: LiveGuardrail | None = None

    for line in instream:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            _write(outstream, {"error": f"invalid JSON: {exc}"})
            continue

        op = msg.get("op")
        try:
            if op == "init":
                guardrail = build_guardrail(msg)
                _write(outstream, {"ok": True})
            elif op == "shutdown":
                _write(outstream, {"ok": True})
                break
            elif guardrail is None:
                _write(outstream, {"error": 'guardrail not initialized — send {"op": "init", ...} first'})
            elif op == "check":
                verdict = guardrail.check_before_tool_call(
                    msg["task_id"], msg["tool_name"], msg.get("parameters"),
                )
                _write(outstream, _verdict_to_dict(verdict))
            elif op == "record":
                # SPEC-031 REQ-2: "output"은 선택 — 생략하면 이전과 동일하게 동작한다.
                guardrail.record_tool_call(
                    msg["task_id"], msg["tool_name"], msg.get("parameters"), msg.get("output"),
                )
                _write(outstream, {"ok": True})
            elif op == "record_blocked":
                # SPEC-030 REQ-6: 클라이언트(TS 플러그인 등)가 이전 "check" 응답에서
                # 받은 gate/reason을 그대로 되돌려 보내 LiveVerdict를 재구성한다.
                _verdict = LiveVerdict(
                    block=True, gate=msg.get("gate"), reason=msg.get("reason"),
                )
                guardrail.record_blocked_attempt(msg["task_id"], msg["tool_name"], _verdict)
                _write(outstream, {"ok": True})
            elif op == "snapshot":
                _write(outstream, {"extra": guardrail.to_task_extra()})
            else:
                _write(outstream, {"error": f"unknown op: {op!r}"})
        except Exception as exc:
            _write(outstream, {"error": str(exc)})


if __name__ == "__main__":
    run()
