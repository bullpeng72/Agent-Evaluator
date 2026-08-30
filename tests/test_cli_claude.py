"""
tests/test_cli_claude.py
===========================
agent-eval claude CLI 테스트.

커버 대상:
  - cmd_claude: 서브커맨드 미지정 시 도움말 후 1 반환
  - _cmd_install: 프로젝트 로컬(기본)/--global 설치, settings.json에 세 훅(PreToolUse/
    PostToolUse/SessionEnd)이 각각 올바른 matcher로 등록되는지(SessionEnd는 "*", 나머지는
    도구 이름 matcher — 둘을 섞으면 SessionEnd가 절대 발화하지 않는 회귀가 생긴다),
    기존 settings.json의 다른 훅을 보존하는지(read-modify-write), 재설치 시 중복 추가
    안 되는지, guardrail_config.json의 --force 보호
  - build_claude_subparser: argparse 서브파서 등록(옵션 파싱 결과 확인)
  - --with-violation-search/--with-recommend-fix: claude mcp add 자동 등록
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

from agent_evaluator.cli import claude as claude_cli


def _ns(**kwargs):
    defaults = {
        "claude_command": "install", "global_install": False, "force": False,
        "with_violation_search": False, "with_recommend_fix": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdClaudeDispatch:
    def test_no_subcommand_prints_help_and_returns_1(self, capsys):
        code = claude_cli.cmd_claude(argparse.Namespace(claude_command=None))
        assert code == 1
        assert "agent-eval claude" in capsys.readouterr().err

    def test_unknown_subcommand_treated_as_missing(self, capsys):
        code = claude_cli.cmd_claude(argparse.Namespace(claude_command="bogus"))
        assert code == 1


class TestInstallLocal:
    def test_install_creates_settings_and_config(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        code = claude_cli.cmd_claude(_ns())
        assert code == 0
        assert (tmp_path / ".claude" / "settings.json").exists()
        assert (tmp_path / ".claude" / ".agent-evaluator" / "guardrail_config.json").exists()
        out = capsys.readouterr().out
        assert "Registered hooks" in out

    def test_all_three_events_registered_with_correct_matchers(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        hooks = settings["hooks"]
        assert set(hooks) == {"PreToolUse", "PostToolUse", "SessionEnd"}
        # SessionEnd's matcher filters by session-end *reason*, not tool name — reusing the
        # tool-name matcher there would make the batch-save hook never fire.
        assert hooks["SessionEnd"][0]["matcher"] == "*"
        # SPEC-041: fully-anchored tool-name matcher. Behaves the same under
        # re.search/re.match/re.fullmatch. Verify with realistic Claude Code tool names.
        pre_matcher = hooks["PreToolUse"][0]["matcher"]
        assert hooks["PostToolUse"][0]["matcher"] == pre_matcher
        should_match = [
            "Bash", "Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch",
            "mcp__filesystem__write_file", "mcp__filesystem__edit_file",
            "mcp__filesystem__move_file", "mcp__git__create_branch",
            "mcp__claude_ai_Google_Drive__update_file",
        ]
        should_not_match = [
            "Read", "Glob", "Grep", "Task", "TodoWrite", "BashOutput", "KillShell",
            "ExitPlanMode", "WebSearch",
            "mcp__ctx__search", "mcp__ctx__sql", "mcp__x__list_dir",
            "mcp__claude_ai_Gmail__send_message", "mcp__foo__dispatch_event",
        ]
        for name in should_match:
            assert re.search(pre_matcher, name), f"expected match: {name}"
        for name in should_not_match:
            assert not re.search(pre_matcher, name), f"unexpected match: {name}"

    def test_hook_command_bakes_in_python_executable(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert sys.executable in cmd
        assert "agent_evaluator.integrations.claude_code_hook" in cmd

    def test_reinstall_does_not_duplicate_hook_entries(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        claude_cli.cmd_claude(_ns())
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert len(settings["hooks"]["PreToolUse"]) == 1

    def test_reinstall_refreshes_stale_matcher_only(self, tmp_path, monkeypatch):
        """SPEC-041: 우리 훅이 이미 있고 matcher만 옛 값이면, matcher만 갱신하고
        command·다른 훅은 건드리지 않는다."""
        monkeypatch.chdir(tmp_path)
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        our_cmd = f"{sys.executable} -m agent_evaluator.integrations.claude_code_hook"
        stale = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "OTHER", "hooks": [{"type": "command", "command": "keep-me.sh"}]},
                    {"matcher": "Bash|Edit|Write",
                     "hooks": [{"type": "command", "command": our_cmd}]},
                ],
            },
        }
        (settings_dir / "settings.json").write_text(json.dumps(stale))

        assert claude_cli.cmd_claude(_ns()) == 0
        settings = json.loads((settings_dir / "settings.json").read_text())
        pre = settings["hooks"]["PreToolUse"]
        assert len(pre) == 2  # 중복 추가 없음
        our = [e for e in pre if any(our_cmd in h["command"] for h in e["hooks"])][0]
        other = [e for e in pre if any("keep-me.sh" in h["command"] for h in e["hooks"])][0]
        assert our["matcher"] == claude_cli._TOOL_MATCHER  # 갱신됨
        assert other["matcher"] == "OTHER"                  # 남의 훅은 그대로

    def test_reinstall_refreshes_stale_interpreter_in_canonical_command(self, tmp_path, monkeypatch):
        """SPEC-041: 우리 훅의 커맨드가 정확한 canonical 형태
        ("<python> -m agent_evaluator.integrations.claude_code_hook")인데 인터프리터
        경로만 죽은 옛 venv면, 재설치 시 현재 인터프리터로 갱신한다. 래핑된
        커맨드(추가 인자 등)는 사용자 의도로 보고 건드리지 않는다."""
        monkeypatch.chdir(tmp_path)
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        mod = "agent_evaluator.integrations.claude_code_hook"
        stale = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": claude_cli._TOOL_MATCHER,
                     "hooks": [{"type": "command", "command": f"/dead/venv/bin/python -m {mod}"}]},
                ],
                "PostToolUse": [
                    {"matcher": claude_cli._TOOL_MATCHER,
                     "hooks": [{"type": "command", "command": f"nice /dead/python -m {mod} --flag"}]},
                ],
            },
        }
        (settings_dir / "settings.json").write_text(json.dumps(stale))
        assert claude_cli.cmd_claude(_ns()) == 0
        settings = json.loads((settings_dir / "settings.json").read_text())
        pre_cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        post_cmd = settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert pre_cmd == f"{sys.executable} -m {mod}"          # canonical → refreshed
        assert post_cmd == f"nice /dead/python -m {mod} --flag"  # wrapped → untouched

    def test_preserves_existing_unrelated_hooks(self, tmp_path, monkeypatch):
        """settings.json에 이미 사용자의 다른 훅이 있으면 지우지 않고 보존해야 한다."""
        monkeypatch.chdir(tmp_path)
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        existing = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Write",
                        "hooks": [{"type": "command", "command": "my-other-tool.sh"}],
                    },
                ],
            },
            "someOtherSetting": True,
        }
        (settings_dir / "settings.json").write_text(json.dumps(existing))

        code = claude_cli.cmd_claude(_ns())
        assert code == 0
        settings = json.loads((settings_dir / "settings.json").read_text())
        assert settings["someOtherSetting"] is True
        pre_entries = settings["hooks"]["PreToolUse"]
        assert len(pre_entries) == 2
        commands = [h["command"] for e in pre_entries for h in e["hooks"]]
        assert "my-other-tool.sh" in commands

    def test_malformed_existing_settings_json_returns_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text("{not valid json")

        code = claude_cli.cmd_claude(_ns())
        assert code == 1
        assert "Failed to parse" in capsys.readouterr().err

    def test_existing_config_without_force_is_preserved(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".claude" / ".agent-evaluator"
        config_dir.mkdir(parents=True)
        (config_dir / "guardrail_config.json").write_text('{"custom": true}')

        code = claude_cli.cmd_claude(_ns())
        assert code == 0
        assert "already exists" in capsys.readouterr().out.lower()
        assert json.loads((config_dir / "guardrail_config.json").read_text()) == {"custom": True}

    def test_existing_config_with_force_is_overwritten(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".claude" / ".agent-evaluator"
        config_dir.mkdir(parents=True)
        (config_dir / "guardrail_config.json").write_text('{"custom": true}')

        code = claude_cli.cmd_claude(_ns(force=True))
        assert code == 0
        content = json.loads((config_dir / "guardrail_config.json").read_text())
        assert content == claude_cli.DEFAULT_GUARDRAIL_CONFIG


class TestInstallGlobal:
    def test_install_global_uses_global_targets(self, tmp_path, monkeypatch):
        fake_settings = tmp_path / "home" / ".claude" / "settings.json"
        fake_config = tmp_path / "home" / ".claude" / ".agent-evaluator" / "guardrail_config.json"
        monkeypatch.setattr(claude_cli, "_GLOBAL_SETTINGS", fake_settings)
        monkeypatch.setattr(claude_cli, "_GLOBAL_CONFIG", fake_config)

        code = claude_cli.cmd_claude(_ns(global_install=True))
        assert code == 0
        assert fake_settings.exists()
        assert fake_config.exists()


class TestArgparseWiring:
    def test_install_subcommand_parses_flags(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        claude_cli.build_claude_subparser(sub)

        args = parser.parse_args(["claude", "install", "--global", "--force"])
        assert args.command == "claude"
        assert args.claude_command == "install"
        assert args.global_install is True
        assert args.force is True

    def test_install_subcommand_defaults(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        claude_cli.build_claude_subparser(sub)

        args = parser.parse_args(["claude", "install"])
        assert args.global_install is False
        assert args.force is False
        assert args.with_violation_search is False

    def test_install_subcommand_parses_with_violation_search(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        claude_cli.build_claude_subparser(sub)

        args = parser.parse_args(["claude", "install", "--with-violation-search"])
        assert args.with_violation_search is True


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr


class TestWithViolationSearchMcpRegistration:
    def test_flag_absent_never_calls_subprocess(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        calls = []

        def _fake_run(*args, **kwargs):
            calls.append((args, kwargs))
            return _FakeCompletedProcess(0)

        monkeypatch.setattr(claude_cli.subprocess, "run", _fake_run)
        code = claude_cli.cmd_claude(_ns())
        assert code == 0
        assert calls == []

    def test_flag_present_registers_mcp_server_with_local_scope(
        self, tmp_path, monkeypatch, capsys,
    ):
        monkeypatch.chdir(tmp_path)
        calls = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeCompletedProcess(0)

        monkeypatch.setattr(claude_cli.subprocess, "run", _fake_run)
        code = claude_cli.cmd_claude(_ns(with_violation_search=True))

        assert code == 0
        assert len(calls) == 1
        cmd = calls[0]
        assert cmd[:4] == ["claude", "mcp", "add", claude_cli._VIOLATION_SEARCH_MCP_NAME]
        assert "--scope" in cmd
        assert cmd[cmd.index("--scope") + 1] == "local"
        assert "--" in cmd
        assert sys.executable in cmd
        assert "agent_evaluator.integrations.violation_search_mcp" in cmd
        assert "registered" in capsys.readouterr().out.lower()

    def test_global_install_uses_user_scope(self, tmp_path, monkeypatch):
        fake_settings = tmp_path / "settings.json"
        fake_config = tmp_path / "guardrail_config.json"
        monkeypatch.setattr(claude_cli, "_GLOBAL_SETTINGS", fake_settings)
        monkeypatch.setattr(claude_cli, "_GLOBAL_CONFIG", fake_config)
        calls = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeCompletedProcess(0)

        monkeypatch.setattr(claude_cli.subprocess, "run", _fake_run)
        claude_cli.cmd_claude(_ns(global_install=True, with_violation_search=True))

        cmd = calls[0]
        assert cmd[cmd.index("--scope") + 1] == "user"

    def test_claude_binary_missing_warns_but_still_succeeds(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        def _fake_run(cmd, **kwargs):
            raise FileNotFoundError("claude")

        monkeypatch.setattr(claude_cli.subprocess, "run", _fake_run)
        code = claude_cli.cmd_claude(_ns(with_violation_search=True))

        assert code == 0
        err = capsys.readouterr().err
        assert "claude" in err.lower()
        assert "mcp add" in err


class TestWithRecommendFixMcpRegistration:
    def test_flag_present_registers_mcp_server(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        calls = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeCompletedProcess(0)

        monkeypatch.setattr(claude_cli.subprocess, "run", _fake_run)
        code = claude_cli.cmd_claude(_ns(with_recommend_fix=True))

        assert code == 0
        assert len(calls) == 1
        cmd = calls[0]
        assert cmd[:4] == ["claude", "mcp", "add", claude_cli._RECOMMEND_FIX_MCP_NAME]
        assert "agent_evaluator.integrations.recommend_fix_mcp" in cmd
        assert "registered" in capsys.readouterr().out.lower()

    def test_both_flags_register_both_servers(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        calls = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeCompletedProcess(0)

        monkeypatch.setattr(claude_cli.subprocess, "run", _fake_run)
        code = claude_cli.cmd_claude(_ns(with_violation_search=True, with_recommend_fix=True))

        assert code == 0
        assert len(calls) == 2
        names = {c[3] for c in calls}
        assert names == {claude_cli._VIOLATION_SEARCH_MCP_NAME, claude_cli._RECOMMEND_FIX_MCP_NAME}

    def test_non_zero_exit_warns_but_still_succeeds(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        def _fake_run(cmd, **kwargs):
            return _FakeCompletedProcess(1, stderr="some claude error")

        monkeypatch.setattr(claude_cli.subprocess, "run", _fake_run)
        code = claude_cli.cmd_claude(_ns(with_violation_search=True))

        assert code == 0
        err = capsys.readouterr().err
        assert "failed" in err
        assert "some claude error" in err

    def test_timeout_warns_but_still_succeeds(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        def _fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

        monkeypatch.setattr(claude_cli.subprocess, "run", _fake_run)
        code = claude_cli.cmd_claude(_ns(with_violation_search=True))

        assert code == 0
        assert "timed out" in capsys.readouterr().err

    def test_already_exists_is_reported_as_no_change_not_a_warning(
        self, tmp_path, monkeypatch, capsys,
    ):
        """SPEC: 재설치/업그레이드 시 'already exists'는 정상 — ⚠️ + 수동 명령이 아니라
        조용한 'nothing to change'로 출력한다."""
        monkeypatch.chdir(tmp_path)

        def _fake_run(cmd, **kwargs):
            return _FakeCompletedProcess(1, stderr="MCP server foo already exists in config")

        monkeypatch.setattr(claude_cli.subprocess, "run", _fake_run)
        code = claude_cli.cmd_claude(_ns(with_violation_search=True))

        assert code == 0
        out, err = capsys.readouterr()
        assert "already registered" in out
        assert "failed" not in err
        assert "mcp add" not in err


def _uni_ns(**kwargs):
    defaults = {
        "claude_command": "uninstall", "global_install": False,
        "keep_config": False, "purge": False, "dry_run": False, "yes": True,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _upg_ns(**kwargs):
    defaults = {
        "claude_command": "upgrade", "global_install": False,
        "with_violation_search": False, "with_recommend_fix": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _doc_ns(**kwargs):
    defaults = {
        "claude_command": "doctor", "global_install": False,
        "json": False, "no_live": True, "strict": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestUpgrade:
    def test_no_install_returns_1(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert claude_cli.cmd_claude(_upg_ns()) == 1
        assert "No existing install" in capsys.readouterr().err

    def test_refreshes_stale_matcher_and_keeps_config_edits(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        # 설치 후 옛 matcher + 사용자 편집 + 기본 키 하나 제거로 "구버전" 시뮬레이션
        claude_cli.cmd_claude(_ns())
        sp = tmp_path / ".claude" / "settings.json"
        s = json.loads(sp.read_text())
        for ev in ("PreToolUse", "PostToolUse"):
            s["hooks"][ev][0]["matcher"] = "Bash|Edit|Write"
        sp.write_text(json.dumps(s))
        cp = tmp_path / ".claude" / ".agent-evaluator" / "guardrail_config.json"
        c = json.loads(cp.read_text())
        c["loop_detection"]["consecutive_repeat_threshold"] = 99
        c.pop("live_loop_window", None)
        cp.write_text(json.dumps(c))

        # MCP 등록 조회는 하지 않도록 (플래그 없음)
        assert claude_cli.cmd_claude(_upg_ns()) == 0

        s2 = json.loads(sp.read_text())
        assert s2["hooks"]["PreToolUse"][0]["matcher"] == claude_cli._TOOL_MATCHER
        c2 = json.loads(cp.read_text())
        assert c2["loop_detection"]["consecutive_repeat_threshold"] == 99  # 사용자 값 보존
        assert c2["live_loop_window"] == 15  # 빠졌던 기본 키 복원
        assert "Added 1 new default key" in capsys.readouterr().out

    def test_invalid_config_json_is_left_untouched(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        cp = tmp_path / ".claude" / ".agent-evaluator" / "guardrail_config.json"
        cp.write_text("{not json")
        assert claude_cli.cmd_claude(_upg_ns()) == 0
        assert cp.read_text() == "{not json"
        assert "not valid JSON" in capsys.readouterr().err


class TestUninstall:
    def test_removes_only_our_hooks_keeps_others(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        sp = tmp_path / ".claude" / "settings.json"
        sp.parent.mkdir()
        sp.write_text(json.dumps({
            "hooks": {"PreToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": "keep.sh"}]},
            ]},
            "other": 1,
        }))
        claude_cli.cmd_claude(_ns())  # adds our hooks alongside keep.sh
        monkeypatch.setattr(claude_cli, "_deregister_mcp_server", lambda *a, **k: None)

        assert claude_cli.cmd_claude(_uni_ns()) == 0
        s = json.loads(sp.read_text())
        assert s["other"] == 1
        cmds = [h["command"] for e in s["hooks"].get("PreToolUse", []) for h in e["hooks"]]
        assert cmds == ["keep.sh"]
        assert "PostToolUse" not in s["hooks"]  # 우리만 있던 이벤트는 제거
        assert not (tmp_path / ".claude" / ".agent-evaluator" / "guardrail_config.json").exists()

    def test_keep_config_preserves_guardrail_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        monkeypatch.setattr(claude_cli, "_deregister_mcp_server", lambda *a, **k: None)
        cp = tmp_path / ".claude" / ".agent-evaluator" / "guardrail_config.json"
        assert claude_cli.cmd_claude(_uni_ns(keep_config=True)) == 0
        assert cp.exists()

    def test_dry_run_changes_nothing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        sp = tmp_path / ".claude" / "settings.json"
        before = sp.read_text()
        called = []
        monkeypatch.setattr(claude_cli, "_deregister_mcp_server", lambda *a, **k: called.append(a))
        assert claude_cli.cmd_claude(_uni_ns(dry_run=True)) == 0
        assert sp.read_text() == before
        assert called == []
        assert "dry-run" in capsys.readouterr().out

    def test_purge_deletes_state_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        monkeypatch.setattr(claude_cli, "_deregister_mcp_server", lambda *a, **k: None)
        state = tmp_path / ".claude" / ".agent-evaluator"
        (state / "sessions").mkdir(parents=True, exist_ok=True)
        (state / "sessions" / "x.json").write_text("{}")
        assert claude_cli.cmd_claude(_uni_ns(purge=True)) == 0
        assert not state.exists()


class TestDoctorStatic:
    def test_missing_settings_is_error_exit_1(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        # isolate from any real ~/.claude/settings.json so the local->global fallback finds nothing
        monkeypatch.setattr(claude_cli, "_GLOBAL_SETTINGS", tmp_path / "nope" / "settings.json")
        assert claude_cli.cmd_claude(_doc_ns()) == 1
        out = capsys.readouterr().out
        assert "settings.json exists" in out
        assert "❌" in out

    def test_missing_local_settings_falls_back_to_global(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        gs = tmp_path / "home" / ".claude" / "settings.json"
        gc = tmp_path / "home" / ".claude" / ".agent-evaluator" / "guardrail_config.json"
        monkeypatch.setattr(claude_cli, "_GLOBAL_SETTINGS", gs)
        monkeypatch.setattr(claude_cli, "_GLOBAL_CONFIG", gc)
        claude_cli.cmd_claude(_ns(global_install=True))  # create the global install
        monkeypatch.setattr(claude_cli, "_mcp_is_registered", lambda name: False)
        capsys.readouterr()
        code = claude_cli.cmd_claude(_doc_ns())  # no --global
        out = capsys.readouterr().out
        assert code == 0
        assert "global — no project-local" in out

    def test_healthy_install_passes(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        # MCP 조회를 오프라인으로
        monkeypatch.setattr(claude_cli, "_mcp_is_registered", lambda name: False)
        assert claude_cli.cmd_claude(_doc_ns()) == 0
        out = capsys.readouterr().out
        assert "hooks registered" in out
        assert "guardrail_config builds" in out
        assert "all checks passed" in out

    def test_stale_matcher_is_a_warning(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        sp = tmp_path / ".claude" / "settings.json"
        s = json.loads(sp.read_text())
        s["hooks"]["PreToolUse"][0]["matcher"] = "Bash|Edit|Write"
        sp.write_text(json.dumps(s))
        monkeypatch.setattr(claude_cli, "_mcp_is_registered", lambda name: False)
        assert claude_cli.cmd_claude(_doc_ns()) == 0  # 경고는 exit 0
        assert claude_cli.cmd_claude(_doc_ns(strict=True)) == 1  # --strict면 1
        assert "drift" in capsys.readouterr().out

    def test_json_output_is_valid(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        monkeypatch.setattr(claude_cli, "_mcp_is_registered", lambda name: None)
        capsys.readouterr()  # drain install output
        claude_cli.cmd_claude(_doc_ns(json=True))
        data = json.loads(capsys.readouterr().out)
        assert data["summary"]["errors"] == 0
        assert {c["label"] for c in data["checks"]} >= {"settings.json parses", "hooks registered"}


class TestDoctorLive:
    def test_live_roundtrip_allow_and_block(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        claude_cli.cmd_claude(_ns())
        monkeypatch.setattr(claude_cli, "_mcp_is_registered", lambda name: False)
        code = claude_cli.cmd_claude(_doc_ns(no_live=False))
        out = capsys.readouterr().out
        assert "allow: benign Bash → allow" in out
        assert "block: rm -rf → deny (exit 2)" in out
        assert "batch report written" in out
        assert code == 0
