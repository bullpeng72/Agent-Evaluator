"""
agent_evaluator.integrations.claude_code_hook
=================================================
Claude Code CLI 훅(PreToolUse/PostToolUse/SessionEnd) → ``LiveGuardrail`` 브리지.

``live_guardrail_stdio.py``(세션 내내 살아있는 상주 프로세스, 요청-응답 루프)와 달리, Claude
Code 훅은 호출마다 별도 OS 프로세스로 실행되고 프로세스 사이에 메모리를 공유하지 않는다(공식
문서로 확인). 그래서 이 모듈은 세션별 파일에 확정된 tool_call 이력을 남겨두고, 매 훅 호출마다
그 이력을 ``LiveGuardrail.record_tool_call()``로 재생(replay)해 판정 상태를 복원한다 —
``LiveGuardrail`` 자체엔 새 코드를 추가하지 않는다(기존 공개 API만 사용, 새 탐지 로직 없음).

상태 파일 위치(``cwd``가 훅 payload의 ``cwd`` 필드 기준)::

    <cwd>/.claude/.agent-evaluator/sessions/<session_id>.json           # 확정된 tool_call 이력
    <cwd>/.claude/.agent-evaluator/sessions/<session_id>.blocked.json   # 차단된 시도 감사 이력
    <cwd>/.claude/.agent-evaluator/guardrail_config.json                # LiveGuardrail 설정
        (``agent-eval claude install``이 :data:`DEFAULT_GUARDRAIL_CONFIG`를 이 경로에 복사한다 —
        파일이 없으면 이 모듈이 기본값을 그대로 쓴다)

실행 (Claude Code가 ``.claude/settings.json``의 훅 등록을 통해 자동 호출)::

    python -m agent_evaluator.integrations.claude_code_hook < hook_payload.json

훅 판정 실패(예외)는 항상 fail-open이다 — 훅 브리지 자체의 버그가 사용자의 모든 도구 호출을
막아버리면 안 되므로, 예외 발생 시 "판정 없음"(허용)으로 처리하고 조용히 반환한다
(``tool_guard(fail_closed=False)``의 기본값과 동일한 설계 원칙).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from agent_evaluator.gates.live_guardrail import LiveVerdict
from agent_evaluator.integrations.live_guardrail_report import record_and_save
from agent_evaluator.integrations.live_guardrail_stdio import build_guardrail

# OpenCode 플러그인 참조 구현(agent_evaluator/integrations/opencode_plugin/agent-evaluator.ts)의
# GUARDRAIL_CONFIG 기본값과 같은 원칙(loop_detection 6, scope, tool_parameter_safety,
# tool_authorization)을 따르되, 도구 이름은 Claude Code CLI 자체 명명(예: "Bash", OpenCode의
# 소문자 "bash"가 아님)에 맞췄다. 아래 두 필드는 "같은 원칙"에서 의도적으로 벗어난다 — 이유는
# 각 필드 옆 주석 참고:
DEFAULT_GUARDRAIL_CONFIG: dict[str, Any] = {
    "loop_detection": {
        "consecutive_repeat_threshold": 6,
        # AOO(OpenCode) 기본값은 이 키를 생략해 LoopDetectionConfig의 기본값("record",
        # 관찰만)으로 떨어진다 — OpenCode가 셸 동작 전체를 단일 "bash" 도구로 뭉뚱그려
        # 기록하는 탓에("ls"→"cat"→"ls" 같은 정상 연속 호출도 도구 *이름*만 보면 반복으로
        # 잡힘), 6으로 threshold를 올려도 여전히 오탐 위험이 남아 있어 차단(fail) 대신
        # 관찰(record)로 낮춰뒀다(위 GUARDRAIL_CONFIG 정의부의 라이브 테스트 노트 참고).
        # Claude Code CLI는 도구가 Bash/Read/Edit/Write/WebFetch 등으로 이미 세분화돼 있어
        # 이 오탐 경로 자체가 훨씬 좁다 — 그래서 여기서는 실제 무한 루프를 실행 전에 막는
        # "fail"을 기본값으로 유지한다. 두 기본값이 다른 것은 버그가 아니라 각 스택의 도구
        # 세분성 차이를 반영한 의도적 선택이다.
        "on_loop_detected": "fail",
    },
    "scope": {"forbidden_tools": ["WebFetch"], "fail_on_violation": True},
    "tool_parameter_safety": {
        "dangerous_patterns": [
            r"\.\./", r"&&", r"\|\|", r";.*rm\s", r"\brm\s+\S", r"__import__", r"eval\(", r"exec\(",
        ],
        "scope_tool_names": ["Bash"],
        "fail_on_dangerous": True,
    },
    # Gate E 하드코딩 백스톱(ToolAuthorizationTracker) — allowed_tools/restricted_tools를
    # 안 줘도 하드코딩된 위험 패턴(rm -rf/DROP TABLE/sudo/eval(/exec(/chmod 777 등)을 모든
    # 도구 호출 파라미터에서 스캔해 매치 시 차단한다(security.py의 dangerous_patterns,
    # ToolParameterSafetyConfig의 커스터마이즈 가능한 목록과는 별개). 과거엔 이 키가 빠져
    # 있어 AC 기본 설치가 AOO 기본 설치보다 이 백스톱 하나만큼 약했다 — 파악 즉시 정렬.
    "tool_authorization": {},
    # LiveGuardrail 생성자 인자가 아니라 이 브리지 자체가 SessionEnd에서 쓰는 값 —
    # build_guardrail() 호출 전에 pop()으로 제거한다.
    "output_dir": "results/claude_code_live_guardrail",
}

_STATE_SUBDIR = Path(".claude") / ".agent-evaluator"


def _state_dir(cwd: str) -> Path:
    return Path(cwd or ".") / _STATE_SUBDIR


def _config_path(state_dir: Path) -> Path:
    return state_dir / "guardrail_config.json"


def _session_file(state_dir: Path, session_id: str) -> Path:
    return state_dir / "sessions" / f"{session_id}.json"


def _blocked_file(state_dir: Path, session_id: str) -> Path:
    return state_dir / "sessions" / f"{session_id}.blocked.json"


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _append_json_list(path: Path, record: dict[str, Any]) -> None:
    records = _load_json_list(path)
    records.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def load_config(state_dir: Path) -> dict[str, Any]:
    """``guardrail_config.json``을 읽는다 — 없으면 :data:`DEFAULT_GUARDRAIL_CONFIG`를 그대로
    쓴다."""
    path = _config_path(state_dir)
    if not path.exists():
        return dict(DEFAULT_GUARDRAIL_CONFIG)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_GUARDRAIL_CONFIG)
    return data if isinstance(data, dict) else dict(DEFAULT_GUARDRAIL_CONFIG)


def _replay(guardrail: Any, task_id: str, records: list[dict[str, Any]]) -> None:
    """이전에 확정된 tool_call 이력을 ``record_tool_call()``로 재생해 판정 상태를 복원한다."""
    for record in records:
        guardrail.record_tool_call(
            task_id, record.get("tool_name", ""), record.get("parameters"), record.get("output"),
        )


def handle_pre_tool_use(payload: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    session_id = payload["session_id"]
    tool_name = payload["tool_name"]
    tool_input = payload.get("tool_input") or {}

    config = dict(load_config(state_dir))
    config.pop("output_dir", None)
    guardrail = build_guardrail(config)
    _replay(guardrail, session_id, _load_json_list(_session_file(state_dir, session_id)))

    verdict = guardrail.check_before_tool_call(session_id, tool_name, tool_input)
    if not verdict.block:
        return {
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"},
        }

    guardrail.record_blocked_attempt(session_id, tool_name, verdict)
    _append_json_list(
        _blocked_file(state_dir, session_id),
        {"tool_name": tool_name, "gate": verdict.gate, "reason": verdict.reason},
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": verdict.reason or "blocked by LiveGuardrail",
        },
    }


def handle_post_tool_use(payload: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    session_id = payload["session_id"]
    tool_name = payload["tool_name"]
    tool_input = payload.get("tool_input") or {}
    tool_result = payload.get("tool_result") or {}

    output: dict[str, Any] | None = None
    result_type = tool_result.get("type")
    if result_type is not None:
        success = result_type == "success"
        output = {"success": success}
        content = tool_result.get("content")
        if isinstance(content, str):
            output["stdout" if success else "stderr"] = content

    _append_json_list(
        _session_file(state_dir, session_id),
        {"tool_name": tool_name, "parameters": tool_input, "output": output},
    )
    return {}


def handle_session_end(payload: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    session_id = payload["session_id"]
    config = dict(load_config(state_dir))
    output_dir = config.pop("output_dir", "results/claude_code_live_guardrail")

    guardrail = build_guardrail(config)
    session_file = _session_file(state_dir, session_id)
    blocked_file = _blocked_file(state_dir, session_id)
    _replay(guardrail, session_id, _load_json_list(session_file))
    for blocked in _load_json_list(blocked_file):
        guardrail.record_blocked_attempt(
            session_id, blocked.get("tool_name", ""),
            LiveVerdict(block=True, gate=blocked.get("gate"), reason=blocked.get("reason")),
        )

    extra = guardrail.to_task_extra()
    result = record_and_save({
        "task_id": session_id,
        "extra": extra,
        "output_dir": output_dir,
        "save_filename": "claude_code_sessions",
        "question": "<claude code session>",
        "response": f"<claude code session: {payload.get('reason', 'unknown')}>",
    })

    session_file.unlink(missing_ok=True)
    blocked_file.unlink(missing_ok=True)
    return result


_HANDLERS = {
    "PreToolUse": handle_pre_tool_use,
    "PostToolUse": handle_post_tool_use,
    "SessionEnd": handle_session_end,
}


def run(instream: TextIO = sys.stdin, outstream: TextIO = sys.stdout) -> None:
    """stdin에서 훅 payload 하나를 읽고 stdout에 결과 JSON 한 줄을 쓴다.

    예외는 절대 올리지 않는다 — fail-open(모듈 docstring 참고). 알 수 없는
    ``hook_event_name``(async/display 전용 훅 등)은 조용히 빈 결과를 반환한다.
    """
    raw = instream.read().strip()
    result: dict[str, Any] = {}
    try:
        parsed: Any = json.loads(raw) if raw else {}
        payload: dict[str, Any] = parsed if isinstance(parsed, dict) else {}
        event_name = payload.get("hook_event_name")
        handler = _HANDLERS.get(event_name) if isinstance(event_name, str) else None
        if handler is not None:
            state_dir = _state_dir(payload.get("cwd", "."))
            result = handler(payload, state_dir)
    except Exception as exc:
        result = {"error": str(exc)}
    try:
        outstream.write(json.dumps(result) + "\n")
        outstream.flush()
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    run()
