"""
ch22_tool_guard_realtime.py — Chapter 22: tool_guard 데코레이터로 비침습적 실시간 제어
====================================================================
Book Chapter 22 — 보안 관련 실시간 제어: 실행 전에 막는 마지막 방어선

`tool_guard` 데코레이터(`agent_evaluator.gates.live_guardrail`)를 시연한다.
`check_before_tool_call()`/`record_tool_call()`을 직접 호출하는 저수준 패턴과 달리,
기존 도구 함수를 전혀 고치지 않고 데코레이터 한 줄로 실행 전 차단·실행 후 기록을
자동화한다. (SPEC-041에서 여러 라운드의 오탐 제거·성능·설치 라이프사이클 하드닝을 거쳤다.)

섹션 1: §22.4 — @tool_guard + live_guardrail_session() 기본 사용. 정상 호출은
        통과·기록되고, 위험한 호출은 GuardrailBlockedError 예외로 드러난다
섹션 2: §22.4 — fail_closed 기본값(fail-open)과 명시적 fail_closed=True의 차이.
        활성 세션 밖에서 호출하면 기본값은 경고만 내고 원본 함수를 그대로
        실행하지만, fail_closed=True는 RuntimeError로 확실히 막는다
섹션 3: §22.4 — capture_output으로 실행 결과(exit_code/stdout)를 Gate G에 반영
섹션 4: §22.4 — async 도구 함수도 동일한 데코레이터로 지원됨을 확인
섹션 5: §22.6 — protected_write_paths로 파일 *위치*(민감 경로) 기반 차단
섹션 6: §22.7 — audit_blocked=True로 완전 차단 이력을 감사 저장소에 남기고,
        세션 종료 시 SQLite 배치 리포트에 편입해 search_violations(include_blocked=True)로
        인시던트 대응 자료로 검색한다

Python이 아닌 런타임(OpenCode/Claude Code 등)과의 연결(stdio 브리지)은 §22.5를
참고하라 — 이 파일은 순수 Python 도구 함수에 데코레이터를 붙이는 패턴만 다룬다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch22_tool_guard_realtime.py

결과:
    results/ch22_tool_guard_realtime.db (섹션 6 — 감사 이력)
    results/ch22_tool_guard_realtime.json + .html (섹션 7 — Harness Gate A–G 리포트)
"""

import asyncio
import subprocess
from pathlib import Path

from agent_evaluator import PerformanceMonitor, create_taskresult, setup_otel
from agent_evaluator.gates.gate_b_behavioral.configs import ScopeConfig, ToolParameterSafetyConfig
from agent_evaluator.gates.live_guardrail import (
    GuardrailBlockedError,
    LiveGuardrail,
    live_guardrail_session,
    tool_guard,
)
from agent_evaluator.storage.sqlite_backend import save_tasks_to_db, search_violations

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR = _PROJECT_ROOT / "results"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _OUTPUT_DIR / "ch22_tool_guard_realtime.db"

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    import socket

    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch22-tool-guard-realtime")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ===========================================================================
# 섹션 1: 기본 사용 — 기존 함수를 전혀 고치지 않고 데코레이터만 붙인다
# ===========================================================================
print("\n=== 섹션 1: @tool_guard 기본 사용 ===")

# LiveGuardrail은 세션(에이전트 루프 1회 실행)마다 새 인스턴스를 만들어야 한다 —
# 내부 상태(_tool_calls)에 락이 없어, 여러 세션이 하나의 인스턴스를 공유하면
# 서로 다른 세션의 tool_calls 이력이 섞여 판정이 오염된다(소스 docstring 명시).
# 아래 세 세션(session-1/2/3)이 각자 독립된 인스턴스를 쓰도록 팩토리 함수로 만든다.
def _new_guardrail() -> LiveGuardrail:
    return LiveGuardrail(
        scope=ScopeConfig(forbidden_tools=["webfetch"], fail_on_violation=True),
        tool_parameter_safety=ToolParameterSafetyConfig(
            # SPEC-041 기준 — `../`·`&&`·`||`·단일 파일 `rm foo`는 정상 코딩 세션에서
            # 흔해 기본 목록에서 뺐다. 되돌리기 어려운 실제 파괴 명령만 남긴다.
            dangerous_patterns=[
                r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f", r";\s*rm\s+-",
                r"\bmkfs\b", r"\bdd\s+if=.*of=/dev/", r"\|\s*(sh|bash|zsh|ksh)\b",
                r"__import__", r"eval\(", r"exec\(",
            ],
            scope_tool_names=["bash"],
            fail_on_dangerous=True,
        ),
    )


guardrail = _new_guardrail()


@tool_guard(audit_blocked=True, fail_closed=True)
def bash(command: str) -> subprocess.CompletedProcess:
    # 이 함수는 LiveGuardrail을 전혀 모른다 — 원래 있던 구현 그대로다.
    return subprocess.run(command, shell=True, capture_output=True, text=True)


with live_guardrail_session(guardrail, task_id="session-1"):
    result = bash(command="echo ok")   # 통과 → 자동 실행 + 기록
    print(f"  [echo ok] 통과 — stdout={result.stdout.strip()!r}")

    try:
        bash(command="rm -rf /")
    except GuardrailBlockedError as e:
        print(f"  [rm -rf /] 차단됨 (Gate {e.verdict.gate}): {e.verdict.reason}")

# ===========================================================================
# 섹션 2: fail_closed — 활성 세션이 없을 때의 동작 차이
# ===========================================================================
print("\n=== 섹션 2: fail_closed — 세션 밖에서 호출했을 때 ===")


@tool_guard()  # fail_closed 기본값 False — fail-open
def read_file_open(path: str) -> str:
    return f"(파일 내용 시뮬레이션: {path})"


@tool_guard(fail_closed=True)  # 명시적으로 fail-closed
def read_file_closed(path: str) -> str:
    return f"(파일 내용 시뮬레이션: {path})"


import warnings  # noqa: E402

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    _out = read_file_open("config.yaml")  # 세션 없이 호출 — 경고만 내고 그대로 실행
print(f"  [fail_closed=False, 세션 없음] 실행됨: {_out!r}  경고 {len(caught)}건 발생")

try:
    read_file_closed("config.yaml")  # 세션 없이 호출 — RuntimeError
except RuntimeError as e:
    print(f"  [fail_closed=True, 세션 없음] RuntimeError: {str(e)[:60]}...")

# ===========================================================================
# 섹션 3: capture_output — 실행 결과를 Gate G(ToolCallAnalyzer)에 반영
# ===========================================================================
print("\n=== 섹션 3: capture_output으로 실행 결과 반영 ===")


def _capture(result: subprocess.CompletedProcess) -> dict:
    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": result.stdout,
    }


@tool_guard(fail_closed=True, capture_output=_capture)
def bash_captured(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(command, shell=True, capture_output=True, text=True)


guardrail_s2 = _new_guardrail()  # 세션마다 새 인스턴스 — session-1의 tool_calls와 섞이지 않는다
with live_guardrail_session(guardrail_s2, task_id="session-2"):
    bash_captured(command="pytest --version")   # 성공 시뮬레이션
    bash_captured(command="exit 1")             # 실패 시뮬레이션

session2_extra = guardrail_s2.snapshot()
_tool_calls = session2_extra.get("tool_calls", [])
print(f"  session-2 확정 tool_calls: {len(_tool_calls)}건")
for tc in _tool_calls:
    print(f"    - {tc.get('name')}: success={tc.get('success', '(신호 없음)')}")

# ===========================================================================
# 섹션 4: async 도구 함수도 동일한 데코레이터로 지원된다
# ===========================================================================
print("\n=== 섹션 4: async 도구 지원 ===")


@tool_guard(fail_closed=True)
async def async_search(query: str) -> str:
    await asyncio.sleep(0)  # 실제로는 비동기 I/O
    return f"(검색 결과 시뮬레이션: {query})"


guardrail_s3 = _new_guardrail()  # 세션마다 새 인스턴스 — 섹션 7에서도 재사용


async def _run_async_demo() -> None:
    with live_guardrail_session(guardrail_s3, task_id="session-3"):
        out = await async_search("최근 배포 이력")
        print(f"  [async_search] 통과 — {out!r}")


asyncio.run(_run_async_demo())

# ===========================================================================
# 섹션 5: protected_write_paths — 명령의 *내용*이 아니라 쓰기 *대상*을 본다
# ===========================================================================
# SPEC-041: dangerous_patterns가 명령 문자열을 보는 블랙리스트라면,
# protected_write_paths는 파일 *위치*를 본다 — ~/.ssh, 셸 rc 파일, /etc, 크론,
# LaunchAgents 등 민감 경로에 쓰는 시도를 도구·내용과 무관하게 Gate E로 막는다.
# Write/Edit는 파라미터 키(file_path 등)에서, 순수 셸 쓰기는 `> TARGET`/`tee TARGET`을
# 파싱해 대상을 추출한다. 인자를 *생략*하면 내장 기본 regex 목록이 켜지고,
# None 또는 []을 명시하면 이 검사를 끈다. 커스텀 리스트는 기본값을 완전히 대체한다.
print("\n=== 섹션 5: 파일 위치 기반 차단 (protected_write_paths) ===")

path_guardrail = LiveGuardrail()   # protected_write_paths 생략 = 내장 기본 목록 활성


@tool_guard(tool_name="bash", audit_blocked=True, fail_closed=True)
def bash_write(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(command, shell=True, capture_output=True, text=True)


with live_guardrail_session(path_guardrail, task_id="session-5"):
    # 내용은 완전히 무해하지만("export PATH=...") 대상이 ~/.zshrc라 차단된다.
    try:
        bash_write(command='echo "export PATH=$PATH:/opt/bin" >> ~/.zshrc')
    except GuardrailBlockedError as e:
        print(f"  [>> ~/.zshrc] 차단됨 (Gate {e.verdict.gate}): {e.verdict.reason}")
    # 프로젝트 안 일반 파일로의 쓰기는 통과한다.
    ok = bash_write(command='echo "build ok" > build.log')
    print(f"  [> build.log] 통과 — exit={ok.returncode}")

# ===========================================================================
# 섹션 6: audit_blocked — 완전 차단 이력을 인시던트 대응 자료로 남기기
# ===========================================================================
print("\n=== 섹션 6: 차단 이력 감사 (audit_blocked=True) ===")

audit_guardrail = LiveGuardrail(
    tool_parameter_safety=ToolParameterSafetyConfig(
        dangerous_patterns=[
            r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f", r";\s*rm\s+-",
            r"\bmkfs\b", r"\bdd\s+if=.*of=/dev/", r"\|\s*(sh|bash|zsh|ksh)\b",
            r"__import__", r"eval\(", r"exec\(",
        ],
        scope_tool_names=["bash"],
        fail_on_dangerous=True,
    ),
)


@tool_guard(tool_name="bash", audit_blocked=True, fail_closed=True)
def bash_audited(command: str) -> subprocess.CompletedProcess:
    # tool_name="bash"를 명시해야 scope_tool_names=["bash"]와 일치한다 — 생략하면
    # 함수 이름("bash_audited")이 도구 이름으로 쓰여 dangerous_patterns 검사 대상에서
    # 벗어난다. scope_tool_names 매칭은 SPEC-041에서 대소문자 무시로 바뀌었지만
    # (OpenCode "bash" ↔ Claude "Bash"), 이름 자체가 다르면 여전히 안 맞는다.
    return subprocess.run(command, shell=True, capture_output=True, text=True)


with live_guardrail_session(audit_guardrail, task_id="session-4"):
    try:
        bash_audited(command="rm -rf important_data/")
    except GuardrailBlockedError:
        print("  [rm -rf important_data/] 차단됨 — 감사 이력에 자동 기록됨 (audit_blocked=True)")

# 세션 종료 시 결과를 TaskResult 객체로 패키징하여 DB에 영속화(§22.6).
session4_task = create_taskresult(
    task_id="session-4",
    question="오래된 데이터 정리해줘",
    response="system command attempted",
    execution_time=0.4,
    task_type="tool_use",
    extra=audit_guardrail.snapshot(),
)
save_tasks_to_db(_DB_PATH, [session4_task])
print(f"  저장 완료: {_DB_PATH}")

# 인시던트 대응 — 이 패턴이 과거에도 시도된 적 있는지 확인(완전 차단 이력 포함).
results = search_violations(_DB_PATH, "dangerous", include_blocked=True)
print(f"  search_violations(..., include_blocked=True) 결과 {len(results)}건:")
for r in results:
    print(f"    - task_id={r['task_id']}  blocked={r['blocked']}  summary={r['summary']}")

# ===========================================================================
# 섹션 7: 배치 리포트 편입 — SQLite 감사 이력과 별개로, 5개 세션을 하나의
# PerformanceMonitor에 모아 표준 Harness Gate A–G JSON+HTML 리포트도 남긴다.
# ``live_guardrail_report.py``(OpenCode/Claude 브리지)와 동일한 규칙 —
# snapshot()의 "tool_calls" 키는 다른 파생 지표(loop_detection 등)와
# 달리 TaskResult.extra가 아니라 최상위 TaskResult.tool_calls로 옮겨야
# Gate G(ToolCallAnalyzer)가 실제 도구 사용 데이터를 읽는다.
# ===========================================================================
print("\n=== 섹션 7: 배치 리포트 편입 (JSON + HTML) ===")

report_monitor = PerformanceMonitor(output_dir=str(_OUTPUT_DIR))
for session_id, session_guardrail, session_response in [
    ("session-1", guardrail, "echo ok 통과 + rm -rf / 차단 시연"),
    ("session-2", guardrail_s2, "capture_output으로 실행 결과(exit_code/stdout) 반영 시연"),
    ("session-3", guardrail_s3, "async 도구 함수 지원 시연"),
    ("session-5", path_guardrail, "protected_write_paths — ~/.zshrc 쓰기 차단 시연"),
    ("session-4", audit_guardrail, "audit_blocked=True 감사 이력 시연"),
]:
    session_extra = dict(session_guardrail.snapshot())
    session_tool_calls = session_extra.pop("tool_calls", [])
    report_monitor.record_task(create_taskresult(
        task_id=session_id,
        question=session_response,
        response="tool_guard 데코레이터 세션 완료",
        execution_time=0.4,
        task_type="tool_use",
        tool_calls=session_tool_calls,
        extra=session_extra,
    ))
report_json = report_monitor.save_to_file("ch22_tool_guard_realtime")
print(f"  저장 완료: {report_json} (+ .html)")

print("\n결과 저장 완료:", _DB_PATH, "+ results/ch22_tool_guard_realtime.json/.html")
print("확인: agent-eval dashboard results/")
