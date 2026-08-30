"""
tests/test_violation_search_mcp.py
=====================================
SPEC-024 REQ-4: violation_search_mcp.py stdio MCP 서버 검증.

FastMCP.call_tool()로 실제 stdio 전송 계층 없이 도구 등록·호출을 in-process로
검증한다(mcp SDK가 공식 제공하는 테스트 방식). 실제 stdio 핸드셰이크 자체는
subprocess로 별도 1회 수동 확인했다(SPEC-019 stdio 브리지와 동일한 검증 관례,
Docs/specs/SPEC-024-local-ade-memory-layer.md 구현 노트 참고).
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("mcp")

from agent_evaluator import create_taskresult
from agent_evaluator.integrations.violation_search_mcp import (
    _default_db_path,
    build_server,
    format_results,
)
from agent_evaluator.storage.sqlite_backend import save_tasks_to_db


def _violating_task(task_id: str):
    return create_taskresult(
        task_id=task_id, question="q", response="r",
        ground_truth="r", execution_time=0.5, task_type="tool_use",
        extra={
            "tool_parameter_safety": {
                "safety_score": 0.75, "dangerous_calls": ["bash"],
                "violations": ["dangerous_pattern:bash:rm_shell_command"],
                "checked_calls": 1, "violation_count": 1,
            },
        },
    )


def _blocked_task(task_id: str):
    """SPEC-030: 완전 차단된 시도 — violation_search가 아니라 blocked_violations에 색인."""
    return create_taskresult(
        task_id=task_id, question="q", response="r",
        ground_truth="r", execution_time=0.5, task_type="tool_use",
        extra={"blocked_attempts": [
            {"tool_name": "bash", "gate": "B", "reason": "dangerous tool parameters: ['bash']"},
        ]},
    )


class TestFormatResults:
    def test_empty_results_says_no_match_explicitly(self):
        """결과가 없을 때 모델이 결과를 지어내지 않도록 명시적으로 "없다"고 말한다."""
        text = format_results([])
        assert "No matching" in text

    def test_non_empty_results_include_task_id_and_summary(self):
        results = [{
            "task_id": "session-1", "summary": "tool_parameter_safety: dangerous_pattern:bash:rm",
            "timestamp": "2026-07-05T00:00:00", "task_type": "tool_use", "success": False,
        }]
        text = format_results(results)
        assert "session-1" in text
        assert "dangerous_pattern:bash:rm" in text
        assert "tool_use" in text

    def test_no_blocked_key_yields_no_prefix(self):
        """SPEC-030 REQ-5: include_blocked=False로 검색한(blocked 키가 아예 없는)
        결과는 접두어 없이 기존과 동일하게 렌더링된다 — 회귀 없음."""
        results = [{
            "task_id": "session-1", "summary": "scope: ['out_of_scope:edit']",
            "timestamp": "2026-07-05T00:00:00", "task_type": "tool_use", "success": False,
        }]
        text = format_results(results)
        assert "[BLOCKED]" not in text
        assert "[OBSERVED]" not in text

    def test_blocked_true_gets_blocked_prefix(self):
        results = [{
            "task_id": "session-1", "summary": "bash: dangerous tool parameters: ['bash']",
            "timestamp": "2026-07-05T00:00:00", "task_type": "tool_use", "success": False,
            "blocked": True,
        }]
        text = format_results(results)
        assert "[BLOCKED]" in text

    def test_blocked_false_gets_observed_prefix(self):
        results = [{
            "task_id": "session-1", "summary": "scope: ['out_of_scope:edit']",
            "timestamp": "2026-07-05T00:00:00", "task_type": "tool_use", "success": False,
            "blocked": False,
        }]
        text = format_results(results)
        assert "[OBSERVED]" in text


class TestDefaultDbPath:
    def test_respects_output_dir_env_var(self, monkeypatch):
        monkeypatch.setenv("AGENT_EVALUATOR_OUTPUT_DIR", "/tmp/custom_dir")
        assert _default_db_path() == os.path.join("/tmp/custom_dir", "opencode_sessions.db")

    def test_falls_back_to_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("AGENT_EVALUATOR_OUTPUT_DIR", raising=False)
        assert _default_db_path() == os.path.join(
            "results/opencode_live_guardrail", "opencode_sessions.db"
        )


class TestBuildServerToolRegistration:
    @pytest.mark.asyncio
    async def test_search_violations_tool_is_registered(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        server = build_server(db_path)
        tools = await server.list_tools()
        assert [t.name for t in tools] == ["search_violations"]


class TestSearchViolationsToolEndToEnd:
    @pytest.mark.asyncio
    async def test_matching_query_returns_formatted_violation(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        save_tasks_to_db(db_path, [_violating_task("session-1")])

        server = build_server(db_path)
        content, _ = await server.call_tool("search_violations", {"query": "bash"})
        text = content[0].text
        assert "session-1" in text
        assert "bash" in text

    @pytest.mark.asyncio
    async def test_unmatched_query_returns_no_results_message(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        save_tasks_to_db(db_path, [_violating_task("session-1")])

        server = build_server(db_path)
        content, _ = await server.call_tool("search_violations", {"query": "kubernetes"})
        assert "No matching" in content[0].text

    @pytest.mark.asyncio
    async def test_default_db_path_used_when_none_given(self, tmp_path, monkeypatch):
        """db_path를 생략하면 AGENT_EVALUATOR_OUTPUT_DIR 기반 기본 경로를 사용한다."""
        monkeypatch.setenv("AGENT_EVALUATOR_OUTPUT_DIR", str(tmp_path))
        db_path = str(tmp_path / "opencode_sessions.db")
        save_tasks_to_db(db_path, [_violating_task("session-1")])

        server = build_server(None)
        content, _ = await server.call_tool("search_violations", {"query": "bash"})
        assert "session-1" in content[0].text

    @pytest.mark.asyncio
    async def test_fully_blocked_attempt_is_found_via_mcp_tool(self, tmp_path):
        """SPEC-030 REQ-5: 이 도구의 docstring이 원래 약속한 "차단된 이력" 검색이
        실제로 동작한다 — 완전 차단된 시도(observation 모드가 아닌)가 결과에 나온다."""
        db_path = str(tmp_path / "test.db")
        save_tasks_to_db(db_path, [_blocked_task("session-blocked")])

        server = build_server(db_path)
        content, _ = await server.call_tool("search_violations", {"query": "dangerous"})
        text = content[0].text
        assert "session-blocked" in text
        assert "[BLOCKED]" in text
