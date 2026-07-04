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
"""
from __future__ import annotations

import argparse
import sys

from agent_evaluator.cli import opencode as opencode_cli


def _ns(**kwargs):
    defaults = {"opencode_command": "install", "global_install": False, "force": False}
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
