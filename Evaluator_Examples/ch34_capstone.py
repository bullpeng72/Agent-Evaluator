"""
ch34_capstone.py — Chapter 34: 3인 팀 캡스톤 — Spec부터 CI까지
====================================================================
Book Chapter 34 — 온보딩·기업 확장·실전 캡스톤 §34.4

§34.4의 3인 팀 시나리오(정민=분석가, 수아=개발자 A, 태호=개발자 B)를 Phase 1~7
그대로 실행 가능한 코드로 재현한다. "Gate F(다중 에이전트 협업)의
ConflictResolutionConfig에 새 옵션 하나를 추가한다"는 연습용 기능을 두 개발자가
스코프를 나눠 동시에 작업하는 과정을 다룬다.

섹션(Phase) 1: 세션 목표 템플릿 — 수아/태호의 "금지" 스코프를 미리 분리(§29.3 방법)
섹션(Phase) 2: 스코프 선언 — check_scope_claim() 사전 확인 → append_claim() (§31.2)
섹션(Phase) 3: 수아의 Tier 2 세션 — ScopeConfig·ToolParameterSafetyConfig·
        TeamConcurrencyConfig(owner="수아")·BranchGuardConfig를 모두 쌓은
        LiveGuardrail. 자기 파일 편집(v1)은 통과·확정 기록, 태호 파일 오침범(v2)과
        전용 브랜치 밖 커밋(v3)은 차단 + record_blocked_attempt()로 감사 이력에 남김
섹션(Phase) 4: 배치 품질 평가 — snapshot()을 PerformanceMonitor에 기록해 Gate A/B 확인
섹션(Phase) 5: PR 제출 — scripts/generate_pr_summary.py로 PR 본문 생성(§33.3 재사용)
섹션(Phase) 6: CI 게이팅 — audit_claims()로 클레임 로그 감사(§31.5)
섹션(Phase) 7: 클레임 해제 — 병합 후 두 클레임 모두 released로 전환

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch34_capstone.py

결과:
    results/capstone_ch34/capstone_claims.jsonl (Phase 2·6·7 — 스크래치 클레임 로그,
        .aoo/claims.jsonl 실제 저장소를 오염시키지 않도록 별도 경로 사용)
    results/capstone_ch34/capstone_sessions.db (Phase 4 — search_violations() 색인)
    results/capstone_ch34/capstone_result.json (+ .html) (Phase 4)
    results/capstone_ch34/pr_body.md (Phase 5)
"""

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.gates.branch_guard import BranchGuardConfig
from agent_evaluator.gates.gate_b_behavioral.configs import ScopeConfig, ToolParameterSafetyConfig
from agent_evaluator.gates.live_guardrail import (
    GuardrailBlockedError,
    LiveGuardrail,
    live_guardrail_session,
    tool_guard,
)
from agent_evaluator.gates.team_concurrency import (
    TeamConcurrencyConfig,
    append_claim,
    audit_claims,
    check_scope_claim,
)
from agent_evaluator.storage.sqlite_backend import save_tasks_to_db

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR = _PROJECT_ROOT / "results" / "capstone_ch34"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_CLAIMS_PATH = _OUTPUT_DIR / "capstone_claims.jsonl"
_DB_PATH = _OUTPUT_DIR / "capstone_sessions.db"
_CLAIMS_PATH.write_text("", encoding="utf-8")  # 데모를 매번 깨끗한 상태에서 시작

# ===========================================================================
# Phase 1: Spec 작성 (정민, 분석가 세션) — §29.3 세션 목표 템플릿 두 개만 발췌
# ===========================================================================
print("\n=== Phase 1: Spec 작성 (정민) — 수아/태호 세션 목표 분리 ===")

SUAH_GOAL = """[수아 세션 목표]
목표: ConflictResolutionConfig에 새 옵션을 추가하고 관련 dataclass 필드를 정의한다.
완료 조건: 1) 기존 pytest 통과  2) 새 필드에 대한 기본값·타입 검증
금지: agent_evaluator/gates/gate_f_multiagent/configs.py 밖의 파일"""

TAEHO_GOAL = """[태호 세션 목표]
목표: 새 옵션을 실제로 사용하는 eval_conflict_resolution() 로직을 구현한다.
완료 조건: 1) 기존 pytest 통과  2) 새 옵션 값에 따른 분기 테스트 3건
금지: agent_evaluator/gates/gate_f_multiagent/evaluators.py 밖의 파일"""

print(SUAH_GOAL)
print()
print(TAEHO_GOAL)

# ===========================================================================
# Phase 2: 스코프 선언 (수아, 태호) — §31.2 순서 그대로: 확인 먼저, 겹치지 않을 때만 클레임
# 실전이라면 started_at은 실제 세션 시작 시각을 쓴다 — 이 데모는 §34.4 Phase 6의
# TTL 감사가 "위반 없음"을 재현하도록 매 실행 시점 기준 현재 시각을 쓴다.
# ===========================================================================
print("\n=== Phase 2: 스코프 선언 (수아, 태호) ===")

_now = datetime.now(timezone.utc).astimezone()

conflicts_suah = check_scope_claim(
    ["agent_evaluator/gates/gate_f_multiagent/configs.py"], str(_CLAIMS_PATH),
)
print(f"  [수아 시작 전 확인] 겹치는 활성 클레임: {len(conflicts_suah)}건 → 시작해도 좋다")
append_claim(
    str(_CLAIMS_PATH), claim_id="c-suah-01", developer="수아",
    scope=["agent_evaluator/gates/gate_f_multiagent/configs.py"],
    started_at=_now.isoformat(), status="active",
)

conflicts_taeho = check_scope_claim(
    ["agent_evaluator/gates/gate_f_multiagent/evaluators.py"], str(_CLAIMS_PATH),
)
print(f"  [태호 시작 전 확인] 겹치는 활성 클레임: {len(conflicts_taeho)}건 → 수아의 configs.py와 겹치지 않으므로 시작 가능")
append_claim(
    str(_CLAIMS_PATH), claim_id="c-taeho-01", developer="태호",
    scope=["agent_evaluator/gates/gate_f_multiagent/evaluators.py"],
    started_at=(_now + timedelta(minutes=5)).isoformat(), status="active",
)

# ===========================================================================
# Phase 3: 수아의 Tier 2 세션 — Part VII가 다룬 4개 Config를 전부 쌓은 LiveGuardrail
# ===========================================================================
print("\n=== Phase 3: 수아의 Tier 2 세션 (LiveGuardrail 안전 루프) ===")

guardrail = LiveGuardrail(
    scope=ScopeConfig(allowed_tools=["read", "edit", "bash"], fail_on_violation=True),
    tool_parameter_safety=ToolParameterSafetyConfig(
        dangerous_patterns=[r"\brm\s+\S", r"&&", r"\|\|"],
        scope_tool_names=["bash"], fail_on_dangerous=True,
    ),
    # owner="수아" — 없으면 자기 자신이 방금 건 클레임조차 충돌로 본다(SPEC-036,
    # 이 캡스톤이 실제로 처음 발견한 문제). 실전에서는 owner="auto"(SPEC-037)를 권장.
    team_concurrency=TeamConcurrencyConfig(claims_path=str(_CLAIMS_PATH), owner="수아"),
    branch_guard=BranchGuardConfig(require_branch_prefix="feature/"),
)

@tool_guard(audit_blocked=True)
def edit(file: str) -> str:
    return f"편집됨: {file}"


@tool_guard(audit_blocked=True)
def bash(command: str) -> str:
    return f"실행됨: {command}"


# tool_guard가 check → 실행 → record를 자동으로 묶는다(Ch30 §30.2) — 이전에는
# check_before_tool_call()이 순수 조회라 통과한 호출도 record_tool_call()을 손으로
# 호출해야 했고, 이걸 빠뜨리면 Phase 4의 Gate B가 "n/a"로 나오는 문제가 있었다(이
# 캡스톤을 검증하며 실제로 발견됐다) — tool_guard는 이 실수 자체를 구조적으로 없앤다.
with live_guardrail_session(guardrail, "suah-session"):
    # 자기 스코프(configs.py) 편집 — owner="수아"가 자기 자신의 클레임을 예외 처리하므로 통과
    edit(file="agent_evaluator/gates/gate_f_multiagent/configs.py")
    print("  [자기 스코프 편집] 차단 여부: False")

    # 실수 1) 태호의 스코프(evaluators.py)를 착각해서 건드리려는 시도
    try:
        edit(file="agent_evaluator/gates/gate_f_multiagent/evaluators.py")
    except GuardrailBlockedError as e:
        print(f"  [태호 스코프 오침범] 차단 여부: True  이유: {e.verdict.reason}")

    # 실수 2) 전용 브랜치가 아닌 곳에서 바로 커밋하려는 시도
    try:
        bash(command="git commit -m 'wip'")
    except GuardrailBlockedError as e:
        print(f"  [전용 브랜치 밖 커밋] 차단 여부: True  이유: {e.verdict.reason}")

snapshot = guardrail.snapshot()
print(f"  세션 요약: tool_calls={len(snapshot.get('tool_calls', []))}건  blocked_attempts={len(snapshot.get('blocked_attempts', []))}건")

# ===========================================================================
# Phase 4: 배치 품질 평가 — snapshot()을 TaskResult.extra에 실어 Gate A/B 확인
# ===========================================================================
print("\n=== Phase 4: 배치 품질 평가 ===")

monitor = PerformanceMonitor(output_dir=str(_OUTPUT_DIR), agent_version="capstone-demo-v1")
task = create_taskresult(
    task_id="suah-session",
    question="Gate F ConflictResolutionConfig에 새 옵션을 추가해줘",
    response="ConflictResolutionConfig에 tie_break_strategy 옵션을 추가하고 테스트 3건을 통과시켰습니다.",
    execution_time=42.0, task_type="tool_use", extra=snapshot,
)
monitor.record_task(task)
save_tasks_to_db(_DB_PATH, [task])  # Phase 5의 search_violations()가 조회할 세션 DB

report = monitor.generate_report().to_dict()
harness = report["extra_metrics"]["harness_groups"]
gate_a, gate_b = harness.get("A", {}), harness.get("B", {})
print(f"  Gate A: {gate_a.get('score')} ({gate_a.get('status', 'n/a')})")
print(f"  Gate B: {gate_b.get('score')} ({gate_b.get('status', 'n/a')})")
# Gate B가 만점인 건 예상대로다 — 차단된 시도 2건은 record_blocked_attempt()로 감사
# 이력에만 남고 tool_calls(Gate B/E 점수의 원천)에는 없기 때문이다(Chapter 30 §30.2).
# Gate A가 낮은 건 이 데모가 ground_truth나 명시적 완료 신호를 주지 않아서다 —
# 실제 프로젝트에서는 ground_truth나 completion_fn을 지정해야 Gate A가 의미 있는 값을 낸다.

result_path = monitor.save_to_file("capstone_result")
print(f"  저장 완료: {_OUTPUT_DIR / 'capstone_result.json'} (+ .html)")

# ===========================================================================
# Phase 5: PR 제출 — scripts/generate_pr_summary.py로 PR 본문 생성(§33.3 재사용)
# ===========================================================================
print("\n=== Phase 5: PR 제출 ===")

_pr_body_path = _OUTPUT_DIR / "pr_body.md"
_gen_script = _PROJECT_ROOT / "scripts" / "generate_pr_summary.py"
_cli_result = subprocess.run(
    [
        sys.executable, str(_gen_script),
        str(_OUTPUT_DIR / "capstone_result.json"),
        str(_DB_PATH),
        "team_concurrency",  # 이 세션에서 실제로 발생한 위반 키워드
    ],
    capture_output=True, text=True,
)
_pr_body_path.write_text(_cli_result.stdout, encoding="utf-8")
print(f"  scripts/generate_pr_summary.py exit={_cli_result.returncode}")
print(f"  PR 본문 저장 완료: {_pr_body_path}")
print("  --- PR 본문 미리보기 ---")
for line in _cli_result.stdout.splitlines():
    print(f"  {line}")

# ===========================================================================
# Phase 6: CI 게이팅 — 병합 전 CI가 클레임 로그를 감사한다(§31.5)
# ===========================================================================
print("\n=== Phase 6: CI 게이팅 (클레임 로그 감사) ===")

violations = audit_claims(str(_CLAIMS_PATH), ttl_hours=8)
print(f"  audit_claims(ttl_hours=8) 결과: {len(violations)}건")
# 수아·태호 둘 다 클레임을 아직 해제하지 않았지만 방금 시작해 TTL을 넘지 않았고
# 스코프도 겹치지 않으므로(각자 자기 파일만 클레임) violations == [] — CI 통과.
print(f"  → {'CI 통과 (violations 없음)' if not violations else 'CI 차단 — 위반 확인 필요'}")

# ===========================================================================
# Phase 7: 클레임 해제 — PR이 병합되면 각자 클레임을 해제한다
# ===========================================================================
print("\n=== Phase 7: 클레임 해제 ===")

append_claim(str(_CLAIMS_PATH), claim_id="c-suah-01", status="released")
append_claim(str(_CLAIMS_PATH), claim_id="c-taeho-01", status="released")
violations_after = audit_claims(str(_CLAIMS_PATH), ttl_hours=8)
print(f"  클레임 해제 후 audit_claims() 결과: {len(violations_after)}건 (계속 0건 유지)")

print(f"\n결과 저장 완료: {_OUTPUT_DIR}")
print(f"확인: agent-eval dashboard {_OUTPUT_DIR}")
print("agent_version='capstone-demo-v1' 태그가 §34.3의 프로덕션 역추적 연결 고리로 이어진다.")
