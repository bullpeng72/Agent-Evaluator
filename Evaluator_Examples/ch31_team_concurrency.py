"""
ch31_team_concurrency.py — Chapter 31: 팀 동시작업 리스크 제어
====================================================================
Book Chapter 31 — 팀 동시작업 리스크 제어: 스코프 충돌과 브랜치 실수 자동 차단

여러 개발자가 각자 로컬에서 AOO 세션을 동시에 돌릴 때 생기는 "모듈 동의 없는
수정"·"같은 파일 동시 편집" 문제, 그리고 보호 브랜치에서의 실수를 두 계층으로
예방한다 — 세션 시작 *전* 사람이 수동으로 확인하는 클레임 로그와, 세션 *도중*
LiveGuardrail이 자동으로 차단하는 TeamConcurrencyConfig/BranchGuardConfig.
실제 저장소를 오염시키지 않도록 임시 클레임 로그 경로를 쓴다.

섹션 1: §31.2 클레임 로그 인프라 — check_scope_claim()/append_claim()으로
        세션 시작 전 스코프 겹침을 수동 확인(개발자 B 겹침 감지 → 개발자 C 통과
        → 개발자 A 해제 후 재확인)
섹션 2: §31.3 TeamConcurrencyConfig — 세션이 "시작된 뒤"의 read/edit/write 호출도
        자동으로 검사한다(bash는 자유 형식 명령이라 경로 파싱이 불가능해 제외).
        차단된 시도는 record_blocked_attempt()로 감사 이력에 남긴다(SPEC-030)
섹션 3: §31.4 BranchGuardConfig — 보호 브랜치에서의 git commit/push를 실행 전
        자동 차단. 브랜치는 이 저장소의 실제 현재 브랜치를 그대로 쓴다

check_scope_claim()/append_claim()/TeamConcurrencyConfig는 SPEC-032가
agent_evaluator.gates.team_concurrency로 승격한 SDK 함수다(예제 전용 코드가
아니다). §31.5의 `agent-eval claims audit` CI 감사는 같은 모듈의
audit_claims()를 감싼 CLI이며, 이 파일은 다루지 않는다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch31_team_concurrency.py

결과:
    /tmp(스크래치)/aoo_claims_demo.jsonl — 실제 저장소를 오염시키지 않도록 임시 경로 사용
"""

import tempfile
from pathlib import Path

from agent_evaluator.gates.branch_guard import BranchGuardConfig
from agent_evaluator.gates.live_guardrail import LiveGuardrail
from agent_evaluator.gates.team_concurrency import (
    TeamConcurrencyConfig,
    append_claim,
    check_scope_claim,
)

# ===========================================================================
# 섹션 1: §31.2 클레임 로그 인프라 — 세션 시작 전 수동 확인
# 실전에서는 .aoo/claims.jsonl을 프로젝트 저장소에 그대로 커밋해 팀과 공유한다.
# ===========================================================================
print("\n=== 섹션 1: 클레임 로그로 세션 시작 전 스코프 겹침 확인 (§31.2) ===")

_claims_path = Path(tempfile.gettempdir()) / "aoo_claims_demo.jsonl"
_claims_path.write_text("", encoding="utf-8")  # 데모를 매번 깨끗한 상태에서 시작

# 개발자 A가 gate_d_performance/를 클레임하고 세션을 시작한다.
append_claim(
    _claims_path,
    claim_id="c-demo-01", developer="sungwoo",
    scope=["agent_evaluator/gates/gate_d_performance/"],
    branch="feat/gate-d-cache", started_at="2026-07-08T09:00:00+09:00", status="active",
)

# 개발자 B가 같은 스코프에서 세션을 시작하려 한다 — 클레임 확인이 겹침을 잡아낸다.
_conflicts_b = check_scope_claim(["agent_evaluator/gates/gate_d_performance/"], _claims_path)
print(f"  [개발자 B 시도] 겹치는 활성 클레임: {len(_conflicts_b)}건")
for _c in _conflicts_b:
    print(f"    - claim_id={_c['claim_id']}  developer={_c['developer']}  scope={_c['scope']}")
print("    → 이 스코프는 이미 다른 세션이 작업 중이므로 시작을 보류하고 담당자와 조율한다.")

# 개발자 C는 겹치지 않는 다른 스코프를 클레임하려 하므로 문제없이 시작할 수 있다.
_conflicts_c = check_scope_claim(["agent_evaluator/gates/gate_e_security/"], _claims_path)
print(f"  [개발자 C 시도] 겹치는 활성 클레임: {len(_conflicts_c)}건 → 시작 가능")

# 개발자 A가 세션을 마치고 클레임을 해제한다 — 이후에는 같은 스코프도 겹침이 없다.
append_claim(
    _claims_path, claim_id="c-demo-01", status="released", released_at="2026-07-08T10:30:00+09:00",
)
_conflicts_after_release = check_scope_claim(
    ["agent_evaluator/gates/gate_d_performance/"], _claims_path,
)
_n_after_release = len(_conflicts_after_release)
print(f"  [클레임 해제 후 재확인] 겹치는 활성 클레임: {_n_after_release}건 → 이제 시작 가능")

# ===========================================================================
# 섹션 2: §31.3 TeamConcurrencyConfig — 세션 도중 자동 검사
# 위는 세션을 "시작하기 전"의 수동 확인이다 — TeamConcurrencyConfig는 세션이
# "시작된 뒤"의 read/edit/write 호출도 자동으로 검사한다. 개발자 A의 클레임을
# 다시 열어 이 두 번째 안전망을 시연한다.
# ===========================================================================
print("\n=== 섹션 2: TeamConcurrencyConfig — 세션 도중 자동 차단 (§31.3) ===")

append_claim(
    _claims_path,
    claim_id="c-demo-02", developer="sungwoo",
    scope=["agent_evaluator/gates/gate_d_performance/"],
    branch="feat/gate-d-cache-2", started_at="2026-07-08T11:00:00+09:00", status="active",
)
team_guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(claims_path=str(_claims_path)))

_v_edit_conflict = team_guardrail.check_before_tool_call(
    "session-team-demo", "edit", {"file": "agent_evaluator/gates/gate_d_performance/aggregate.py"},
)
print(f"  [edit, 겹치는 클레임] 자동 차단 여부: {_v_edit_conflict.block}  이유: {_v_edit_conflict.reason}")
if _v_edit_conflict.block:
    # SPEC-030 — 완전히 차단된 시도도 감사 이력(blocked_violations)에 명시적으로 남긴다.
    team_guardrail.record_blocked_attempt("session-team-demo", "edit", _v_edit_conflict)

# bash는 scoped_tool_names 기본값(read/edit/write)에 없어 같은 경로를 건드려도 이 자동
# 검사로는 잡히지 않는다 — 자유 형식 명령의 경로 파싱이 불가능하다는 의도된 제약이다.
_v_bash_same_path = team_guardrail.check_before_tool_call(
    "session-team-demo", "bash", {"command": "rm -rf agent_evaluator/gates/gate_d_performance/"},
)
print(f"  [bash, 검사 대상 아님] 자동 차단 여부: {_v_bash_same_path.block}  (team_concurrency는 건드리지 않음)")

# 클레임을 정리해 다음 실행에서 데모가 깨끗한 상태로 시작하게 한다.
append_claim(_claims_path, claim_id="c-demo-02", status="released")

# ===========================================================================
# 섹션 3: §31.4 BranchGuardConfig — 보호 브랜치에서의 git commit/push 자동 차단
# 브랜치는 monkeypatch 없이 이 저장소의 실제 현재 브랜치를 그대로 쓴다 —
# require_branch_prefix="feature/"를 주면, 이 스크립트를 어떤 브랜치에서 실행하든
# (그 접두어와 일치하지 않는 한) 보호 대상이 되는 것을 그대로 보여준다.
# ===========================================================================
print("\n=== 섹션 3: BranchGuardConfig — 보호 브랜치 git 변경 자동 차단 (§31.4) ===")

branch_guardrail = LiveGuardrail(
    branch_guard=BranchGuardConfig(require_branch_prefix="feature/"),
)
print(f"  [branch_guard] 캐싱된 현재 브랜치: {branch_guardrail._current_branch}")
_v_branch_commit = branch_guardrail.check_before_tool_call(
    "session-branch", "bash", {"command": "git commit -m 'AI 세션 커밋'"},
)
print(f"  [git commit, feature/ 접두어 불일치] 차단 여부: {_v_branch_commit.block}  이유: {_v_branch_commit.reason}")

# git과 무관한 명령은 같은 브랜치에서도 그대로 통과한다.
_v_branch_pytest = branch_guardrail.check_before_tool_call(
    "session-branch", "bash", {"command": "pytest tests/"},
)
print(f"  [git과 무관한 명령] 차단 여부: {_v_branch_pytest.block}")

print("\n결과 저장 완료:", _claims_path)
print("확인: agent-eval claims audit --ttl-hours 8  (§31.5 — CI에서 TTL 초과·겹치는 클레임 감사)")
