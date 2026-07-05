"""
ch28_local_ade_loop.py — Chapter 28: 로컬 자가교정 ADE 구축
====================================================================
Book Chapter 28 — OCOA 스택 (Ollama + ctx + OpenCode + Agent-Evaluator)

이 챕터는 네 조각(Ollama·ctx·OpenCode·LiveGuardrail)의 "배선"을 다룬다.
이 예제 파일이 실제로 실행할 수 있는 것은 그중 **LiveGuardrail(Python SDK)
부분뿐**이다 — Ollama/OpenCode/ctx는 별도로 설치해야 하는 외부 CLI이므로,
그 부분은 §28.7의 검증 경계 표와 동일하게 명확히 "개념 코드(목업)"로 표시한다.

섹션 1: §28.5.3(리팩토링 워크플로우) 저장소 전용 확장 GUARDRAIL_CONFIG — git 안전장치
        (강제 푸시·--no-verify·git reset --hard 차단) + # noqa 은폐 차단 데모.
        이어서 scope_tool_names(SPEC-024) 없이는 edit 호출까지 오탐하는 것과,
        지정 시 오탐이 사라지는 것을 대조(Ch27 §27.6 3차 발견과 동일한 문제)
섹션 2: §28.3/28.4의 다섯 단계 폐루프 재현 — 1~3단계(차단·즉시노출·기록)는
        실제 LiveGuardrail 호출, 4~5단계(색인·검색)는 ctx CLI가 없으므로
        메모리 딕셔너리로 대체한 목업(§28.7 참고)
섹션 3: §28.5.3의 "검증" 단계 — pytest 재통과를 세션 완료 조건으로 강제하는 패턴
섹션 4: §28.5.4(코드 리뷰 워크플로우) 읽기 전용 자가 점검 세션 — ScopeConfig로
        edit/bash를 전부 차단하고 read/grep/glob만 허용하는 패턴
섹션 5: SPEC-024 REQ-2(FTS5 색인)/REQ-3(search_violations())/REQ-5(transcript 힌트) —
        ctx 없이 자체 저장소로 위반을 검색한다. 섹션 2의 "완전 차단"된 git push
        시도는 이 경로로도 검색되지 않음을 재확인하고, fail_on_dangerous=False
        (감지·미차단) 모드의 위반만 실제로 검색됨을 대조(§28.7 4~5단계 재평가).
        summarize_guardrail_result()로 위반이 있을 때만 search_violations
        힌트가 붙는 것도 함께 확인

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch28_local_ade_loop.py

결과:
    results/opencode_live_guardrail/ch28_demo_sessions.db (섹션 5)
"""

from pathlib import Path
from typing import List

from agent_evaluator import create_taskresult
from agent_evaluator.gates.gate_b_behavioral.configs import ScopeConfig, ToolParameterSafetyConfig
from agent_evaluator.gates.live_guardrail import LiveGuardrail
from agent_evaluator.storage.sqlite_backend import save_tasks_to_db, search_violations


def summarize_guardrail_result(session_id: str, extra: dict) -> str:
    """agent-evaluator.ts의 summarizeGuardrailResult()를 Python으로 재현한 것.

    실제 요약 로직의 유일한 소스는 TypeScript 쪽(agent-evaluator.ts)이지만, 그 파일은
    Node/Bun 없이는 실행할 수 없으므로 여기서는 같은 조건 분기를 Python으로 옮겨
    적어 REQ-5(위반이 있을 때만 search_violations 힌트를 붙이는 로직)를 순수 Python
    환경에서도 직접 실행해 확인할 수 있게 한다. Ch27 §27.2의 동명 함수와 동일하다.
    """
    lines = [f"[agent-evaluator] Gate B/E guardrail summary (session {session_id})"]

    tps = extra.get("tool_parameter_safety")
    if tps and tps.get("dangerous_calls"):
        lines.append(f"- dangerous tool parameters: {tps.get('dangerous_calls')}")
    scope = extra.get("scope")
    if scope and scope.get("in_scope") is False:
        lines.append(f"- scope violation: {scope.get('violations')}")

    if len(lines) == 1:
        lines.append("- no violations detected")
    else:
        # SPEC-024 REQ-5 — 위반이 1건 이상 있을 때만 search_violations 힌트를 붙인다.
        lines.append("- 다음 세션에서 유사한 시도를 하기 전에 search_violations 도구로 이 사유를 검색해 확인하라.")
    return "\n".join(lines)


# ===========================================================================
# 섹션 1: §28.5.3(리팩토링 워크플로우) — 저장소 자체 개선 세션 전용 GUARDRAIL_CONFIG
# ===========================================================================
print("\n=== 섹션 1: 저장소 전용 확장 GUARDRAIL_CONFIG ===")


_REPO_DANGEROUS_PATTERNS = [
    r"\.\./", r"&&", r"\|\|", r";.*rm\s", r"__import__", r"eval\(", r"exec\(",
    r"\brm\s+\S",               # Ch27 §27.6 2차 발견 반영 (2026-07-05)
    # 여기부터 저장소 자체 개선 세션 전용 추가 (§28.5.3)
    r"--no-verify",             # 커밋 훅 우회 시도 차단
    r"git\s+push\s+.*--force",  # 강제 푸시 차단
    r"git\s+reset\s+--hard",    # 비가역 리셋 차단
    r"#\s*noqa",                # ruff 위반을 숨기는 처방 차단
]


def make_repo_guardrail() -> LiveGuardrail:
    """§28.5.3 예제와 동일 — Ch27의 rm 대응 패턴(플래그 유무 무관)에 git 안전장치를 추가한다."""
    return LiveGuardrail(
        tool_parameter_safety=ToolParameterSafetyConfig(
            dangerous_patterns=_REPO_DANGEROUS_PATTERNS,
            scope_tool_names=["bash"],  # SPEC-024 REQ-1 — 검사를 셸 호출로만 한정(아래 데모 참고)
            fail_on_dangerous=True,
        ),
        scope=ScopeConfig(
            # §28.5.3의 목표 선언에서 프롬프트로 좁힌 반경을 도구 화이트리스트로도 다시 한번 강제
            # fail_on_violation 기본값은 False이므로 명시하지 않으면 이 화이트리스트는
            # 평가만 되고 실제로는 아무것도 차단하지 않는다 (실측으로 확인된 동작).
            allowed_tools=["read", "edit", "grep", "glob", "bash"],
            fail_on_violation=True,
        ),
    )


repo_guardrail = make_repo_guardrail()

_REPO_ATTEMPTS = [
    ("edit", {"file": "agent_evaluator/gates/gate_d_performance/aggregate.py"}),
    ("bash", {"command": "ruff check agent_evaluator/gates/gate_d_performance/"}),
    ("edit", {"file": "agent_evaluator/gates/gate_d_performance/aggregate.py", "content": "x = 1  # noqa: E501"}),
    ("bash", {"command": "git commit -am 'fix' --no-verify"}),
    ("bash", {"command": "git push origin main --force"}),
]

for tool_name, params in _REPO_ATTEMPTS:
    verdict = repo_guardrail.check_before_tool_call("repo-session-1", tool_name, params)
    if verdict.block:
        print(f"  [{tool_name:<5s}] 차단됨 (Gate {verdict.gate}): {verdict.reason}")
    else:
        print(f"  [{tool_name:<5s}] 통과 — {params}")
        repo_guardrail.record_tool_call("repo-session-1", tool_name, params)

# --- scope_tool_names(SPEC-024) 없이는 edit도 오탐한다 — 이 챕터 자체를 다루는
#     파일(예: 이 예제 파일)을 편집하려 하면, 그 파일 내용에 "git push --force" 같은
#     문자열이 들어있다는 이유만으로 edit 호출까지 차단된다 (Ch27 §27.6 3차 발견과 동일) ---
_edit_this_file = {
    "file": "Evaluator_Examples/ch28_local_ade_loop.py",
    "content": '_REPO_ATTEMPTS = [("bash", {"command": "git push origin main --force"})]',
}
_unscoped_guardrail = LiveGuardrail(
    tool_parameter_safety=ToolParameterSafetyConfig(
        dangerous_patterns=_REPO_DANGEROUS_PATTERNS,
        # scope_tool_names 미지정 → 모든 도구 호출을 검사(수정 전 동작)
        fail_on_dangerous=True,
    ),
)
verdict_edit_before = _unscoped_guardrail.check_before_tool_call("repo-session-1", "edit", _edit_this_file)
print(
    f"  [scope 미지정] 이 파일 자체를 편집(edit) 차단 여부: {verdict_edit_before.block}  "
    f"← 이 콘텐츠에 'git push --force' 문자열이 있어서 오탐"
)

# repo_guardrail(= make_repo_guardrail())은 이미 scope_tool_names=["bash"]가 적용돼 있다.
verdict_edit_after = repo_guardrail.check_before_tool_call("repo-session-1", "edit", _edit_this_file)
print(f"  [scope_tool_names=['bash']] 같은 edit 차단 여부: {verdict_edit_after.block}  ← 더 이상 오탐하지 않는다")
verdict_bash_after = repo_guardrail.check_before_tool_call(
    "repo-session-1", "bash", {"command": "git push origin main --force"},
)
print(f"  [scope_tool_names=['bash']] bash에서 강제 푸시 차단 여부: {verdict_bash_after.block}  ← bash는 그대로 차단된다")

# ===========================================================================
# 섹션 2: §28.3 다섯 단계 폐루프 — 1~3단계 실제 SDK, 4~5단계는 목업(§28.7)
# ===========================================================================
print("\n=== 섹션 2: 다섯 단계 폐루프 (세션 1의 실수를 세션 2가 피한다) ===")


class MockCtxIndex:
    """개념 코드 — 실제 ctx(Rust CLI, https://github.com/ctxrs/ctx)를 대체하는 목업.

    ctx는 로컬 SQLite에 세션 transcript를 색인하고 자연어로 검색하는 별도
    오프라인 CLI이며, 이 저장소는 ctx의 색인 정확도를 검증하지 않았다(§28.7).
    여기서는 "차단 사유가 다음 세션에서 검색 가능해야 한다"는 개념만
    딕셔너리로 흉내낸다 — 실제 배포 시에는 `ctx setup` / `ctx search`로 교체한다.
    """

    def __init__(self) -> None:
        self._events: List[dict] = []

    def index_session(self, session_id: str, transcript_note: str) -> None:
        """실제로는: ctx setup (배치형 명령 — 자동 백그라운드 색인 없음, §28.3 4단계)."""
        self._events.append({"session_id": session_id, "note": transcript_note})

    def search(self, query: str) -> List[dict]:
        """실제로는: ctx search "query" (§28.3 5단계)."""
        return [e for e in self._events if query.lower() in e["note"].lower()]


ctx_index = MockCtxIndex()

# --- 세션 1: 위험한 시도가 차단되고, 그 사실이 세션 transcript에 남는다 ---
session1_guardrail = make_repo_guardrail()
_attempted_command = "git push origin main --force"
verdict1 = session1_guardrail.check_before_tool_call(
    "repo-session-2", "bash", {"command": _attempted_command},
)
print(f"  [세션 1] 차단됨: {verdict1.block}  이유: {verdict1.reason}")

# 1. 차단 (실제 SDK) → 2. 즉시 노출은 OpenCode 훅의 throw로 이뤄지므로 여기서는 로그로 대체
# 3. 기록 — 실제로는 client.session.prompt({noReply: true, ...})로 세션 transcript에 영구 기록(Ch27 §27.5)
#    summarizeGuardrailResult()는 점수만이 아니라 구체적으로 어떤 명령이 막혔는지도 적는다(§27.5) —
#    다음 세션이 "git push" 같은 키워드로 검색할 수 있으려면 원 명령어 텍스트가 요약에 남아야 한다.
#
# ⚠️ 단순화 — 아래 transcript_summary는 verdict1(개별 판정 결과)에서 직접 만든 것이다.
# 실제 OpenCode 플러그인의 summarizeGuardrailResult()는 개별 verdict가 아니라
# session1_guardrail.snapshot()이 반환하는 extra를 입력받는다. 그런데 이 git push
# 시도는 fail_on_dangerous=True로 완전히 차단됐으므로 record_tool_call()이 호출되지
# 않았고(§27.6·§28.7 신규 발견 — 아래 섹션 5에서 직접 재현), snapshot()의
# tool_parameter_safety는 이 시도를 전혀 반영하지 않는다. 즉 이 절이 그리는 "3. 기록"은
# 개념 설명이고, snapshot() 기반의 실제 배치 경로로는 이 특정 위반이 transcript
# 요약에도, 그래서 색인·검색에도 나타나지 않는다 — §28.7 4~5단계 재평가 참고.
transcript_summary = f"blocked by Gate {verdict1.gate}: attempted '{_attempted_command}' — {verdict1.reason}"
# 4. 색인 — 실제로는 `ctx setup` (여기서는 MockCtxIndex로 대체, §28.7 참고)
ctx_index.index_session("repo-session-2", transcript_summary)
print(f"  [색인 완료 — 목업] {transcript_summary}")

# --- 세션 2: 유사한 작업을 다시 시도하기 전에 과거 이력을 검색한다 ---
# 5. 검색·회피 — 실제로는 `ctx search "git push force"` (여기서는 MockCtxIndex.search)
hits = ctx_index.search("git push")
if hits:
    print(f"  [세션 2] 검색 결과 {len(hits)}건 회수 — 과거에 이 시도가 막혔음을 확인:")
    for h in hits:
        print(f"    - {h['note']}")
    print("  → 모델이 같은 우회를 다시 시도할 가능성이 줄어든다 (§28.4)")
else:
    print("  [세션 2] 검색 결과 없음")

# ===========================================================================
# 섹션 3: §28.5.3 — "검증" 단계: pytest 재통과를 완료 조건으로 강제
# ===========================================================================
print("\n=== 섹션 3: 리팩토링 세션의 완료 조건 — pytest 재통과 강제 ===")


def verify_before_declaring_done(pytest_passed: bool) -> str:
    """§28.5.3 — LiveGuardrail은 위험한 시도만 막을 뿐 '고친 코드가 동작을
    보존했다'는 보증은 하지 않는다. 이 검증은 LiveGuardrail이 아니라 개발자가
    세션 워크플로우에 직접 강제하는 규율이다.
    """
    # TODO(현업 적용): 아래를 실제로 `subprocess.run(["pytest", "tests/", "-k", "gate_d"])`
    #   결과의 returncode == 0 여부로 교체하세요. 여기서는 인자로 시뮬레이션합니다.
    if not pytest_passed:
        return "완료 선언 보류 — pytest 실패, 원인을 다시 조사할 것"
    return "완료 조건 충족 — ruff 위반 감소 + pytest 전부 통과 확인됨"


print(f"  시나리오 A (pytest 실패): {verify_before_declaring_done(False)}")
print(f"  시나리오 B (pytest 통과): {verify_before_declaring_done(True)}")

# ===========================================================================
# 섹션 4: §28.5.4(코드 리뷰 워크플로우) — 읽기 전용 자가 점검 세션
# ===========================================================================
print("\n=== 섹션 4: 코드 리뷰 전 읽기 전용 자가 점검 ===")


def make_review_guardrail() -> LiveGuardrail:
    """§28.5.4 예제와 동일 — PR을 올리기 전 자가 점검 세션은 파일을 수정하지
    않아야 한다. allowed_tools에서 edit/bash를 빼고 read/grep/glob만
    남기면, 모델이 점검 중 스스로 "고치는 게 낫겠다"고 판단해도 실제로는
    차단된다.
    """
    return LiveGuardrail(
        scope=ScopeConfig(
            allowed_tools=["read", "grep", "glob"],  # edit·bash는 의도적으로 제외
            fail_on_violation=True,  # 필수 — 없으면 화이트리스트가 차단하지 않는다
        ),
    )


review_guardrail = make_review_guardrail()

_REVIEW_ATTEMPTS = [
    ("grep", {"pattern": "fail_on_violation", "path": "agent_evaluator/gates/"}),
    ("read", {"file": "agent_evaluator/gates/gate_b_behavioral/configs.py"}),
    ("edit", {"file": "agent_evaluator/gates/gate_b_behavioral/configs.py"}),  # 점검 중 실수로 고치려는 시도
]

for tool_name, params in _REVIEW_ATTEMPTS:
    verdict = review_guardrail.check_before_tool_call("review-session-1", tool_name, params)
    if verdict.block:
        print(f"  [{tool_name:<5s}] 차단됨 (Gate {verdict.gate}): {verdict.reason}")
    else:
        print(f"  [{tool_name:<5s}] 통과 — {params}")
        review_guardrail.record_tool_call("review-session-1", tool_name, params)
# → read/grep은 통과하고 edit만 차단된다. 자가 점검 세션이 실제로
#   "읽기 전용"으로 강제됨을 보여준다 (§28.5.4 참고).

# ===========================================================================
# 섹션 5: SPEC-024 REQ-2/3 — ctx 없이 Agent-Evaluator 자체로 위반 검색하기
# (그리고 섹션 2의 "완전 차단" 시나리오는 왜 이 방식으로도 검색되지 않는지)
# ===========================================================================
print("\n=== 섹션 5: 위반 이력 검색 — ctx 대신 search_violations() (SPEC-024) ===")

_ch28_db = (
    Path(__file__).parent.parent / "results" / "opencode_live_guardrail" / "ch28_demo_sessions.db"
)
_ch28_db.parent.mkdir(parents=True, exist_ok=True)

# 5-A. 섹션 2의 git push 시도를 실제 배치 경로(snapshot → save_tasks_to_db)로 저장해 보면,
# 완전히 차단됐기 때문에 아무 위반도 색인되지 않는다 — 위 "⚠️ 단순화" 주석에서 예고한 그대로.
_blocked_extra = session1_guardrail.snapshot()
_tps = _blocked_extra.get("tool_parameter_safety")
print(f"  [세션 1 재확인] snapshot()의 tool_parameter_safety: {_tps}")
_blocked_task = create_taskresult(
    task_id="repo-session-2", question="q", response="r", execution_time=1.0, extra=_blocked_extra,
)
save_tasks_to_db(_ch28_db, [_blocked_task])
_hits_blocked = search_violations(_ch28_db, "git")
print(f"  search_violations(db, 'git') 결과: {len(_hits_blocked)}건  ← 완전 차단된 시도는 검색되지 않는다")

# REQ-5 힌트도 위반이 없으므로 붙지 않는다 — "3. 기록" 절에서 예고한 것과 동일한 결론.
print("  [세션 1 재확인] summarize_guardrail_result():")
for _line in summarize_guardrail_result("repo-session-2", _blocked_extra).splitlines():
    print(f"    {_line}")

# 5-B. 반면 fail_on_dangerous=False(감지만, 차단은 안 함)로 설정하면 실행이 허용되고
# record_tool_call()이 호출되므로, 그 위반이 실제로 색인·검색된다.
monitor_guardrail = LiveGuardrail(
    tool_parameter_safety=ToolParameterSafetyConfig(
        dangerous_patterns=_REPO_DANGEROUS_PATTERNS,
        scope_tool_names=["bash"],
        fail_on_dangerous=False,  # 감지만 하고 차단은 하지 않음
    ),
)
_v = monitor_guardrail.check_before_tool_call(
    "repo-session-3", "bash", {"command": "rm -rf build/"},
)
print(f"  [모니터 모드] rm -rf 차단 여부: {_v.block}  (실행은 허용, 위반은 감지)")
monitor_guardrail.record_tool_call("repo-session-3", "bash", {"command": "rm -rf build/"})

_monitor_extra = monitor_guardrail.snapshot()
monitor_task = create_taskresult(
    task_id="repo-session-3", question="q", response="r", execution_time=1.0, extra=_monitor_extra,
)
save_tasks_to_db(_ch28_db, [monitor_task])
_hits_monitor = search_violations(_ch28_db, "bash")
print(f"  search_violations(db, 'bash') 결과: {len(_hits_monitor)}건")
for r in _hits_monitor:
    print(f"    - task_id={r['task_id']}  summary={r['summary']}")

# REQ-5 힌트 — 이번엔 위반이 있으므로 search_violations 힌트가 붙는다.
print("  [모니터 모드] summarize_guardrail_result():")
for _line in summarize_guardrail_result("repo-session-3", _monitor_extra).splitlines():
    print(f"    {_line}")

print("\n=== 요약 ===")
print("  실제 SDK로 검증된 부분: LiveGuardrail 차단(섹션 1·2·4) — Ch27과 동일한 메커니즘")
print("  실제 SDK로 검증된 부분: search_violations()로 '감지·기록' 위반 검색(섹션 5) — SPEC-024")
print("  목업으로 대체한 부분:   ctx 색인·검색(섹션 2 후반부) — §28.7 검증 경계 참고")
print("  중요한 제약(섹션 5):    완전히 '차단'된 시도는 ctx로도, search_violations()로도 검색되지 않는다")
print("  개발자 워크플로우 규율: pytest 재통과 강제(섹션 3) — LiveGuardrail이 아니라 사람이 강제")
