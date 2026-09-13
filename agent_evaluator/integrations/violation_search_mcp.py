"""
agent_evaluator.integrations.violation_search_mcp
=====================================================
SPEC-024 REQ-4: ``search_violations()``(REQ-3)를 감싸는 최소 stdio MCP 서버.

노출 도구는 둘 — ``search_violations(query: str) -> str`` (REQ-3의 구조화 결과를
사람이 읽는 문자열로 변환) 과 ``show_violation(task_id: str) -> str`` (SPEC-041 —
검색 결과의 task_id로 이어서 호출해 그 세션에서 차단된 명령의 원문 발췌를 본다).
MCP 도구 결과는 모델에게 텍스트로 전달되므로, 구조화 dict를 그대로 넘기는 것보다
읽기 쉬운 문자열이 다음 세션의 모델이 실제로 활용하기에 더 낫다.

이 모듈은 세션 내내 살아있는 stdio MCP 서버다(``live_guardrail_stdio.py``와 동일한
장수명 프로세스 모델, ``live_guardrail_report.py``의 1회성 배치 브리지와는 다르다) —
``ctx mcp serve``/``opencode mcp add ctx-history -- ctx mcp serve``와 동일한 방식으로
OpenCode에 등록해서 쓴다(Ch27/28 라이브 검증에서 이미 확인된 등록 경로).

실행::

    python -m agent_evaluator.integrations.violation_search_mcp [db_path]

``db_path``를 생략하면 ``AGENT_EVALUATOR_OUTPUT_DIR``(기본값
``results/opencode_live_guardrail``) 아래의 ``opencode_sessions.db``를 사용한다 —
``live_guardrail_report.py``가 기본으로 저장하는 경로와 동일하다.

OpenCode 등록::

    opencode mcp add agent-evaluator-violations -- \\
        python -m agent_evaluator.integrations.violation_search_mcp

의존성(옵트인, ``pip install "agent-evaluator[mcp]"``)::

    mcp>=1.0.0
"""
from __future__ import annotations

import os
import sqlite3
import sys
from typing import Any

from agent_evaluator.integrations._blocked_detail import truncate_excerpt
from agent_evaluator.storage.sqlite_backend import list_violations as _list_violations
from agent_evaluator.storage.sqlite_backend import search_violations as _search_violations

_DEFAULT_OUTPUT_DIR = "results/opencode_live_guardrail"
_DEFAULT_DB_FILENAME = "opencode_sessions.db"


def _default_db_path() -> str:
    """``live_guardrail_report.py``의 기본 저장 경로와 동일한 규칙으로 db_path를 정한다."""
    output_dir = os.environ.get("AGENT_EVALUATOR_OUTPUT_DIR", _DEFAULT_OUTPUT_DIR)
    return os.path.join(output_dir, _DEFAULT_DB_FILENAME)


# SPEC-041 P3.2: 위반 요약 텍스트에서 감지되는 키워드 → (Gate, recommend_fix metric).
# search_violations 결과를 찾은 뒤 "그래서 뭘 고쳐야?"로 이어지도록 recommend_fix 힌트를
# 붙이기 위한 것 — 두 MCP 도구(search_violations ↔ recommend_fix)를 체이닝한다.
_VIOLATION_TO_GATE_METRIC: tuple[tuple[str, str, str], ...] = (
    ("loop_detection", "B", "loop_detection"),
    ("consecutive_repeat", "B", "loop_detection"),
    ("deadlock", "B", "deadlock"),
    ("scope", "B", "scope_score"),
    ("tool_parameter_safety", "B", "tool_parameter_safety"),
    ("dangerous", "B", "tool_parameter_safety"),
    ("tool_authorization", "E", "threat_severity"),
    ("privilege_escalation", "E", "threat_severity"),
    ("tool_chain_attack", "E", "threat_severity"),
    ("protected write", "E", "threat_severity"),
)


def format_results(
    results: list[dict[str, Any]],
    *,
    header: str = "Past violation history — search results:",
    empty_message: str = "No matching past violation history found.",
) -> str:
    """(REQ-4) REQ-3의 구조화 검색 결과를 사람이 읽기 쉬운 문자열로 변환한다.

    SPEC-045 REQ-4/5: ``header``/``empty_message``를 열어둬 ``list_violations()``
    (키워드 없는 브라우징)도 동일한 렌더링을 재사용한다 — 정렬 기준(최신순 vs
    관련도순)만 다르고 한 줄 형식·``[BLOCKED]``/``[OBSERVED]`` 접두어·발췌 표시·
    recommend_fix/show_violation 체이닝 힌트는 완전히 동일하게 유지된다.

    Args:
        results: :func:`agent_evaluator.storage.sqlite_backend.search_violations` 또는
            :func:`agent_evaluator.storage.sqlite_backend.list_violations`의 반환값.
        header: 결과가 있을 때 첫 줄에 쓸 문구(호출 맥락에 맞게 오버라이드).
        empty_message: 결과가 없을 때 낼 문장 — 모델이 결과를 지어내지 않도록 항상
            명시적으로 "없다"고 말한다.

    Returns:
        결과가 없으면 ``empty_message`` — 결과가 있으면 번호를 매긴 사람이 읽을 수
        있는 목록. 결과에서 위반 유형이 식별되면 이어서 호출할 ``recommend_fix``
        힌트를 덧붙인다.
    """
    if not results:
        return empty_message
    lines = [header]
    _blocked_task_ids: list[str] = []
    for i, r in enumerate(results, start=1):
        # SPEC-030 REQ-5: include_blocked=True 결과에만 "blocked" 키가 있다 —
        # 관찰 모드(위반 기록만, 실행은 됨)와 완전 차단(실행 자체가 막힘)을
        # 모델이 혼동하지 않도록 접두어로 명확히 구분한다.
        _prefix = "[BLOCKED] " if r.get("blocked") else "[OBSERVED] " if "blocked" in r else ""
        lines.append(
            f"{i}. {_prefix}[{r.get('timestamp')}] task_id={r.get('task_id')} "
            f"(task_type={r.get('task_type')}, success={r.get('success')}): {r.get('summary')}"
        )
        # SPEC-041: with detail=True the blocked rows carry a short PII-redacted excerpt of
        # the offending command — show it inline so no second round-trip is needed.
        # SPEC-045 REQ-7: the stored excerpt may be captured at report_max_chars (longer,
        # for the HTML report) — trim it back down for this scannable list/search context.
        _ex = (r.get("arg_excerpt") or "").strip() if r.get("blocked") else ""
        if _ex:
            lines.append(f"   command: {truncate_excerpt(_ex)}")
        if r.get("blocked") and r.get("task_id"):
            _blocked_task_ids.append(str(r["task_id"]))

    # 가장 흔한 위반 유형 하나를 골라 recommend_fix 힌트로 연결한다.
    _blob = " ".join(str(r.get("summary") or "") for r in results).lower()
    _hit = next(
        ((g, m) for kw, g, m in _VIOLATION_TO_GATE_METRIC if kw in _blob), None
    )
    if _hit:
        _g, _m = _hit
        lines.append(
            f"\nTo see how to address this, call the recommend_fix "
            f"(gate=\"{_g}\", metric=\"{_m}\") tool."
        )
    # SPEC-041: chain into show_violation() for the full command(s) of a blocked session —
    # the model already has the task_id from the lines above, no human copy-paste.
    if _blocked_task_ids:
        _uniq = list(dict.fromkeys(_blocked_task_ids))
        lines.append(
            f"\nFor the exact command(s) of a blocked session, call show_violation "
            f"(task_id=\"{_uniq[0]}\")."
        )
    return "\n".join(lines)


def build_server(db_path: str | None = None) -> Any:
    """(REQ-4) ``search_violations`` 도구 1개를 노출하는 ``FastMCP`` 인스턴스를 만든다.

    Args:
        db_path: 검색 대상 SQLite DB 파일 경로. ``None``이면 :func:`_default_db_path`.

    Returns:
        ``mcp.server.fastmcp.FastMCP`` 인스턴스(아직 ``run()``은 호출하지 않음).
    """
    from mcp.server.fastmcp import FastMCP

    _db_path = db_path or _default_db_path()
    server = FastMCP("agent-evaluator-violations")

    def _no_db_message(action: str) -> str:
        return (
            f"No violation history database at {_db_path} yet — it is created when the "
            f"first LiveGuardrail-monitored session ends. Nothing to {action}. (If sessions "
            f"have already ended, this server is pointed at the wrong path: register it as "
            f"`python -m agent_evaluator.integrations.violation_search_mcp <batch-report-db>` "
            f"with an explicit path — see `agent-eval claude doctor`.)"
        )

    @server.tool()
    def list_violations(limit: int = 20, since: str | None = None, gate: str | None = None) -> str:
        """과거 세션에서 무엇이(혹은 무언가가 있기는 했는지) 차단/관찰됐는지 **전혀
        모를 때 가장 먼저** 호출한다 — search_violations()와 달리 키워드가 필요 없다.

        키워드 없이 최근 이력을 최신순으로 나열한다. 흥미로운 항목을 발견하면
        search_violations()로 좁히거나, show_violation(task_id)로 그 세션의 전체
        상세(원문 발췌)를 본다 — list_violations → search_violations → show_violation
        순서로 쓰는 3단 조회 체인의 시작점이다.

        Args:
            limit: 최대 반환 건수(관찰/차단 이력 각각).
            since: ISO-8601 타임스탬프 하한(예: "2026-09-08"). 생략하면 전체 기간.
            gate: "B" 또는 "E"로 좁힌다(차단 이력에만 적용 — 관찰 이력은 gate 컬럼이
                없어 이 필터와 무관하게 반환된다).
        """
        if not os.path.exists(_db_path):
            return _no_db_message("list")
        try:
            results = _list_violations(
                _db_path, include_blocked=True, detail=True,
                since=since, gate=gate, limit=limit,
            )
        except sqlite3.Error as exc:
            return f"Could not read the violation history database at {_db_path}: {exc}"
        return format_results(
            results,
            header=(
                "Recent violation/blocked-attempt history (most recent first, "
                "no keyword filter):"
            ),
            empty_message="No violation/blocked-attempt history recorded yet — nothing to list.",
        )

    @server.tool()
    def search_violations(query: str) -> str:
        """과거 세션에서 Gate B(행동 무결성)·Gate E(보안 경계) 위반으로 차단된
        이력을 자연어로 검색한다.

        지금 시도하려는 도구 호출(셸 명령, 파일 삭제 등)이 과거 세션에서 이미
        LiveGuardrail에 의해 차단된 적이 있는지 확인하고 싶을 때 사용하라. 뭘
        찾아야 할지조차 모르면 이 도구 대신 list_violations()부터 호출할 것.
        """
        # SPEC-041: the DB file only appears after the first monitored session ends
        # (or the configured path is simply wrong). Degrade to a plain sentence instead
        # of surfacing a raw "unable to open database file" traceback to the model.
        if not os.path.exists(_db_path):
            return _no_db_message("search")
        # SPEC-030 REQ-5: include_blocked=True로 완전 차단 이력(SPEC-030)까지
        # 함께 검색한다 — 이 도구의 docstring이 원래부터 약속했던 "차단된 이력"
        # 검색을 실제로 이행한다.
        try:
            results = _search_violations(
                _db_path, query, include_blocked=True, detail=True
            )
        except sqlite3.Error as exc:
            return f"Could not read the violation history database at {_db_path}: {exc}"
        return format_results(results)

    @server.tool()
    def show_violation(task_id: str) -> str:
        """한 세션(task_id)에서 차단된 도구 호출의 **원문(발췌)**을 보여준다.

        ``search_violations`` 결과의 ``task_id``를 그대로 넘겨 이어서 호출한다 —
        차단된 명령이 무엇이었는지, 어느 Gate/사유로 막혔는지 확인할 때 쓴다.
        감사 이력에 발췌가 없으면(캡처 이전 세션 등) 호스트 세션 트랜스크립트에서
        best-effort로 복원한다.
        """
        if not os.path.exists(_db_path):
            return (
                f"No violation history database at {_db_path} yet — nothing to show. "
                f"(It is created when the first LiveGuardrail-monitored session ends; if "
                f"sessions have already ended this server is pointed at the wrong path — "
                f"see `agent-eval claude doctor` / `agent-eval opencode doctor`.)"
            )
        try:
            from agent_evaluator.storage.sqlite_backend import show_violation as _show
        except Exception as exc:  # pragma: no cover - import guard
            return f"Could not load show_violation: {exc}"
        try:
            sv = _show(_db_path, task_id)
        except sqlite3.Error as exc:
            return f"Could not read the violation history database at {_db_path}: {exc}"
        from agent_evaluator.integrations._blocked_detail import format_blocked_detail

        return format_blocked_detail(sv)

    return server


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    db_path = argv[0] if argv else None
    try:
        server = build_server(db_path)
    except ImportError as exc:
        # SPEC-041: [mcp] extra 미설치 시 bare "No module named 'mcp'" 대신 명확한 안내를
        # stderr로 낸다 — 이 프로세스는 OpenCode/Claude가 스폰하므로 사용자는 클라이언트
        # 로그에서만 이걸 보게 된다.
        sys.stderr.write(
            f"[agent-evaluator] recommend/violation-search MCP server needs the optional "
            f"'mcp' dependency — install it with:  pip install \"agent-evaluator[mcp]\"\n"
            f"  (original error: {exc})\n"
        )
        raise SystemExit(1) from exc
    server.run()


if __name__ == "__main__":
    main()
