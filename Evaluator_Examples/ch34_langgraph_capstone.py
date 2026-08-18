"""
ch34_langgraph_capstone.py — Chapter 34 확장: 외부 프레임워크(LangGraph) 팀 캡스톤
====================================================================
Book Chapter 34 — 온보딩·기업 확장·실전 캡스톤 §34.4의 확장판

§34.4의 3인 팀 캡스톤이 SDK 자체(Gate F Config 추가)를 대상으로 했다면, 이 예제는
실제 외부 에이전트 프레임워크(LangGraph)로 만든 제품 — 2노드(retrieve→answer)
사내 규정 Q&A 에이전트 — 에 Ch28~34 전체 파이프라인을 적용한다.

**중요한 구분(이 예제 전체의 핵심)**: AOO 스택(`LiveGuardrail`)은 "이 파일을 짜는
개발 세션"을 지키는 것이지, 완성된 LangGraph 에이전트의 런타임을 지키는 게 아니다.
완성된 그래프의 실행 결과는 `@agent_eval(framework="langgraph")`로 별도 평가한다 —
이 둘은 같은 SDK 안에 있지만 완전히 다른 계층이다.

팀 구성: 지호(분석가, Tier 1) / 민준(retrieve 노드 담당) / 서연(answer 노드 담당)

섹션 0: 제품 코드 — LangGraph 2노드 그래프. `build_graph().invoke()`는 실제
        langgraph/langchain-core API를 호출한다(mock 아님) — retrieve_node()/
        answer_node()는 실전이라면 각각 retrieve_node.py/answer_node.py로 분리될
        민준/서연의 스코프이지만, 이 저장소의 예제 파일 컨벤션(챕터당 파일 1개)에
        맞춰 이 파일 안에 절을 나눠 담는다. 클레임/스코프 검사는 실제 파일 존재
        여부가 아니라 문자열 스코프만 비교하므로(§31.2), 이 통합이 데모의 정확성에
        영향을 주지 않는다.
섹션 1: §29.3 Spec — "0) 기존 자산 검색"(ch29_spec_driven.py의 카탈로그 재사용) +
        실패모드·Gate매핑·골든셋·세션목표 템플릿(민준/서연 스코프 분리)
섹션 2: §30~31 LiveGuardrail — 세션 시작 전 스코프 클레임 → 민준 세션 도중
        자기 파일 편집(통과) / 서연 파일 오침범 시도(차단) / 위험 명령 시도(차단) /
        confirm_before_execute()로 공유 파일(그래프 조립부) HITL 승인 거부
섹션 3: §32 TDD-AI — 실제 골든셋 3건을 v1(버그)·v2(수정) 두 버전으로 실행해
        Gate A–G 배치 채점. "출산휴가"가 "휴가"의 부분 문자열이라 오매칭되는 실제
        버그를 골든셋이 잡아내고, 수정 후 Gate A가 개선되는 과정을 재현한다.
        (실측: 저자가 실제 git 커밋으로 검증한 결과 Gate A 0.6457→0.7533,
        agent_version 40eb57ca→40eb57ca-dirty-a3f397 — 재현성을 위해 이 예제는
        명시적 버전 문자열 "v1-buggy"/"v2-fixed"를 쓴다. 실전에서는
        agent_version="auto"가 이 태깅을 커밋 상태로 자동으로 해준다.)
섹션 4: §33 PR 거버넌스 — v1→v2 baseline 델타 확인 + PR 본문 자동 생성
        (scripts/generate_pr_summary.py와 동일 구조) + search_violations() 교차확인

의존성:
    pip install agent-evaluator
    pip install "agent-evaluator[langchain]"   (langgraph·langchain-core 포함 — 없으면
        설치 안내를 출력하고 종료한다)

실행:
    python Evaluator_Examples/ch34_langgraph_capstone.py

결과:
    results/langgraph_capstone/langgraph_capstone_claims.jsonl (섹션 2 — 스크래치 클레임 로그)
    results/langgraph_capstone/langgraph_capstone_sessions.db (섹션 2 — search_violations() 색인)
    results/langgraph_capstone/langgraph_capstone_{v1,v2}.json (+ .html) (섹션 3)
    results/langgraph_capstone/pr_body.md (섹션 4)
"""

import sys
from pathlib import Path

try:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
except ImportError:
    print("이 예제는 LangGraph/langchain-core가 필요합니다.")
    print('    pip install "agent-evaluator[langchain]"')
    sys.exit(0)

from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval
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
from agent_evaluator.integrations.live_guardrail_report import record_and_save
from agent_evaluator.storage.sqlite_backend import search_violations

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results" / "langgraph_capstone"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_CLAIMS_PATH = _OUTPUT_DIR / "langgraph_capstone_claims.jsonl"
_CLAIMS_PATH.write_text("", encoding="utf-8")  # 데모를 매번 깨끗한 상태에서 시작

# ===========================================================================
# 섹션 0: 제품 코드 — LangGraph 2노드 그래프 (실제 langgraph API, mock 아님)
# ===========================================================================
print("=== 섹션 0: 제품 코드 — LangGraph 2노드 그래프 ===")

# TODO(현업 적용): 실제 벡터DB/RAG로 교체. 지금은 결정론적 mock.
_DOCS = {
    "휴가": "연차는 입사 1년차부터 매월 1일씩 발생하며 최대 15일까지 이월 가능하다.",
    "재택": "재택근무는 주 2회까지 팀장 승인 하에 가능하다.",
}


def _search_docs(query: str, *, fixed: bool) -> str:
    """[민준 담당, retrieve_node.py] v1은 "출산휴가"가 "휴가"의 부분 문자열이라
    연차 규정으로 오매칭되는 실제 버그를 담고 있다. v2(fixed=True)가 그 수정본이다.
    """
    if fixed and "출산" in query:
        return "관련 문서를 찾지 못했습니다."
    for keyword, content in _DOCS.items():
        if keyword in query:
            return content
    return "관련 문서를 찾지 못했습니다."


def _make_retrieve_node(*, fixed: bool):
    def retrieve_node(state: MessagesState) -> dict:
        last_human = next(m for m in reversed(state["messages"]) if isinstance(m, HumanMessage))
        query = last_human.content
        assert isinstance(query, str)  # 이 데모는 항상 순수 문자열 content만 사용
        tool_call_id = "call_search_docs_1"
        ai_with_call = AIMessage(
            content="",
            tool_calls=[{"name": "search_docs", "args": {"query": query}, "id": tool_call_id}],
        )
        result = _search_docs(query, fixed=fixed)
        tool_msg = ToolMessage(content=result, name="search_docs", tool_call_id=tool_call_id)
        return {"messages": [ai_with_call, tool_msg]}

    return retrieve_node


def answer_node(state: MessagesState) -> dict:
    """[서연 담당, answer_node.py] 검색 결과를 근거로 최종 답변을 합성한다."""
    tool_result = next(m for m in reversed(state["messages"]) if isinstance(m, ToolMessage))
    return {"messages": [AIMessage(content=f"문서에 따르면: {tool_result.content}")]}


def build_graph(*, fixed: bool):
    """[지호 담당, docs_qa_graph.py — 공유 파일] 두 노드를 엮는다."""
    graph = StateGraph(MessagesState)
    graph.add_node("retrieve", _make_retrieve_node(fixed=fixed))
    graph.add_node("answer", answer_node)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", END)
    return graph.compile()


_smoke = build_graph(fixed=True).invoke(
    {"messages": [HumanMessage(content="휴가 규정이 궁금해요")]}
)
print(f"  스모크 테스트: {_smoke['messages'][-1].content!r}")

# ===========================================================================
# 섹션 1: §29.3 Spec-Driven — "0) 기존 자산 검색" → 4대 산출물
# ===========================================================================
print("\n=== 섹션 1: Ch29 Spec 산출물 ===")
print("  0) 기존 자산 검색: ch29_spec_driven.py에 동일 도메인(사내 규정 Q&A)의 실패모드")
print("     카탈로그·Gate 매핑이 이미 있음 → 재사용하고 LangGraph 고유 항목만 추가한다.")

FAILURE_MODE_CATALOG = [
    {"failure_mode": "존재하지 않는 규정 조항을 지어내 답변(환각)", "user_impact": "high"},
    {
        "failure_mode": "retrieve 노드가 ToolMessage를 누락 → answer 노드가 근거 없이 답변",
        "user_impact": "high",
    },
    {"failure_mode": "열람 권한이 없는 부서 문서 노출", "user_impact": "high"},
    {"failure_mode": "같은 질문에 다른 답변을 반복(비일관성)", "user_impact": "medium"},
    {"failure_mode": "검색 도구 무한 재호출(루프)", "user_impact": "low"},
]
for fm in FAILURE_MODE_CATALOG:
    print(f"    - [{fm['user_impact']:>6s}] {fm['failure_mode']}")

GOLDEN_SET = [
    {
        "question": "휴가 규정이 궁금해요",
        "ground_truth": "연차는 입사 1년차부터 매월 1일씩 발생하며 최대 15일까지 이월 가능하다.",
    },
    {
        "question": "재택근무 며칠까지 되나요",
        "ground_truth": "재택근무는 주 2회까지 팀장 승인 하에 가능하다.",
    },
    {
        "question": "출산휴가는 며칠인가요",
        "ground_truth": "관련 문서를 찾지 못했습니다.",
    },  # 문서에 없는 케이스
]

MINJUN_SPEC = {
    "developer": "민준",
    "목표": "retrieve_node.py — 질문에서 검색어를 뽑아 문서를 조회한다",
    "완료조건": ["골든셋 3건 모두 정확한 문서(또는 '찾지 못함')를 반환한다"],
    "금지": ["retrieve_node.py 밖의 파일은 건드리지 않는다"],
}
SEOYEON_SPEC = {
    "developer": "서연",
    "목표": "answer_node.py — 검색 결과를 근거로 답변을 합성한다",
    "완료조건": ["ToolMessage 내용을 답변에 그대로 포함한다"],
    "금지": ["answer_node.py 밖의 파일은 건드리지 않는다"],
}
for spec in (MINJUN_SPEC, SEOYEON_SPEC):
    print(f"  [{spec['developer']}] {spec['목표']} / 금지: {spec['금지'][0]}")

# ===========================================================================
# 섹션 2: §30~31 LiveGuardrail — 클레임 선언 → 세션 도중 실시간 차단 → HITL
# ===========================================================================
print("\n=== 섹션 2: LiveGuardrail 실시간 차단 (Ch30·Ch31) ===")

for dev, scope in [("민준", ["retrieve_node.py"]), ("서연", ["answer_node.py"])]:
    conflicts = check_scope_claim(scope, str(_CLAIMS_PATH))
    if not conflicts:
        append_claim(
            str(_CLAIMS_PATH),
            claim_id=f"c-{dev}-01",
            developer=dev,
            scope=scope,
            started_at="2026-07-13T09:00:00+09:00",
            status="active",
        )
    print(f"  [{dev}] 클레임 개설 — 스코프={scope}, 충돌={'있음' if conflicts else '없음'}")

guardrail = LiveGuardrail(
    scope=ScopeConfig(allowed_tools=["read", "edit", "grep", "glob"], fail_on_violation=True),
    tool_parameter_safety=ToolParameterSafetyConfig(
        dangerous_patterns=[
            r"\.\./",
            r"&&",
            r"\|\|",
            r";.*rm\s",
            r"__import__",
            r"eval\(",
            r"exec\(",
            r"\brm\s+\S",
        ],
        scope_tool_names=["bash"],
        fail_on_dangerous=True,
    ),
    team_concurrency=TeamConcurrencyConfig(claims_path=str(_CLAIMS_PATH), owner="민준"),
    branch_guard=BranchGuardConfig(require_branch_prefix="feature/"),
)

@tool_guard(audit_blocked=True)
def edit(file: str) -> str:
    return f"편집됨: {file}"


@tool_guard(audit_blocked=True)
def bash(command: str) -> str:
    return f"실행됨: {command}"


# tool_guard가 check → 실행 → record를 자동으로 묶는다(Ch30 §30.2) — 세 시도 모두
# 이 함수들을 평소처럼 호출하기만 하면 되고, 차단은 GuardrailBlockedError로 드러난다.
with live_guardrail_session(guardrail, "minjun-session"):
    edit(file="retrieve_node.py")
    print("  [자기 파일 편집]        block=False")

    try:
        edit(file="answer_node.py")
    except GuardrailBlockedError as e:
        print(f"  [서연 파일 오침범 시도]  block=True reason={e.verdict.reason}")

    try:
        bash(command="rm -f retrieve_node.py")
    except GuardrailBlockedError as e:
        print(f"  [위험 명령 시도]        block=True reason={e.verdict.reason}")


def confirm_before_execute(
    guardrail, task_id, tool_name, parameters, requires_confirmation, approve_fn=None
):
    """Ch30 §30.2 참조 패턴 — HITL "confirmed" 단계는 verdict 이후 조합한다."""
    verdict = guardrail.check_before_tool_call(task_id, tool_name, parameters)
    if verdict.block:
        guardrail.record_blocked_attempt(task_id, tool_name, verdict)
        return f"차단됨 (Gate {verdict.gate}): {verdict.reason}"
    if requires_confirmation and not (approve_fn() if approve_fn else False):
        return "거부됨: 사람의 승인 없이는 공유 파일(그래프 조립부)을 고치지 않음"
    guardrail.record_tool_call(task_id, tool_name, parameters)
    return f"실행됨: {tool_name}({parameters})"


hitl_result = confirm_before_execute(
    guardrail,
    "minjun-session",
    "edit",
    {"file": "docs_qa_graph.py"},
    requires_confirmation=True,
)
print(f"  [공유 파일 수정 시도]    {hitl_result}")

audit_result = audit_claims(str(_CLAIMS_PATH), ttl_hours=8)
print(f"  audit_claims(): {audit_result if audit_result else '위반 없음 (PASS)'}")

_sessions_db = str(_OUTPUT_DIR / "langgraph_capstone_sessions.db")
save_result = record_and_save(
    {
        "task_id": "minjun-session",
        "extra": guardrail.to_task_extra(),
        "output_dir": str(_OUTPUT_DIR),
        "save_filename": "langgraph_capstone_sessions",
        "success": None,
    }
)
print(f"  세션 리포트 편입: gate_b={save_result.get('gate_b_score')}")

# ===========================================================================
# 섹션 3: §32 TDD-AI — 골든셋이 실제 버그를 잡는 v1(버그) → v2(수정) 비교
# ===========================================================================
print("\n=== 섹션 3: TDD-AI 버전 비교 (Ch32) ===")

_gate_a_scores = {}
for version, fixed, note in [
    ("v1-buggy", False, "retrieve/answer 2-노드 그래프 최초 구현"),
    ("v2-fixed", True, "'출산' 복합어 오매칭 버그 수정(민준, retrieve_node.py)"),
]:
    app = build_graph(fixed=fixed)
    monitor = PerformanceMonitor(
        output_dir=str(_OUTPUT_DIR),
        agent_version=version,
        iteration_note=note,
    )

    @agent_eval(
        monitor, task_type="information_retrieval", framework="langgraph", task_id_prefix=version
    )
    def docs_qa_agent(question: str, ground_truth: str = "", _app=app):
        return _app.invoke({"messages": [HumanMessage(content=question)]})

    n_pass = 0
    for case in GOLDEN_SET:
        result = docs_qa_agent(case["question"], ground_truth=case["ground_truth"])
        final_answer = result["messages"][-1].content
        if case["ground_truth"] in final_answer:
            n_pass += 1

    report = monitor.generate_report()
    gate_a = (report.extra_metrics or {}).get("harness_groups", {}).get("A", {}).get("score")
    _gate_a_scores[version] = gate_a
    monitor.save_to_file(f"langgraph_capstone_{version}")
    print(f"  [{version}] 골든셋 {n_pass}/{len(GOLDEN_SET)} PASS, Gate A={gate_a}")

# ===========================================================================
# 섹션 4: §33 PR 거버넌스 — baseline 델타 + PR 본문 생성 + 위반 이력 교차확인
# ===========================================================================
print("\n=== 섹션 4: PR 검증과 거버넌스 (Ch33) ===")

delta = _gate_a_scores["v2-fixed"] - _gate_a_scores["v1-buggy"]
_a1, _a2 = _gate_a_scores["v1-buggy"], _gate_a_scores["v2-fixed"]
print(f"  Gate A 델타: {_a1:.4f} → {_a2:.4f} ({delta:+.4f})")
print(
    "  실전 CI 명령: agent-eval gate results/ci_run.json "
    "--baseline-version main-latest --fail-on-regression 10"
)

violations = search_violations(_sessions_db, "team_concurrency", include_blocked=True)
violations += search_violations(_sessions_db, "scope", include_blocked=True)
pr_lines = [
    "## 세션 목표",
    "'출산' 복합어 오매칭 버그 수정(민준, retrieve_node.py)",
    "",
    "## Gate A 델타",
    f"{_gate_a_scores['v1-buggy']:.4f} → {_gate_a_scores['v2-fixed']:.4f} ({delta:+.4f})",
    "",
    "## 위반 이력",
]
seen = set()
for v in violations:
    if v["summary"] in seen:
        continue
    seen.add(v["summary"])
    pr_lines.append(f"- {'[차단됨]' if v.get('blocked') else '[관찰됨]'} {v['summary']}")
if not seen:
    pr_lines.append("- 없음")
pr_body = "\n".join(pr_lines)
(_OUTPUT_DIR / "pr_body.md").write_text(pr_body, encoding="utf-8")
print(f"  PR 본문 생성 완료 — 위반 {len(seen)}건 포함")

print(f"\n확인: agent-eval dashboard {_OUTPUT_DIR}")
print(
    f"결과 저장 완료: {_OUTPUT_DIR}/langgraph_capstone_{{v1-buggy,v2-fixed}}.json"
    " (+ .html), pr_body.md"
)
