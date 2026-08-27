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
import re
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
        # 도구 "이름"만 비교하는 연속 반복 임계값. Claude Code CLI는 도구가
        # Bash/Read/Edit/Write 등으로 세분화돼 있어 OpenCode(단일 "bash")보다 오탐
        # 경로가 좁으므로 "fail"(실행 전 차단)을 유지하되, 정상적인 반복 편집·테스트에
        # 여유를 두려고 8로 올렸다. 실제 무한 루프는 대개 "연속 동일 호출"(consecutive)로
        # 나타나므로, 아래 live_loop_blocking_types도 그 타입만 차단하도록 좁혔다.
        "consecutive_repeat_threshold": 8,
        "on_loop_detected": "fail",
    },
    # SPEC-041: 실시간 루프 판정을 최근 N호출로만 한정 — 세션 초반의 일시적 반복
    # 하나가 세션 끝까지 모든 도구 호출을 막는 latch 현상을 없앤다.
    "live_loop_window": 15,
    "scope": {"forbidden_tools": ["WebFetch"], "fail_on_violation": True},
    "tool_parameter_safety": {
        # SPEC-041: `../`(상대 경로)·`&&`·`||`(셸 체이닝)·단일 파일 `rm foo`는 정상 코딩
        # 세션에서 흔하고 그 자체로 파괴적이지 않아 하드-fail 목록에서 뺐다. 남긴 것은
        # 되돌리기 어려운 실제 파괴 명령뿐이다(재귀+강제 삭제 `rm -rf`/`-fr`, 체이닝된
        # rm, mkfs, 디바이스로의 dd, fork bomb, 파이프-투-셸). Gate E 하드코딩 백스톱
        # (tool_authorization)이 sudo/DROP TABLE/chmod 777 등을 여전히 별도로 잡는다.
        "dangerous_patterns": [
            r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f", r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*r",
            r";\s*rm\s+-", r"\bmkfs\b", r"\bdd\s+if=.*of=/dev/",
            r":\(\)\s*\{\s*:\s*\|",
            # 파이프-투-셸: `curl x | sh` 뿐 아니라 임의의 `... | sh|bash|zsh`도 잡는다
            # (생성한 스크립트를 인터프리터에 직접 흘려넣는 실행 패턴). 프로세스 치환으로
            # 셸을 띄우는 `>(sh)` / `<(bash ...)` 도 포함.
            r"\|\s*(sh|bash|zsh|ksh)\b", r"[<>]\(\s*(sh|bash|zsh|ksh)\b",
            r"__import__", r"eval\(", r"exec\(",
        ],
        # dangerous_patterns + 길이 검사(max_argument_length)를 Bash로만 한정한다.
        # Write/Edit는 인자 = 파일 본문이라, 스코프에 넣으면 2KB 넘는 정상 파일
        # 생성·수정이 arg_too_long으로 통째로 차단된다(코드 생성 회귀).
        "scope_tool_names": ["Bash"],
        # scope_tool_names로 Bash만 검사하므로 파일 본문에는 영향이 없지만, 방어적으로
        # 넉넉히 잡아 둔다(기본값 2000은 실시간 경로에 지나치게 작다).
        "max_argument_length": 100000,
        "fail_on_dangerous": True,
    },
    # Gate E 하드코딩 백스톱(ToolAuthorizationTracker) — allowed_tools/restricted_tools를
    # 안 줘도 하드코딩된 위험 패턴(rm -rf/DROP TABLE/sudo/eval(/exec(/chmod 777 등)을 모든
    # 도구 호출 파라미터에서 스캔해 매치 시 차단한다(security.py의 dangerous_patterns,
    # ToolParameterSafetyConfig의 커스터마이즈 가능한 목록과는 별개). 과거엔 이 키가 빠져
    # 있어 AC 기본 설치가 AOO 기본 설치보다 이 백스톱 하나만큼 약했다 — 파악 즉시 정렬.
    "tool_authorization": {},
    # SPEC-041: 서킷 브레이커 — 한 세션에서 연속 N회 차단되면 남은 세션 동안
    # 관찰 전용(allow + systemMessage 경고)으로 전환한다. 지속 차단은 공격보다
    # 오설정일 확률이 압도적이므로, 무기한 락아웃 대신 안전하게 열어 준다.
    # 이 브리지가 SessionEnd/PreToolUse에서 직접 쓰는 값 — build_guardrail() 전에 pop한다.
    # 0 또는 null이면 서킷 브레이커를 끈다.
    "circuit_breaker_after": 5,
    # LiveGuardrail 생성자 인자가 아니라 이 브리지 자체가 SessionEnd에서 쓰는 값 —
    # build_guardrail() 호출 전에 pop()으로 제거한다.
    "output_dir": "results/claude_code_live_guardrail",
}

_STATE_SUBDIR = Path(".claude") / ".agent-evaluator"

# SPEC-041: 서킷 브레이커 기본 임계값 — guardrail_config.json의 "circuit_breaker_after"로
# 덮어쓸 수 있고, 0/null이면 비활성화된다.
_DEFAULT_CIRCUIT_BREAKER_AFTER = 5


def _state_dir(cwd: str) -> Path:
    return Path(cwd or ".") / _STATE_SUBDIR


def _config_path(state_dir: Path) -> Path:
    return state_dir / "guardrail_config.json"


def _safe_session_id(session_id: Any) -> str:
    """세션 ID를 파일명에 안전한 문자로 제한한다 (SPEC-041, 방어적).

    Claude Code는 session_id로 UUID를 넘기지만, 이 값은 훅 스크립트가 그대로
    ``sessions/<id>.json`` 등의 경로에 쓰므로 ``/``·``..``가 들어오면 상태 파일
    쓰기가 프로젝트 밖으로 새어나갈 수 있다. ``[A-Za-z0-9._-]`` 이외는 ``_``로
    치환하고, 앞쪽 점(``.``/``..``)은 제거한다. 빈 값이면 ``"_nosession"``.
    """
    _s = re.sub(r"[^A-Za-z0-9._-]", "_", str(session_id or ""))
    _s = _s.lstrip(".")
    return _s or "_nosession"


def _session_file(state_dir: Path, session_id: str) -> Path:
    return state_dir / "sessions" / f"{_safe_session_id(session_id)}.json"


def _blocked_file(state_dir: Path, session_id: str) -> Path:
    return state_dir / "sessions" / f"{_safe_session_id(session_id)}.blocked.json"


def _circuit_file(state_dir: Path, session_id: str) -> Path:
    return state_dir / "sessions" / f"{_safe_session_id(session_id)}.circuit.json"


def _session_config_file(state_dir: Path, session_id: str) -> Path:
    return state_dir / "sessions" / f"{_safe_session_id(session_id)}.config.json"


def _session_config(state_dir: Path, session_id: str, *, create: bool) -> dict[str, Any]:
    """세션 첫 훅 호출 시점의 guardrail 설정을 세션에 고정한다 (SPEC-041).

    Claude Code 훅은 호출마다 별도 프로세스라, 세션 도중 ``guardrail_config.json``이
    바뀌면 PreToolUse 호출들이 서로 다른 설정으로 판정하고 SessionEnd 배치 리포트도
    세션이 실제로 강제한 것과 다른 설정으로 점수를 낸다. 첫 PreToolUse에서 해석한
    설정을 ``sessions/<id>.config.json``에 스냅숏해 세션 전체(리포트 포함)가 한
    설정을 쓰게 한다.

    Args:
        create: True(PreToolUse)면 스냅숏이 없을 때 만든다. False(SessionEnd)면
            스냅숏이 있으면 읽고, 없으면(그 세션에 PreToolUse가 한 번도 안 온
            경우) 만들지 않고 현재 설정을 그대로 쓴다.
    """
    _pin = _session_config_file(state_dir, session_id)
    try:
        if _pin.exists():
            data = json.loads(_pin.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    resolved = load_config(state_dir)
    if create:
        try:
            _pin.parent.mkdir(parents=True, exist_ok=True)
            _pin.write_text(json.dumps(resolved), encoding="utf-8")
        except OSError:
            pass
    return resolved


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    """세션/차단 이력 파일을 읽는다.

    SPEC-041: 파일 포맷을 JSON 배열에서 **JSON Lines**(한 줄당 dict 하나)로 바꿨다.
    ``_append_json_list``가 매번 전체를 읽어-고쳐-쓰던 read-modify-write를 없애
    (1) 긴 세션의 O(n²) I/O를 O(n)으로 줄이고 (2) 병렬 도구 호출의 PostToolUse가
    동시에 이력에 append해도 레코드가 유실되지 않게 한다(O_APPEND 한 줄 쓰기).
    구버전이 남긴 JSON 배열 파일도 그대로 읽는다(하위 호환).
    """
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return []
    if not text:
        return []
    if text[0] == "[":  # 레거시: 파일 전체가 JSON 배열
        try:
            data = json.loads(text)
            return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # 잘린 줄 등은 건너뛴다
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _append_json_list(path: Path, record: dict[str, Any]) -> None:
    """레코드 한 줄을 JSON Lines로 append한다 (read 없이 O_APPEND 한 번)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


def _config_search_paths(state_dir: Path) -> list[Path]:
    """``guardrail_config.json`` 후보 경로를 우선순위 순으로 만든다 (SPEC-041).

    1. ``<state_dir>/guardrail_config.json`` (= ``<cwd>/.claude/.agent-evaluator/...``)
    2. cwd에서 상위로 거슬러 올라가며 만나는 ``.claude/.agent-evaluator/guardrail_config.json``
       (모노레포 하위 디렉터리에서 세션을 시작한 경우)
    3. ``~/.claude/.agent-evaluator/guardrail_config.json`` (``--global`` 설치 위치)

    과거엔 (1)만 봤기 때문에 ``agent-eval claude install --global``로 홈에 저장한 설정이
    프로젝트-로컬 설정이 없는 cwd에서 조용히 무시되고 :data:`DEFAULT_GUARDRAIL_CONFIG`가
    쓰였다 — 이 함수가 그 간극을 메운다.
    """
    seen: set[Path] = set()
    candidates: list[Path] = []

    def _add(p: Path) -> None:
        if p not in seen:
            seen.add(p)
            candidates.append(p)

    _add(_config_path(state_dir))

    try:
        cwd = state_dir.parent.parent.resolve()
    except (OSError, RuntimeError):
        cwd = None
    if cwd is not None:
        for parent in [cwd, *cwd.parents]:
            _add(parent / _STATE_SUBDIR / "guardrail_config.json")

    try:
        _add(Path.home() / _STATE_SUBDIR / "guardrail_config.json")
    except (OSError, RuntimeError):
        pass

    return candidates


def load_config(state_dir: Path) -> dict[str, Any]:
    """``guardrail_config.json``을 읽는다.

    :func:`_config_search_paths` 순서대로 처음 발견되는 유효한 JSON 객체를 쓰고,
    어디에도 없으면 :data:`DEFAULT_GUARDRAIL_CONFIG`를 그대로 쓴다.
    """
    for path in _config_search_paths(state_dir):
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            return data
    return dict(DEFAULT_GUARDRAIL_CONFIG)


def _replay(guardrail: Any, task_id: str, records: list[dict[str, Any]]) -> None:
    """이전에 확정된 tool_call 이력을 ``record_tool_call()``로 재생해 판정 상태를 복원한다."""
    for record in records:
        guardrail.record_tool_call(
            task_id, record.get("tool_name", ""), record.get("parameters"), record.get("output"),
        )


def _read_circuit_state(path: Path) -> dict[str, Any]:
    """서킷 브레이커 상태 파일을 읽는다.

    Returns:
        ``{"consecutive_blocks": int, "tripped": bool}``. 파일이 없거나 손상됐으면
        ``{"consecutive_blocks": 0, "tripped": False}``.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "consecutive_blocks": int(data.get("consecutive_blocks", 0)),
            "tripped": bool(data.get("tripped", False)),
        }
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return {"consecutive_blocks": 0, "tripped": False}


def _write_circuit_state(path: Path, consecutive_blocks: int, tripped: bool) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"consecutive_blocks": consecutive_blocks, "tripped": tripped}),
            encoding="utf-8",
        )
    except OSError:
        pass


def handle_pre_tool_use(payload: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    session_id = payload["session_id"]
    tool_name = payload["tool_name"]
    tool_input = payload.get("tool_input") or {}

    config = dict(_session_config(state_dir, session_id, create=True))
    config.pop("output_dir", None)
    cb_after = config.pop("circuit_breaker_after", _DEFAULT_CIRCUIT_BREAKER_AFTER)
    try:
        cb_after_int = int(cb_after)
    except (TypeError, ValueError):
        cb_after_int = _DEFAULT_CIRCUIT_BREAKER_AFTER

    circuit_path = _circuit_file(state_dir, session_id)
    circuit = _read_circuit_state(circuit_path)

    guardrail = build_guardrail(config)
    _replay(guardrail, session_id, _load_json_list(_session_file(state_dir, session_id)))

    verdict = guardrail.check_before_tool_call(session_id, tool_name, tool_input)
    if not verdict.block:
        return {
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"},
        }

    # 감사 이력은 서킷 브레이커 상태와 무관하게 항상 남긴다.
    guardrail.record_blocked_attempt(session_id, tool_name, verdict)

    # SPEC-041: 서킷 브레이커가 이미 트립됐으면(sticky, 세션 끝까지) 더 세지 않고
    # 바로 관찰 전용으로 통과시킨다.
    already_tripped = circuit["tripped"]
    consecutive = circuit["consecutive_blocks"] + 1
    tripped = already_tripped or (cb_after_int > 0 and consecutive >= cb_after_int)
    _write_circuit_state(circuit_path, consecutive, tripped)

    _append_json_list(
        _blocked_file(state_dir, session_id),
        {
            "tool_name": tool_name,
            "gate": verdict.gate,
            "reason": verdict.reason,
            "enforced": not tripped,
        },
    )

    if tripped:
        # SPEC-041: 연속 차단이 임계값에 도달 — 남은 세션 동안 관찰 전용으로 전환한다.
        # 지속 차단은 공격보다 오설정일 확률이 압도적이므로, 무기한 락아웃 대신
        # 크게 경고하고 통과시킨다. 위반은 계속 감사 이력에 기록된다(enforced=false).
        # 한 번 트립되면 이후 정상 호출이 성공해도(PostToolUse) 되돌아가지 않는다.
        _msg = (
            f"⚠️ LiveGuardrail circuit breaker tripped — {consecutive} consecutive blocks "
            f"in this session (most recent: {verdict.reason or 'blocked by LiveGuardrail'}). "
            f"Observe-only for the rest of the session: violations are still recorded but no "
            f"longer enforced. This almost always means the guardrail config is miscalibrated "
            f"— edit .claude/.agent-evaluator/guardrail_config.json (or the --global copy at "
            f"~/.claude/.agent-evaluator/guardrail_config.json) and start a new session."
        )
        return {
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"},
            "systemMessage": _msg,
        }

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
        # SPEC-041: Claude Code는 성공 결과에 type="text"(에러는 "error"|"failure")를
        # 보낸다 — 과거 코드는 type=="success"만 성공으로 봐서 *모든* 성공 도구 호출을
        # 실패로 기록했고(Gate G tool_success_rate가 항상 ~0%), stdout을 stderr로 넣었다.
        # 실패 값 목록에 없으면 성공으로 본다("success"도 계속 성공으로 처리 — 하위 호환).
        success = str(result_type).lower() not in ("error", "failure", "cancelled", "canceled")
        output = {"success": success}
        content = tool_result.get("content")
        if isinstance(content, str):
            output["stdout" if success else "stderr"] = content

    _record: dict[str, Any] = {"tool_name": tool_name, "parameters": tool_input, "output": output}
    # SPEC-041: 서브에이전트(Task) tool 호출은 부모와 같은 session_id로 오지만
    # agent_id/agent_type로 구별된다(공식 문서). 있으면 이력에 남겨 리포트에서
    # 메인 스레드와 구분할 수 있게 한다(판정 로직엔 영향 없음).
    _agent_id = payload.get("agent_id")
    if _agent_id:
        _record["agent_id"] = _agent_id
    _append_json_list(_session_file(state_dir, session_id), _record)
    # SPEC-041: 도구가 실제로 실행됐으므로 연속 차단 스트릭을 리셋한다 — 서킷
    # 브레이커는 "쉬지 않고 연달아 막힌" 경우에만 트립해야 한다. 단 이미 트립된
    # 상태(tripped)는 유지한다 — 트립 후 관찰 전용으로 통과한 호출의 PostToolUse가
    # 브레이커를 되돌리면 안 되므로.
    circuit_path = _circuit_file(state_dir, session_id)
    if circuit_path.exists():
        _write_circuit_state(circuit_path, 0, _read_circuit_state(circuit_path)["tripped"])
    return {}


def handle_session_end(payload: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    session_id = payload["session_id"]
    session_file = _session_file(state_dir, session_id)
    blocked_file = _blocked_file(state_dir, session_id)
    result: dict[str, Any] = {"ok": False}
    try:
        config = dict(_session_config(state_dir, session_id, create=False))
        output_dir = config.pop("output_dir", "results/claude_code_live_guardrail")
        config.pop("circuit_breaker_after", None)  # 브리지 전용 키 — LiveGuardrail 인자 아님

        guardrail = build_guardrail(config)
        _replay(guardrail, session_id, _load_json_list(session_file))
        for blocked in _load_json_list(blocked_file):
            guardrail.record_blocked_attempt(
                session_id, blocked.get("tool_name", ""),
                LiveVerdict(block=True, gate=blocked.get("gate"), reason=blocked.get("reason")),
            )
        result = record_and_save({
            "task_id": session_id,
            "extra": guardrail.to_task_extra(),
            "output_dir": output_dir,
            "save_filename": "claude_code_sessions",
            "question": "<claude code session>",
            "response": f"<claude code session: {payload.get('reason', 'unknown')}>",
        })
    except Exception as exc:
        # SPEC-041: 배치 저장이 실패해도(권한·sqlite 락 등) 세션 상태 파일은 반드시
        # 정리한다 — 안 그러면 sessions/ 에 고아 파일이 세션마다 쌓인다.
        result = {"ok": False, "error": str(exc)}
    finally:
        session_file.unlink(missing_ok=True)
        blocked_file.unlink(missing_ok=True)
        _circuit_file(state_dir, session_id).unlink(missing_ok=True)
        _session_config_file(state_dir, session_id).unlink(missing_ok=True)
    return result


_HANDLERS = {
    "PreToolUse": handle_pre_tool_use,
    "PostToolUse": handle_post_tool_use,
    "SessionEnd": handle_session_end,
}


def run(
    instream: TextIO = sys.stdin,
    outstream: TextIO = sys.stdout,
    errstream: TextIO | None = None,
) -> int:
    """stdin에서 훅 payload 하나를 읽고 stdout에 결과 JSON 한 줄을 쓴다.

    예외는 절대 올리지 않는다 — fail-open(모듈 docstring 참고). 알 수 없는
    ``hook_event_name``(async/display 전용 훅 등)은 조용히 빈 결과를 반환한다.

    Returns:
        프로세스 종료 코드. PreToolUse deny면 2(+ 사유를 stderr로) — 최신 Claude
        Code는 ``hookSpecificOutput.permissionDecision`` JSON으로 차단을 읽지만,
        구버전·다른 하네스는 exit 2 + stderr 만 이해할 수 있어 둘 다 낸다(SPEC-041).
        그 외에는 0.
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

    _hso = result.get("hookSpecificOutput") if isinstance(result, dict) else None
    if isinstance(_hso, dict) and _hso.get("permissionDecision") == "deny":
        _reason = _hso.get("permissionDecisionReason") or "blocked by LiveGuardrail"
        try:
            (errstream or sys.stderr).write(str(_reason) + "\n")
            (errstream or sys.stderr).flush()
        except (BrokenPipeError, ValueError):
            pass
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(run())
