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

    요청에 선택적으로 ``"id"``(임의 스칼라)를 넣으면 응답에 그대로 되돌려 실어 준다
    (SPEC-041). 응답이 아직 FIFO 순서로 오지만, ``id``가 있으면 호출자가 순서가
    아니라 ``id``로 응답을 매칭할 수 있어 "요청 A가 타임아웃으로 취소된 뒤 늦게 온
    A의 응답이 다음 요청 B에 잘못 배정되는" 영구 데스싱크를 피할 수 있다. ``id``를
    안 보내면 응답에도 안 붙으므로 기존 호출자는 영향 없음.

    첫 요청은 반드시 ``{"op": "init", ...}`` — LiveGuardrail 생성자 인자를 JSON으로:

        {"op": "init",
         "loop_detection": {"consecutive_repeat_threshold": 3, "on_loop_detected": "fail"},
         "scope": {"forbidden_tools": ["shell_exec"], "fail_on_violation": true},
         "tool_authorization": {"restricted_tools": ["rm", "shell_exec"]},
         "branch_guard": {"protected_branches": ["main", "master"]},
         "team_concurrency": {"owner": "auto"},
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
from agent_evaluator.gates.branch_guard import BranchGuardConfig
from agent_evaluator.gates.gate_b_behavioral.configs import (
    DeadlockConfig,
    LoopDetectionConfig,
    ScopeConfig,
    ToolParameterSafetyConfig,
)
from agent_evaluator.gates.live_guardrail import LiveGuardrail, LiveVerdict
from agent_evaluator.gates.team_concurrency import TeamConcurrencyConfig

_CONFIG_CLASSES: dict[str, type] = {
    "loop_detection": LoopDetectionConfig,
    "deadlock": DeadlockConfig,
    "scope": ScopeConfig,
    "tool_parameter_safety": ToolParameterSafetyConfig,
    # SPEC-035/SPEC-032: branch_guard/team_concurrency were LiveGuardrail constructor
    # kwargs from the start but were never added here, so neither the OpenCode stdio
    # bridge nor the Claude Code hook bridge (which calls build_guardrail() directly,
    # see claude_code_hook.py) could enable them — the only working path was
    # constructing LiveGuardrail() directly in Python. Both fields are plain
    # JSON-serializable dataclasses (str/bool/tuple-of-str), so they slot into the
    # same "init_msg[key] -> cls(**init_msg[key])" pattern as the four configs above.
    "branch_guard": BranchGuardConfig,
    "team_concurrency": TeamConcurrencyConfig,
}
_TRACKER_CLASSES: dict[str, type] = {
    "tool_authorization": ToolAuthorizationTracker,
    "privilege_escalation": PrivilegeEscalationDetector,
    "tool_chain_attack": ToolChainAttackDetector,
}


def build_guardrail(init_msg: dict[str, Any]) -> LiveGuardrail:
    """``{"op": "init", ...}`` 메시지를 ``LiveGuardrail`` 인스턴스로 변환한다.

    SPEC-041: 한 Config/tracker 블록에 오타 키(예: ``consecutive_repeat_treshold``)나
    잘못된 값이 있어도 **그 블록만 건너뛰고** 나머지로 가드레일을 만든다 — 과거엔
    ``cls(**{...})``의 ``TypeError``가 전체 빌드를 깨서 가드레일이 통째로 fail-open
    됐다(설정 오타 하나로 보안 기능이 조용히 꺼짐). 건너뛴 블록은 stderr로 알린다.
    """
    kwargs: dict[str, Any] = {}
    for key, cls in {**_CONFIG_CLASSES, **_TRACKER_CLASSES}.items():
        if init_msg.get(key) is None:
            continue
        try:
            kwargs[key] = cls(**init_msg[key])
        except (TypeError, ValueError) as exc:
            print(
                f"[agent-evaluator] guardrail config '{key}' is invalid and was SKIPPED "
                f"(the rest of the guardrail is still active): {exc}",
                file=sys.stderr,
            )
    # SPEC-031: 생략하면 LiveGuardrail의 기본값(2000)을 그대로 쓴다.
    if init_msg.get("max_tool_output_chars") is not None:
        kwargs["max_tool_output_chars"] = init_msg["max_tool_output_chars"]
    # SPEC-041: 실시간 루프 판정 knob (스칼라/리스트라 별도 Config 클래스 없이 그대로 전달).
    if init_msg.get("live_loop_window") is not None:
        kwargs["live_loop_window"] = init_msg["live_loop_window"]
    if init_msg.get("live_loop_blocking_types") is not None:
        kwargs["live_loop_blocking_types"] = tuple(init_msg["live_loop_blocking_types"])
    # SPEC-041: tool_authorization 백스톱 스캔에서 제외할 파일 본문 키.
    if init_msg.get("auth_scan_skip_keys") is not None:
        kwargs["auth_scan_skip_keys"] = tuple(init_msg["auth_scan_skip_keys"])
    # SPEC-041: 순수 셸 파일 쓰기(cat/tee/echo/printf 리다이렉트) 완화 on/off.
    if init_msg.get("lenient_shell_file_write") is not None:
        kwargs["lenient_shell_file_write"] = bool(init_msg["lenient_shell_file_write"])
    # SPEC-041: 민감한 쓰기 대상 경로 패턴(None이면 기본값, []면 검사 끔).
    if "protected_write_paths" in init_msg:
        _pwp = init_msg["protected_write_paths"]
        kwargs["protected_write_paths"] = tuple(_pwp) if _pwp is not None else None
    return LiveGuardrail(**kwargs)


def _verdict_to_dict(v: LiveVerdict) -> dict[str, Any]:
    return dataclasses.asdict(v)


def _write(outstream: TextIO, payload: dict[str, Any], _req_id: Any = None) -> None:
    # SPEC-041: 요청에 "id"가 있으면 응답에 그대로 되돌려 실어 준다 — 비-Python 호출자
    # (OpenCode .ts 등)가 응답을 FIFO 순서가 아니라 id로 매칭할 수 있게 해, 한 요청이
    # 타임아웃으로 취소된 뒤 늦게 도착한 응답이 다음 요청에 잘못 배정되는 데스싱크를
    # 막는다. id가 없으면(구 호출자) 필드를 안 붙이므로 기존 동작과 100% 동일하다.
    if _req_id is not None and "id" not in payload:
        payload = {**payload, "id": _req_id}
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

        _req_id = msg.get("id") if isinstance(msg, dict) else None
        op = msg.get("op")
        try:
            if op == "init":
                guardrail = build_guardrail(msg)
                _write(outstream, {"ok": True}, _req_id)
            elif op == "shutdown":
                _write(outstream, {"ok": True}, _req_id)
                break
            elif guardrail is None:
                _write(
                    outstream,
                    {"error": 'guardrail not initialized — send {"op": "init", ...} first'},
                    _req_id,
                )
            elif op == "check":
                verdict = guardrail.check_before_tool_call(
                    msg["task_id"], msg["tool_name"], msg.get("parameters"),
                )
                _write(outstream, _verdict_to_dict(verdict), _req_id)
            elif op == "record":
                # SPEC-031 REQ-2: "output"은 선택 — 생략하면 이전과 동일하게 동작한다.
                guardrail.record_tool_call(
                    msg["task_id"], msg["tool_name"], msg.get("parameters"), msg.get("output"),
                )
                _write(outstream, {"ok": True}, _req_id)
            elif op == "record_blocked":
                # SPEC-030 REQ-6: 클라이언트(TS 플러그인 등)가 이전 "check" 응답에서
                # 받은 gate/reason을 그대로 되돌려 보내 LiveVerdict를 재구성한다.
                _verdict = LiveVerdict(
                    block=True, gate=msg.get("gate"), reason=msg.get("reason"),
                )
                guardrail.record_blocked_attempt(msg["task_id"], msg["tool_name"], _verdict)
                _write(outstream, {"ok": True}, _req_id)
            elif op == "snapshot":
                _write(outstream, {"extra": guardrail.to_task_extra()}, _req_id)
            else:
                _write(outstream, {"error": f"unknown op: {op!r}"}, _req_id)
        except Exception as exc:
            _write(outstream, {"error": str(exc)}, _req_id)


if __name__ == "__main__":
    run()
