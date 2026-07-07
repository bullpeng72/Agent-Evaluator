"""
tests/test_live_guardrail_stdio.py
=====================================
SPEC-019 Rollout 6단계: agent_evaluator.integrations.live_guardrail_stdio 검증.

stdin/stdout을 io.StringIO로 대체해 프로세스 스폰 없이 프로토콜 자체를 검증한다.
"""
import io
import json

from agent_evaluator.integrations.live_guardrail_stdio import run


def _run_protocol(requests):
    """요청(dict) 리스트를 개행 구분 JSON으로 만들어 run()에 넣고, 응답(dict) 리스트를 반환."""
    instream = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
    outstream = io.StringIO()
    run(instream, outstream)
    lines = [ln for ln in outstream.getvalue().splitlines() if ln]
    return [json.loads(ln) for ln in lines]


class TestInitProtocol:
    def test_init_ok(self):
        responses = _run_protocol([{"op": "init", "scope": {"forbidden_tools": ["rm"]}}])
        assert responses == [{"ok": True}]

    def test_check_before_init_returns_error(self):
        responses = _run_protocol([{"op": "check", "task_id": "t1", "tool_name": "x"}])
        assert "error" in responses[0]

    def test_unknown_op_returns_error(self):
        responses = _run_protocol([{"op": "init"}, {"op": "bogus"}])
        assert responses[0] == {"ok": True}
        assert "error" in responses[1]

    def test_invalid_json_line_returns_error_and_continues(self):
        instream = io.StringIO('{"op": "init"}\nnot json\n{"op": "shutdown"}\n')
        outstream = io.StringIO()
        run(instream, outstream)
        lines = [json.loads(ln) for ln in outstream.getvalue().splitlines() if ln]
        assert lines[0] == {"ok": True}
        assert "error" in lines[1]
        assert lines[2] == {"ok": True}


class TestCheckRecordSnapshotRoundTrip:
    def test_scope_violation_blocks(self):
        responses = _run_protocol([
            {"op": "init", "scope": {"forbidden_tools": ["rm"], "fail_on_violation": True}},
            {"op": "check", "task_id": "t1", "tool_name": "rm", "parameters": {"path": "/x"}},
        ])
        assert responses[0] == {"ok": True}
        verdict = responses[1]
        assert verdict["block"] is True
        assert verdict["gate"] == "B"

    def test_clean_call_does_not_block(self):
        responses = _run_protocol([
            {"op": "init", "scope": {"forbidden_tools": ["rm"], "fail_on_violation": True}},
            {"op": "check", "task_id": "t1", "tool_name": "search", "parameters": {}},
        ])
        assert responses[1]["block"] is False
        assert responses[1]["gate"] is None
        assert responses[1]["reason"] is None
        assert responses[1]["detail"] == {}

    def test_record_then_snapshot_reflects_confirmed_calls(self):
        responses = _run_protocol([
            {"op": "init", "scope": {"allowed_tools": ["search"]}},
            {"op": "record", "task_id": "t1", "tool_name": "search", "parameters": {"q": "a"}},
            {"op": "record", "task_id": "t1", "tool_name": "search", "parameters": {"q": "b"}},
            {"op": "snapshot"},
        ])
        assert responses[1] == {"ok": True}
        assert responses[2] == {"ok": True}
        extra = responses[3]["extra"]
        assert extra["scope"]["in_scope"] is True
        assert extra["scope"]["unique_tools"] == ["search"]

    def test_tool_authorization_blocks_via_tracker_kwargs(self):
        responses = _run_protocol([
            {"op": "init", "tool_authorization": {"restricted_tools": ["shell_exec"]}},
            {"op": "check", "task_id": "t1", "tool_name": "shell_exec", "parameters": {}},
        ])
        verdict = responses[1]
        assert verdict["block"] is True
        assert verdict["gate"] == "E"

    def test_shutdown_stops_loop(self):
        responses = _run_protocol([
            {"op": "init"},
            {"op": "shutdown"},
            {"op": "check", "task_id": "t1", "tool_name": "x"},  # 이후 요청은 처리되지 않아야 함
        ])
        assert responses == [{"ok": True}, {"ok": True}]


class TestRecordBlockedProtocol:
    """SPEC-030 REQ-6: {"op": "record_blocked", ...} — 완전 차단된 시도의 감사 이력."""

    def test_record_blocked_then_snapshot_reflects_it(self):
        responses = _run_protocol([
            {"op": "init", "scope": {"forbidden_tools": ["rm"], "fail_on_violation": True}},
            {"op": "check", "task_id": "t1", "tool_name": "rm", "parameters": {"path": "/x"}},
            {"op": "record_blocked", "task_id": "t1", "tool_name": "rm", "gate": "B", "reason": "scope violation"},
            {"op": "snapshot"},
        ])
        check_verdict = responses[1]
        assert check_verdict["block"] is True
        assert responses[2] == {"ok": True}
        extra = responses[3]["extra"]
        assert extra["blocked_attempts"] == [
            {"tool_name": "rm", "gate": "B", "reason": "scope violation"},
        ]

    def test_record_blocked_does_not_affect_confirmed_tool_calls(self):
        responses = _run_protocol([
            {"op": "init", "scope": {"allowed_tools": ["search"]}},
            {"op": "record", "task_id": "t1", "tool_name": "search", "parameters": {"q": "a"}},
            {"op": "record_blocked", "task_id": "t1", "tool_name": "rm", "gate": "B", "reason": "blocked"},
            {"op": "snapshot"},
        ])
        extra = responses[3]["extra"]
        assert extra["tool_calls"] == [{"name": "search", "arguments": {"q": "a"}}]
        assert extra["blocked_attempts"] == [
            {"tool_name": "rm", "gate": "B", "reason": "blocked"},
        ]


class TestRecordOutputProtocol:
    """SPEC-031 REQ-2: {"op": "record", ..., "output": {...}} — 도구 실행 결과 캡처."""

    def test_output_field_is_merged_into_tool_call(self):
        responses = _run_protocol([
            {"op": "init"},
            {"op": "record", "task_id": "t1", "tool_name": "bash", "parameters": {"command": "pytest"},
             "output": {"success": False, "exit_code": 1}},
            {"op": "snapshot"},
        ])
        extra = responses[2]["extra"]
        assert extra["tool_calls"] == [
            {"name": "bash", "arguments": {"command": "pytest"}, "success": False, "exit_code": 1},
        ]

    def test_omitted_output_is_backward_compatible(self):
        responses = _run_protocol([
            {"op": "init"},
            {"op": "record", "task_id": "t1", "tool_name": "search", "parameters": {"q": "a"}},
            {"op": "snapshot"},
        ])
        extra = responses[2]["extra"]
        assert extra["tool_calls"] == [{"name": "search", "arguments": {"q": "a"}}]

    def test_init_max_tool_output_chars_is_applied(self):
        responses = _run_protocol([
            {"op": "init", "max_tool_output_chars": 5},
            {"op": "record", "task_id": "t1", "tool_name": "bash", "parameters": {},
             "output": {"stdout": "0123456789"}},
            {"op": "snapshot"},
        ])
        extra = responses[2]["extra"]
        assert extra["tool_calls"][0]["stdout"] == "01234"
