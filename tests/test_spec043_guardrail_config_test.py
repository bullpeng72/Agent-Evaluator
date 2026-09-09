"""
tests/test_spec043_guardrail_config_test.py
===========================================
SPEC-043 REQ-6a — ``agent-eval {claude,opencode} test-config <cases.yaml>``.

Covers the shared helper (``load_config_cases`` / ``run_config_tests`` /
``cmd_test_config_common``) and the two CLI wirings.
"""
from __future__ import annotations

import json

import pytest

from agent_evaluator.cli._integration_health import (
    cmd_test_config_common,
    load_config_cases,
    run_config_tests,
)

_FORBID_CFG = {"scope": {"forbidden_tools": ["WebFetch"], "fail_on_violation": True}}


# --------------------------------------------------------------------------- #
# load_config_cases
# --------------------------------------------------------------------------- #
class TestLoadConfigCases:
    def test_missing_file_raises_valueerror(self):
        with pytest.raises(ValueError, match="not found"):
            load_config_cases("/no/such/file.yaml")

    def test_json_cases_list_under_key(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"cases": [
            {"tool": "WebFetch", "args": {"url": "x"}, "expect": "deny", "gate": "b"},
        ]}))
        cases = load_config_cases(str(p))
        assert len(cases) == 1
        assert cases[0]["tool"] == "WebFetch"
        assert cases[0]["gate"] == "B"          # upper-cased
        assert cases[0]["name"] == "WebFetch"   # defaults to tool

    def test_bare_top_level_list(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps([{"tool": "Read", "expect": "allow"}]))
        cases = load_config_cases(str(p))
        assert cases[0]["args"] == {}

    def test_empty_cases_returns_empty_list(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"cases": []}))
        assert load_config_cases(str(p)) == []

    def test_missing_tool_or_expect_raises(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"cases": [{"tool": "Read"}]}))
        with pytest.raises(ValueError, match="expect: allow|deny"):
            load_config_cases(str(p))

    def test_bad_expect_value_raises(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"cases": [{"tool": "Read", "expect": "maybe"}]}))
        with pytest.raises(ValueError):
            load_config_cases(str(p))

    def test_yaml_extension_without_pyyaml_falls_back_to_json(self, tmp_path):
        # valid JSON content in a .yaml file always parses (yaml is a superset)
        p = tmp_path / "c.yaml"
        p.write_text(json.dumps({"cases": [{"tool": "Read", "expect": "allow"}]}))
        assert len(load_config_cases(str(p))) == 1

    def test_malformed_json_raises_valueerror(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text("{not json")
        with pytest.raises(ValueError, match="not valid JSON"):
            load_config_cases(str(p))


# --------------------------------------------------------------------------- #
# run_config_tests
# --------------------------------------------------------------------------- #
class TestRunConfigTests:
    def test_forbidden_tool_denied_with_gate(self):
        cases = [{"name": "wf", "tool": "WebFetch", "args": {"url": "x"},
                  "expect": "deny", "gate": "B"}]
        rows, ok, skipped = run_config_tests(_FORBID_CFG, cases)
        assert ok is True and skipped == []
        assert rows[0]["actual"] == "deny"
        assert rows[0]["gate_actual"] == "B"

    def test_expectation_mismatch_marks_row_failed(self):
        cases = [{"name": "x", "tool": "WebFetch", "args": {}, "expect": "allow",
                  "gate": None}]
        rows, ok, _ = run_config_tests(_FORBID_CFG, cases)
        assert ok is False
        assert rows[0]["expect"] == "allow" and rows[0]["actual"] == "deny"

    def test_gate_mismatch_fails_even_when_block_matches(self):
        cases = [{"name": "x", "tool": "WebFetch", "args": {}, "expect": "deny",
                  "gate": "E"}]
        rows, ok, _ = run_config_tests(_FORBID_CFG, cases)
        assert ok is False
        assert rows[0]["gate_expect"] == "E" and rows[0]["gate_actual"] == "B"

    def test_empty_config_allows_everything(self):
        cases = [{"name": "x", "tool": "WebFetch", "args": {}, "expect": "allow",
                  "gate": None}]
        rows, ok, skipped = run_config_tests({}, cases)
        assert ok is True and skipped == []

    def test_typo_config_block_surfaced_as_skipped(self):
        bad = {"loop_detection": {"consecutive_repeat_treshold": 3}}
        cases = [{"name": "x", "tool": "Read", "args": {}, "expect": "allow",
                  "gate": None}]
        _, _, skipped = run_config_tests(bad, cases)
        assert skipped and "loop_detection" in skipped[0]

    def test_no_cases_all_ok(self):
        rows, ok, skipped = run_config_tests(_FORBID_CFG, [])
        assert rows == [] and ok is True


# --------------------------------------------------------------------------- #
# cmd_test_config_common
# --------------------------------------------------------------------------- #
class TestCmdTestConfigCommon:
    def _cases_file(self, tmp_path, cases):
        p = tmp_path / "cases.json"
        p.write_text(json.dumps({"cases": cases}))
        return str(p)

    def test_all_pass_exit_0(self, tmp_path, capsys):
        f = self._cases_file(tmp_path, [
            {"tool": "WebFetch", "args": {"url": "x"}, "expect": "deny"},
        ])
        rc = cmd_test_config_common(f, _FORBID_CFG, as_json=False, color=False)
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_mismatch_exit_1(self, tmp_path, capsys):
        f = self._cases_file(tmp_path, [
            {"tool": "WebFetch", "args": {}, "expect": "allow"},
        ])
        rc = cmd_test_config_common(f, _FORBID_CFG, as_json=False, color=False)
        assert rc == 1
        assert "FAIL" in capsys.readouterr().out

    def test_empty_file_exit_0(self, tmp_path):
        f = self._cases_file(tmp_path, [])
        assert cmd_test_config_common(f, _FORBID_CFG, as_json=False, color=False) == 0

    def test_missing_file_exit_1(self, tmp_path, capsys):
        rc = cmd_test_config_common(str(tmp_path / "nope.yaml"), {},
                                    as_json=False, color=False)
        assert rc == 1
        assert "error:" in capsys.readouterr().out

    def test_json_output_shape(self, tmp_path, capsys):
        f = self._cases_file(tmp_path, [
            {"tool": "WebFetch", "args": {"url": "x"}, "expect": "deny"},
        ])
        cmd_test_config_common(f, _FORBID_CFG, as_json=True, color=False)
        payload = json.loads(capsys.readouterr().out)
        assert payload["passed"] is True
        assert payload["n_cases"] == 1
        assert payload["cases"][0]["ok"] is True
        assert "skipped_config_blocks" in payload

    def test_skipped_block_warning_printed(self, tmp_path, capsys):
        f = self._cases_file(tmp_path, [
            {"tool": "Read", "args": {}, "expect": "allow"},
        ])
        bad = {"loop_detection": {"consecutive_repeat_treshold": 3}}
        cmd_test_config_common(f, bad, as_json=False, color=False)
        out = capsys.readouterr().out
        assert "PARTIAL config" in out


# --------------------------------------------------------------------------- #
# CLI wiring
# --------------------------------------------------------------------------- #
class TestCliWiring:
    def test_claude_test_config_dispatches(self, tmp_path, monkeypatch, capsys):
        import agent_evaluator.cli.claude as cl

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude" / ".agent-evaluator").mkdir(parents=True)
        (tmp_path / ".claude" / ".agent-evaluator" / "guardrail_config.json").write_text(
            json.dumps({"scope": {"forbidden_tools": ["WebFetch"], "fail_on_violation": True}})
        )
        cases = tmp_path / "cases.json"
        cases.write_text(json.dumps({"cases": [
            {"tool": "WebFetch", "args": {"url": "x"}, "expect": "deny"},
        ]}))
        import argparse

        rc = cl.cmd_claude(argparse.Namespace(
            claude_command="test-config", cases=str(cases),
            global_install=False, json=False,
        ))
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_opencode_test_config_dispatches(self, tmp_path, monkeypatch, capsys):
        import argparse

        import agent_evaluator.cli.opencode as oc

        monkeypatch.chdir(tmp_path)
        sib = tmp_path / ".opencode" / "plugin"
        sib.mkdir(parents=True)
        (sib / "agent-evaluator.ts").write_text("// plugin")
        (sib / "agent-evaluator.config.json").write_text(
            json.dumps({"scope": {"forbidden_tools": ["WebFetch"], "fail_on_violation": True}})
        )
        cases = tmp_path / "cases.json"
        cases.write_text(json.dumps({"cases": [
            {"tool": "WebFetch", "args": {"url": "x"}, "expect": "deny"},
        ]}))
        rc = oc.cmd_opencode(argparse.Namespace(
            opencode_command="test-config", cases=str(cases),
            global_install=False, json=False,
        ))
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_opencode_test_config_no_sibling_uses_defaults(self, tmp_path, monkeypatch):
        import argparse

        import agent_evaluator.cli.opencode as oc

        monkeypatch.chdir(tmp_path)
        sib = tmp_path / ".opencode" / "plugin"
        sib.mkdir(parents=True)
        (sib / "agent-evaluator.ts").write_text("// plugin")
        cases = tmp_path / "cases.json"
        cases.write_text(json.dumps({"cases": [
            {"tool": "Read", "args": {"file_path": "/tmp/x"}, "expect": "allow"},
        ]}))
        rc = oc.cmd_opencode(argparse.Namespace(
            opencode_command="test-config", cases=str(cases),
            global_install=False, json=False,
        ))
        assert rc == 0
