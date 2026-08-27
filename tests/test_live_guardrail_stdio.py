"""
tests/test_live_guardrail_stdio.py
=====================================
SPEC-019 Rollout 6단계: agent_evaluator.integrations.live_guardrail_stdio 검증.

stdin/stdout을 io.StringIO로 대체해 프로세스 스폰 없이 프로토콜 자체를 검증한다.
"""
import io
import json

from agent_evaluator.gates.team_concurrency import append_claim
from agent_evaluator.integrations.live_guardrail_stdio import build_guardrail, run


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


class TestRequestIdEcho:
    """SPEC-041: 요청에 "id"가 있으면 응답에 그대로 되돌려 실어 준다 — OpenCode .ts
    브리지가 응답을 FIFO 순서가 아니라 id로 매칭해, 타임아웃으로 취소된 요청의 늦은
    응답이 다음 요청에 잘못 배정되는 데스싱크를 피할 수 있게 한다."""

    def test_every_response_carries_its_request_id(self):
        responses = _run_protocol([
            {"op": "init", "id": 100, "scope": {"forbidden_tools": ["WebFetch"],
                                                "fail_on_violation": True}},
            {"op": "check", "id": 1, "task_id": "t", "tool_name": "Bash",
             "parameters": {"command": "ls"}},
            {"op": "check", "id": 2, "task_id": "t", "tool_name": "webfetch",
             "parameters": {"url": "x"}},
            {"op": "snapshot", "id": 3},
            {"op": "shutdown", "id": 4},
        ])
        by_id = {r["id"]: r for r in responses}
        assert by_id[100]["ok"] is True
        assert by_id[1]["block"] is False
        assert by_id[2]["block"] is True and by_id[2]["gate"] == "B"  # case-insensitive too
        assert "extra" in by_id[3]
        assert by_id[4]["ok"] is True

    def test_idless_request_gets_idless_response_backward_compat(self):
        responses = _run_protocol([{"op": "init"}, {"op": "bogus"}, {"op": "shutdown"}])
        assert all("id" not in r for r in responses)

    def test_error_response_also_carries_id(self):
        responses = _run_protocol([
            {"op": "check", "id": 7, "task_id": "t", "tool_name": "x"},  # before init
        ])
        assert responses[0]["id"] == 7 and "error" in responses[0]


class TestBuildGuardrailResilience:
    """SPEC-041: 한 Config 블록의 오타/잘못된 값이 전체 가드레일 빌드를 깨면 안 된다
    (설정 오타 하나로 보안 기능이 통째로 fail-open 되던 문제)."""

    def test_typo_in_one_config_block_is_skipped_rest_active(self, capsys):
        g = build_guardrail({
            "loop_detection": {"consecutive_repeat_treshold": 3},  # typo
            "tool_parameter_safety": {
                "dangerous_patterns": [r"rm -rf"], "scope_tool_names": ["bash"],
                "fail_on_dangerous": True,
            },
            "tool_authorization": {},
        })
        assert g._loop_detection is None                 # 잘못된 블록만 스킵
        assert g._tool_parameter_safety is not None       # 나머지는 살아있음
        assert "SKIPPED" in capsys.readouterr().err
        assert g.check_before_tool_call("t", "bash", {"command": "rm -rf /x"}).block is True

    def test_bad_value_in_tracker_block_is_skipped(self, capsys):
        g = build_guardrail({
            "privilege_escalation": {"not_a_real_kwarg": 1},
            "scope": {"forbidden_tools": ["webfetch"], "fail_on_violation": True},
        })
        assert g._privilege_escalation is None
        assert g._scope is not None
        assert "SKIPPED" in capsys.readouterr().err


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


class TestBranchGuardTeamConcurrencyProtocol:
    """branch_guard/team_concurrency were LiveGuardrail constructor kwargs from the
    start but were never added to _CONFIG_CLASSES, so neither the OpenCode stdio
    bridge nor the Claude Code hook bridge (build_guardrail() is shared by both,
    see claude_code_hook.py) could enable them via the init message. This class
    proves both are now actually enforced through the protocol, not just accepted
    without error."""

    def test_branch_guard_blocks_protected_branch_git_commit(self, monkeypatch):
        monkeypatch.setattr(
            "agent_evaluator.gates.live_guardrail.get_current_branch", lambda: "main",
        )
        responses = _run_protocol([
            {"op": "init", "branch_guard": {"protected_branches": ["main"]}},
            {"op": "check", "task_id": "t1", "tool_name": "bash",
             "parameters": {"command": "git commit -m wip"}},
        ])
        assert responses[0] == {"ok": True}
        verdict = responses[1]
        assert verdict["block"] is True
        assert verdict["gate"] == "B"

    def test_branch_guard_allows_non_protected_branch(self, monkeypatch):
        monkeypatch.setattr(
            "agent_evaluator.gates.live_guardrail.get_current_branch", lambda: "feature/x",
        )
        responses = _run_protocol([
            {"op": "init", "branch_guard": {"protected_branches": ["main"]}},
            {"op": "check", "task_id": "t1", "tool_name": "bash",
             "parameters": {"command": "git commit -m wip"}},
        ])
        assert responses[1]["block"] is False

    def test_team_concurrency_blocks_overlapping_claim(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c-1", developer="other-dev",
            scope=["agent_evaluator/gates/gate_d_performance/"], status="active",
        )
        responses = _run_protocol([
            {"op": "init", "team_concurrency": {"claims_path": str(claims_path)}},
            {"op": "check", "task_id": "t1", "tool_name": "edit",
             "parameters": {"path": "agent_evaluator/gates/gate_d_performance/aggregate.py"}},
        ])
        assert responses[0] == {"ok": True}
        verdict = responses[1]
        assert verdict["block"] is True
        assert verdict["gate"] == "B"

    def test_team_concurrency_allows_non_overlapping_claim(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c-1", developer="other-dev",
            scope=["agent_evaluator/gates/gate_d_performance/"], status="active",
        )
        responses = _run_protocol([
            {"op": "init", "team_concurrency": {"claims_path": str(claims_path)}},
            {"op": "check", "task_id": "t1", "tool_name": "edit",
             "parameters": {"path": "agent_evaluator/gates/gate_e_security/aggregate.py"}},
        ])
        assert responses[1]["block"] is False


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
