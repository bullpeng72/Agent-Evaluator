"""
tests/test_cli_opencode.py
===========================
agent-eval opencode CLI 테스트.

커버 대상:
  - cmd_opencode: 서브커맨드 미지정 시 도움말 후 1 반환
  - _cmd_install: 프로젝트 로컬(기본)/--global 설치, 파일 내용의 PYTHON_BIN
    플레이스홀더가 sys.executable로 치환되는지, 기존 파일 존재 시 --force 없이는
    거부되고 --force면 덮어쓰는지, 번들 원본이 없을 때의 에러 처리
  - build_opencode_subparser: argparse 서브파서 등록(옵션 파싱 결과 확인)
  - --with-violation-search(SPEC-024 REQ-6): opencode mcp add 자동 등록
"""
from __future__ import annotations

import argparse
import subprocess
import sys

from agent_evaluator.cli import opencode as opencode_cli


def _ns(**kwargs):
    defaults = {
        "opencode_command": "install", "global_install": False, "force": False,
        "with_violation_search": False, "with_recommend_fix": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdOpencodeDispatch:
    def test_no_subcommand_prints_help_and_returns_1(self, capsys):
        code = opencode_cli.cmd_opencode(argparse.Namespace(opencode_command=None))
        assert code == 1
        assert "agent-eval opencode" in capsys.readouterr().err

    def test_unknown_subcommand_treated_as_missing(self, capsys):
        code = opencode_cli.cmd_opencode(argparse.Namespace(opencode_command="bogus"))
        assert code == 1


class TestInstallLocal:
    def test_install_creates_local_plugin_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        code = opencode_cli.cmd_opencode(_ns())
        assert code == 0
        target = tmp_path / ".opencode" / "plugin" / "agent-evaluator.ts"
        assert target.exists()
        out = capsys.readouterr().out
        assert "Installed" in out

    def test_python_placeholder_replaced_with_sys_executable(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        opencode_cli.cmd_opencode(_ns())
        content = (tmp_path / ".opencode" / "plugin" / "agent-evaluator.ts").read_text()
        assert opencode_cli._PYTHON_PLACEHOLDER not in content
        assert sys.executable in content

    def test_existing_file_without_force_is_rejected(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / ".opencode" / "plugin" / "agent-evaluator.ts"
        target.parent.mkdir(parents=True)
        target.write_text("# user-customized GUARDRAIL_CONFIG")

        code = opencode_cli.cmd_opencode(_ns())
        assert code == 1
        assert "already exists" in capsys.readouterr().err.lower()
        assert target.read_text() == "# user-customized GUARDRAIL_CONFIG"

    def test_existing_file_with_force_is_overwritten(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / ".opencode" / "plugin" / "agent-evaluator.ts"
        target.parent.mkdir(parents=True)
        target.write_text("# user-customized GUARDRAIL_CONFIG")

        code = opencode_cli.cmd_opencode(_ns(force=True))
        assert code == 0
        assert "GUARDRAIL_CONFIG" in target.read_text()
        assert "user-customized" not in target.read_text()


class TestInstallGlobal:
    def test_install_global_uses_global_target(self, tmp_path, monkeypatch):
        fake_global = tmp_path / "config" / "opencode" / "plugin" / "agent-evaluator.ts"
        monkeypatch.setattr(opencode_cli, "_GLOBAL_TARGET", fake_global)

        code = opencode_cli.cmd_opencode(_ns(global_install=True))
        assert code == 0
        assert fake_global.exists()


class TestBundledPluginMissing:
    def test_missing_bundled_source_returns_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(opencode_cli, "_BUNDLED_PLUGIN", tmp_path / "does-not-exist.ts")

        code = opencode_cli.cmd_opencode(_ns())
        assert code == 1
        assert "not found" in capsys.readouterr().err.lower()


class TestArgparseWiring:
    def test_install_subcommand_parses_flags(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        opencode_cli.build_opencode_subparser(sub)

        args = parser.parse_args(["opencode", "install", "--global", "--force"])
        assert args.command == "opencode"
        assert args.opencode_command == "install"
        assert args.global_install is True
        assert args.force is True

    def test_install_subcommand_defaults(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        opencode_cli.build_opencode_subparser(sub)

        args = parser.parse_args(["opencode", "install"])
        assert args.global_install is False
        assert args.force is False
        assert args.with_violation_search is False

    def test_install_subcommand_parses_with_violation_search(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        opencode_cli.build_opencode_subparser(sub)

        args = parser.parse_args(["opencode", "install", "--with-violation-search"])
        assert args.with_violation_search is True


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr


class TestWithViolationSearchMcpRegistration:
    """SPEC-024 REQ-6: --with-violation-search가 opencode mcp add를 자동 실행한다."""

    def test_flag_absent_never_calls_subprocess(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        calls = []

        def _fake_run(*args, **kwargs):
            calls.append((args, kwargs))
            return _FakeCompletedProcess(0)

        monkeypatch.setattr(opencode_cli.subprocess, "run", _fake_run)
        code = opencode_cli.cmd_opencode(_ns())
        assert code == 0
        assert calls == []

    def test_flag_present_registers_mcp_server(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        calls = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeCompletedProcess(0)

        monkeypatch.setattr(opencode_cli.subprocess, "run", _fake_run)
        code = opencode_cli.cmd_opencode(_ns(with_violation_search=True))

        assert code == 0
        assert len(calls) == 1
        cmd = calls[0]
        assert cmd[:4] == ["opencode", "mcp", "add", opencode_cli._VIOLATION_SEARCH_MCP_NAME]
        assert "--" in cmd
        assert sys.executable in cmd
        assert "agent_evaluator.integrations.violation_search_mcp" in cmd
        assert "registered" in capsys.readouterr().out.lower()

    def test_opencode_binary_missing_warns_but_still_succeeds(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        def _fake_run(cmd, **kwargs):
            raise FileNotFoundError("opencode")

        monkeypatch.setattr(opencode_cli.subprocess, "run", _fake_run)
        code = opencode_cli.cmd_opencode(_ns(with_violation_search=True))

        assert code == 0  # 플러그인 설치 자체는 성공 — MCP 등록 실패로 전체를 실패시키지 않는다
        err = capsys.readouterr().err
        assert "opencode" in err.lower()
        assert "mcp add" in err  # 수동 등록 안내 포함


class TestWithRecommendFixMcpRegistration:
    """--with-recommend-fix가 opencode mcp add를 자동 실행한다 (_register_violation_search_mcp와
    동일한 _register_mcp_server() 공유 실행부를 쓴다)."""

    def test_flag_present_registers_mcp_server(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        calls = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeCompletedProcess(0)

        monkeypatch.setattr(opencode_cli.subprocess, "run", _fake_run)
        code = opencode_cli.cmd_opencode(_ns(with_recommend_fix=True))

        assert code == 0
        assert len(calls) == 1
        cmd = calls[0]
        assert cmd[:4] == ["opencode", "mcp", "add", opencode_cli._RECOMMEND_FIX_MCP_NAME]
        assert "--" in cmd
        assert sys.executable in cmd
        assert "agent_evaluator.integrations.recommend_fix_mcp" in cmd
        assert "registered" in capsys.readouterr().out.lower()

    def test_both_flags_register_both_servers(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        calls = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeCompletedProcess(0)

        monkeypatch.setattr(opencode_cli.subprocess, "run", _fake_run)
        code = opencode_cli.cmd_opencode(
            _ns(with_violation_search=True, with_recommend_fix=True)
        )

        assert code == 0
        assert len(calls) == 2
        names = {c[3] for c in calls}
        assert names == {
            opencode_cli._VIOLATION_SEARCH_MCP_NAME,
            opencode_cli._RECOMMEND_FIX_MCP_NAME,
        }

    def test_opencode_binary_missing_warns_but_still_succeeds(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        def _fake_run(cmd, **kwargs):
            raise FileNotFoundError("opencode")

        monkeypatch.setattr(opencode_cli.subprocess, "run", _fake_run)
        code = opencode_cli.cmd_opencode(_ns(with_recommend_fix=True))

        assert code == 0
        err = capsys.readouterr().err
        assert "opencode" in err.lower()
        assert "mcp add" in err

    def test_non_zero_exit_warns_but_still_succeeds(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        def _fake_run(cmd, **kwargs):
            return _FakeCompletedProcess(1, stderr="some opencode error")

        monkeypatch.setattr(opencode_cli.subprocess, "run", _fake_run)
        code = opencode_cli.cmd_opencode(_ns(with_violation_search=True))

        assert code == 0
        err = capsys.readouterr().err
        assert "실패" in err
        assert "some opencode error" in err

    def test_timeout_warns_but_still_succeeds(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        def _fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

        monkeypatch.setattr(opencode_cli.subprocess, "run", _fake_run)
        code = opencode_cli.cmd_opencode(_ns(with_violation_search=True))

        assert code == 0
        assert "시간 초과" in capsys.readouterr().err


class TestMissingHooksCheck:
    """Harness Method Ch06 §6.2 — 훅 3개(tool.execute.before/after, event)가 전부
    등록됐는지 설치 시점에 자동 확인한다."""

    def test_no_missing_hooks_for_complete_content(self):
        content = (
            '"tool.execute.before": async (input, output) => {},\n'
            '"tool.execute.after": async (input, output) => {},\n'
            "event: async ({ event }) => {},\n"
        )
        assert opencode_cli._missing_hooks(content) == []

    def test_reports_each_missing_hook_by_name(self):
        content = '"tool.execute.before": async (input, output) => {},\n'
        missing = opencode_cli._missing_hooks(content)
        assert missing == ["tool.execute.after", "event"]

    def test_real_bundled_plugin_has_no_missing_hooks(self):
        """번들 원본 자체가 회귀로 훅을 잃지 않았는지 실제 파일로 확인."""
        content = opencode_cli._BUNDLED_PLUGIN.read_text(encoding="utf-8")
        assert opencode_cli._missing_hooks(content) == []

    def test_install_with_complete_bundled_plugin_prints_no_warning(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        code = opencode_cli.cmd_opencode(_ns())
        assert code == 0
        assert "missing hook" not in capsys.readouterr().err

    def test_install_warns_when_bundled_content_missing_a_hook(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        original = opencode_cli._BUNDLED_PLUGIN.read_text(encoding="utf-8")
        broken = original.replace('"tool.execute.after":', "// removed for test")
        broken_bundled = tmp_path / "broken-bundled.ts"
        broken_bundled.write_text(broken, encoding="utf-8")
        monkeypatch.setattr(opencode_cli, "_BUNDLED_PLUGIN", broken_bundled)

        code = opencode_cli.cmd_opencode(_ns())
        assert code == 0  # 훅 누락 경고는 설치 자체를 실패시키지 않는다
        err = capsys.readouterr().err
        assert "missing hook" in err
        assert "tool.execute.after" in err
