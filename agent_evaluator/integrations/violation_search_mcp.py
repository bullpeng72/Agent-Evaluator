"""
agent_evaluator.integrations.violation_search_mcp
=====================================================
SPEC-024 REQ-4: ``search_violations()``(REQ-3)를 감싸는 최소 stdio MCP 서버.

노출 도구는 정확히 하나 — ``search_violations(query: str) -> str``. REQ-3의 구조화
결과(``List[Dict[str, Any]]``)를 사람이 읽기 쉬운 자연어 문자열로 변환해 반환한다
(MCP 도구 결과는 모델에게 텍스트로 전달되므로, 구조화 dict를 그대로 넘기는 것보다
읽기 쉬운 문자열이 다음 세션의 모델이 실제로 활용하기에 더 낫다).

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
import sys
from typing import Any, Dict, List, Optional

from agent_evaluator.storage.sqlite_backend import search_violations as _search_violations

_DEFAULT_OUTPUT_DIR = "results/opencode_live_guardrail"
_DEFAULT_DB_FILENAME = "opencode_sessions.db"


def _default_db_path() -> str:
    """``live_guardrail_report.py``의 기본 저장 경로와 동일한 규칙으로 db_path를 정한다."""
    output_dir = os.environ.get("AGENT_EVALUATOR_OUTPUT_DIR", _DEFAULT_OUTPUT_DIR)
    return os.path.join(output_dir, _DEFAULT_DB_FILENAME)


def format_results(results: List[Dict[str, Any]]) -> str:
    """(REQ-4) REQ-3의 구조화 검색 결과를 사람이 읽기 쉬운 문자열로 변환한다.

    Args:
        results: :func:`agent_evaluator.storage.sqlite_backend.search_violations`
            의 반환값.

    Returns:
        결과가 없으면 명시적으로 "없다"고 말하는 문장(모델이 결과를 지어내지
        않도록) — 결과가 있으면 관련도 순으로 번호를 매긴 사람이 읽을 수 있는 목록.
    """
    if not results:
        return "일치하는 과거 위반 이력이 없습니다."
    lines = ["과거 위반 이력 검색 결과:"]
    for i, r in enumerate(results, start=1):
        lines.append(
            f"{i}. [{r.get('timestamp')}] task_id={r.get('task_id')} "
            f"(task_type={r.get('task_type')}, success={r.get('success')}): {r.get('summary')}"
        )
    return "\n".join(lines)


def build_server(db_path: Optional[str] = None) -> Any:
    """(REQ-4) ``search_violations`` 도구 1개를 노출하는 ``FastMCP`` 인스턴스를 만든다.

    Args:
        db_path: 검색 대상 SQLite DB 파일 경로. ``None``이면 :func:`_default_db_path`.

    Returns:
        ``mcp.server.fastmcp.FastMCP`` 인스턴스(아직 ``run()``은 호출하지 않음).
    """
    from mcp.server.fastmcp import FastMCP

    _db_path = db_path or _default_db_path()
    server = FastMCP("agent-evaluator-violations")

    @server.tool()
    def search_violations(query: str) -> str:
        """과거 세션에서 Gate B(행동 무결성)·Gate E(보안 경계) 위반으로 차단된
        이력을 자연어로 검색한다.

        지금 시도하려는 도구 호출(셸 명령, 파일 삭제 등)이 과거 세션에서 이미
        LiveGuardrail에 의해 차단된 적이 있는지 확인하고 싶을 때 사용하라.
        """
        results = _search_violations(_db_path, query)
        return format_results(results)

    return server


def main(argv: Optional[List[str]] = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    db_path = argv[0] if argv else None
    server = build_server(db_path)
    server.run()


if __name__ == "__main__":
    main()
