"""
tests/test_claude_code_hook.py
=================================
agent_evaluator.integrations.claude_code_hook 테스트.

커버 대상:
  - handle_pre_tool_use: 허용/차단 판정, 차단 시 감사 이력 파일 기록
  - handle_post_tool_use: 확정 tool_call을 세션 상태 파일에 기록 (success/error → stdout/stderr)
  - handle_session_end: 이력 재생 → 배치 저장(record_and_save) → 상태 파일 정리
  - run(): hook_event_name 기반 디스패치, 알 수 없는 이벤트/손상된 입력에도 fail-open
  - load_config: 설정 파일 없음/손상 시 DEFAULT_GUARDRAIL_CONFIG 폴백
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from agent_evaluator.integrations import claude_code_hook as hook


def _state_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".claude" / ".agent-evaluator"
    d.mkdir(parents=True)
    return d


class TestLoadConfig:
    def test_missing_file_falls_back_to_default(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        assert hook.load_config(state_dir) == hook.DEFAULT_GUARDRAIL_CONFIG

    def test_corrupt_file_falls_back_to_default(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        (state_dir / "guardrail_config.json").write_text("{not valid json")
        assert hook.load_config(state_dir) == hook.DEFAULT_GUARDRAIL_CONFIG

    def test_valid_file_is_read(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        custom = {"loop_detection": {"consecutive_repeat_threshold": 2}}
        (state_dir / "guardrail_config.json").write_text(json.dumps(custom))
        assert hook.load_config(state_dir) == custom


class TestHandlePreToolUse:
    def test_allows_benign_call(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        payload = {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "ls -la"}}
        result = hook.handle_pre_tool_use(payload, state_dir)
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_blocks_dangerous_command_and_records_audit_trail(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        payload = {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
        result = hook.handle_pre_tool_use(payload, state_dir)

        out = result["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        assert out["permissionDecisionReason"]

        blocked = hook._load_json_list(hook._blocked_file(state_dir, "s1"))
        assert len(blocked) == 1
        assert blocked[0]["tool_name"] == "Bash"
        assert blocked[0]["gate"] == "B"

    def test_tool_authorization_backstop_catches_pattern_gate_b_misses(self, tmp_path):
        """"sudo" isn't in DEFAULT_GUARDRAIL_CONFIG's tool_parameter_safety.dangerous_patterns
        (Gate B), but it IS in ToolAuthorizationTracker's hardcoded list (Gate E) — this proves
        the "tool_authorization": {} default (added to close the AOO/AC parity gap: AOO's
        GUARDRAIL_CONFIG always had this key, AC's DEFAULT_GUARDRAIL_CONFIG didn't) is actually
        wired in and blocking, not just present without effect."""
        state_dir = _state_dir(tmp_path)
        payload = {
            "session_id": "s1", "tool_name": "Bash",
            "tool_input": {"command": "sudo systemctl restart nginx"},
        }
        result = hook.handle_pre_tool_use(payload, state_dir)

        out = result["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        blocked = hook._load_json_list(hook._blocked_file(state_dir, "s1"))
        assert blocked[0]["gate"] == "E"

    def test_loop_detection_uses_replayed_history(self, tmp_path):
        """이전에 확정된 호출 이력이 파일에서 재생되어 루프 판정에 반영돼야 한다."""
        state_dir = _state_dir(tmp_path)
        (state_dir / "guardrail_config.json").write_text(json.dumps({
            "loop_detection": {"consecutive_repeat_threshold": 2, "on_loop_detected": "fail"},
        }))
        session_file = hook._session_file(state_dir, "s1")
        # 이미 동일 도구가 1회 확정 기록된 상태를 흉내낸다.
        hook._append_json_list(
            session_file, {"tool_name": "Bash", "parameters": {}, "output": None},
        )

        payload = {"session_id": "s1", "tool_name": "Bash", "tool_input": {}}
        result = hook.handle_pre_tool_use(payload, state_dir)
        # threshold=2, 이미 1회 + 이번 후보 1회 = 2연속 → 루프 감지되어 차단
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestHandlePostToolUse:
    def test_records_successful_call_with_stdout(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        payload = {
            "session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "ls"},
            "tool_result": {"type": "success", "content": "file1\nfile2"},
        }
        result = hook.handle_post_tool_use(payload, state_dir)
        assert result == {}

        records = hook._load_json_list(hook._session_file(state_dir, "s1"))
        assert len(records) == 1
        assert records[0]["tool_name"] == "Bash"
        assert records[0]["output"]["success"] is True
        assert records[0]["output"]["stdout"] == "file1\nfile2"

    def test_records_failed_call_with_stderr(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        payload = {
            "session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "false"},
            "tool_result": {"type": "error", "content": "command failed"},
        }
        hook.handle_post_tool_use(payload, state_dir)
        records = hook._load_json_list(hook._session_file(state_dir, "s1"))
        assert records[0]["output"]["success"] is False
        assert records[0]["output"]["stderr"] == "command failed"

    def test_missing_tool_result_records_none_output(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        payload = {"session_id": "s1", "tool_name": "Bash", "tool_input": {}}
        hook.handle_post_tool_use(payload, state_dir)
        records = hook._load_json_list(hook._session_file(state_dir, "s1"))
        assert records[0]["output"] is None

    def test_multiple_calls_accumulate(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        for i in range(3):
            hook.handle_post_tool_use(
                {"session_id": "s1", "tool_name": "Bash", "tool_input": {"n": i}}, state_dir,
            )
        records = hook._load_json_list(hook._session_file(state_dir, "s1"))
        assert len(records) == 3


class TestHandleSessionEnd:
    def test_saves_batch_report_and_cleans_up_state(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        output_dir = str(tmp_path / "results")
        (state_dir / "guardrail_config.json").write_text(json.dumps({
            "tool_parameter_safety": {"fail_on_dangerous": True},
            "output_dir": output_dir,
        }))
        session_file = hook._session_file(state_dir, "s1")
        hook._append_json_list(
            session_file, {"tool_name": "Bash", "parameters": {"command": "ls"}, "output": None},
        )
        blocked_file = hook._blocked_file(state_dir, "s1")
        hook._append_json_list(
            blocked_file, {"tool_name": "Bash", "gate": "B", "reason": "dangerous"},
        )

        result = hook.handle_session_end({"session_id": "s1", "reason": "clear"}, state_dir)

        assert result["ok"] is True
        assert not session_file.exists()
        assert not blocked_file.exists()

    def test_cleanup_does_not_error_when_files_absent(self, tmp_path):
        state_dir = _state_dir(tmp_path)
        output_dir = str(tmp_path / "results")
        (state_dir / "guardrail_config.json").write_text(json.dumps({"output_dir": output_dir}))
        result = hook.handle_session_end({"session_id": "no-history", "reason": "clear"}, state_dir)
        assert result["ok"] is True


class TestRunDispatch:
    def test_unknown_hook_event_returns_empty_result(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        payload = {"hook_event_name": "Notification", "cwd": str(tmp_path)}
        instream = io.StringIO(json.dumps(payload))
        outstream = io.StringIO()
        hook.run(instream, outstream)
        assert json.loads(outstream.getvalue()) == {}

    def test_empty_stdin_returns_empty_result(self):
        outstream = io.StringIO()
        hook.run(io.StringIO(""), outstream)
        assert json.loads(outstream.getvalue()) == {}

    def test_malformed_json_fails_open_not_crash(self):
        outstream = io.StringIO()
        hook.run(io.StringIO("{not valid"), outstream)
        result = json.loads(outstream.getvalue())
        assert "error" in result

    def test_missing_required_field_fails_open_not_crash(self, tmp_path):
        """PreToolUse인데 tool_name이 없는 등 KeyError가 나도 예외를 올리지 않는다."""
        outstream = io.StringIO()
        payload = {"hook_event_name": "PreToolUse", "session_id": "s1", "cwd": str(tmp_path)}
        hook.run(io.StringIO(json.dumps(payload)), outstream)
        result = json.loads(outstream.getvalue())
        assert "error" in result

    def test_pre_tool_use_dispatches_and_allows(self, tmp_path):
        outstream = io.StringIO()
        payload = {
            "hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Bash",
            "tool_input": {"command": "ls"}, "cwd": str(tmp_path),
        }
        hook.run(io.StringIO(json.dumps(payload)), outstream)
        result = json.loads(outstream.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_full_lifecycle_pre_post_sessionend(self, tmp_path):
        """PreToolUse(허용) → PostToolUse(기록) → SessionEnd(배치 저장) 전체 흐름."""
        cwd = str(tmp_path)
        config_dir = tmp_path / ".claude" / ".agent-evaluator"
        config_dir.mkdir(parents=True)
        (config_dir / "guardrail_config.json").write_text(
            json.dumps({"output_dir": str(tmp_path / "results")})
        )

        def _call(payload):
            out = io.StringIO()
            hook.run(io.StringIO(json.dumps(payload)), out)
            return json.loads(out.getvalue())

        pre = _call({
            "hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Bash",
            "tool_input": {"command": "ls"}, "cwd": cwd,
        })
        assert pre["hookSpecificOutput"]["permissionDecision"] == "allow"

        post = _call({
            "hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Bash",
            "tool_input": {"command": "ls"}, "tool_result": {"type": "success", "content": "ok"},
            "cwd": cwd,
        })
        assert post == {}

        end = _call({
            "hook_event_name": "SessionEnd", "session_id": "s1", "reason": "clear", "cwd": cwd,
        })
        assert end["ok"] is True
        assert not (config_dir / "sessions" / "s1.json").exists()
