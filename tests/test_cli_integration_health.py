"""
tests/test_cli_integration_health.py
====================================
``agent_evaluator.cli._integration_health`` — ``agent-eval {claude,opencode}
doctor/upgrade/uninstall``이 공유하는 헬퍼의 단위 테스트.

커버:
  - deep_merge_defaults: 없는 키만 채우고 사용자 값은 안 건드림, 중첩 dict 재귀, 리스트는 leaf
  - interpreter_from_command: 접두 래핑(nice/env VAR=v) 건너뛰고 첫 실행 토큰 추출
  - probe_import: 되는 모듈 True / 없는 모듈 False + 마지막 에러 줄
  - DoctorReport: 상태 집계, exit_code(strict), JSON/텍스트 렌더
  - validate_guardrail_config: 정상 설정 통과, 오타 키 SKIPPED 경고 수집
  - mcp_initialize_probe: 실제 번들 MCP 서버와 핸드셰이크(‘mcp’ extra 있을 때만)
"""
from __future__ import annotations

import json
import sys

import pytest

from agent_evaluator.cli._integration_health import (
    DoctorReport,
    deep_merge_defaults,
    interpreter_from_command,
    probe_import,
    validate_guardrail_config,
)


class TestDeepMergeDefaults:
    def test_adds_missing_top_level_key(self):
        merged, added = deep_merge_defaults({"a": 1}, {"a": 9, "b": 2})
        assert merged == {"a": 1, "b": 2}
        assert added == ["b"]

    def test_never_overwrites_existing_user_value(self):
        merged, added = deep_merge_defaults({"a": {"x": 99}}, {"a": {"x": 1, "y": 2}})
        assert merged == {"a": {"x": 99, "y": 2}}
        assert added == ["a.y"]

    def test_list_is_leaf_not_merged(self):
        merged, added = deep_merge_defaults({"p": [1]}, {"p": [1, 2, 3]})
        assert merged == {"p": [1]}
        assert added == []

    def test_does_not_mutate_input(self):
        user = {"a": 1}
        deep_merge_defaults(user, {"a": 1, "b": 2})
        assert user == {"a": 1}

    def test_nested_missing_block_added_whole(self):
        merged, added = deep_merge_defaults({}, {"scope": {"forbidden_tools": ["x"]}})
        assert merged == {"scope": {"forbidden_tools": ["x"]}}
        assert added == ["scope"]
        merged["scope"]["forbidden_tools"].append("y")  # deep-copied, not shared


class TestInterpreterFromCommand:
    def test_plain(self):
        assert interpreter_from_command("/x/py -m mod") == "/x/py"

    def test_skips_nice_and_env_prefix(self):
        assert interpreter_from_command("nice env FOO=bar /x/py -m mod") == "/x/py"

    def test_unparseable_returns_none(self):
        assert interpreter_from_command('py -m "mod') is None


class TestProbeImport:
    def test_importable_module(self):
        ok, err = probe_import(sys.executable, "json")
        assert ok is True
        assert err == ""

    def test_missing_module(self):
        ok, err = probe_import(sys.executable, "totally_not_a_real_module_xyz")
        assert ok is False
        assert "totally_not_a_real_module_xyz" in err

    def test_missing_interpreter(self):
        ok, err = probe_import("/no/such/python", "json")
        assert ok is False
        assert "not found" in err or "No such file" in err


class TestDoctorReport:
    def test_exit_code_ok_when_all_pass(self):
        r = DoctorReport(title="t")
        r.ok("static", "x")
        r.info("live", "skipped")
        assert r.exit_code() == 0

    def test_exit_code_1_on_error(self):
        r = DoctorReport(title="t")
        r.ok("static", "x")
        r.error("static", "y", "boom")
        assert r.exit_code() == 1
        assert r.n_errors == 1

    def test_strict_fails_on_warning(self):
        r = DoctorReport(title="t")
        r.warn("static", "y")
        assert r.exit_code() == 0
        assert r.exit_code(strict=True) == 1

    def test_render_json_shape(self):
        r = DoctorReport(title="t")
        r.ok("static", "a", "d")
        r.warn("live", "b")
        data = json.loads(r.render_json())
        assert data["title"] == "t"
        assert data["summary"] == {"errors": 0, "warnings": 1, "passed": 1}
        assert data["checks"][0] == {"tier": "static", "status": "ok", "label": "a", "detail": "d"}

    def test_render_text_groups_by_tier_and_has_summary(self):
        r = DoctorReport(title="My Title")
        r.ok("static", "a")
        r.error("live", "b", "why")
        txt = r.render_text(color=False)
        assert "My Title" in txt
        assert "Static" in txt and "Live" in txt
        assert "1 error(s)" in txt


class TestValidateGuardrailConfig:
    def test_valid_config_builds_clean(self):
        ok, warns = validate_guardrail_config(
            {"scope": {"forbidden_tools": ["WebFetch"], "fail_on_violation": True}}
        )
        assert ok is True
        assert warns == []

    def test_typo_key_is_reported_as_skipped_warning(self):
        ok, warns = validate_guardrail_config(
            {"loop_detection": {"consecutive_repeat_treshold": 3}}  # typo
        )
        assert ok is True  # build_guardrail skips the bad block, stays alive
        assert any("loop_detection" in w for w in warns)

    def test_bridge_only_keys_are_ignored(self):
        ok, warns = validate_guardrail_config(
            {"output_dir": "x", "circuit_breaker_after": 5, "scope": {"forbidden_tools": []}}
        )
        assert ok is True
        assert warns == []


class TestMcpInitializeProbe:
    def test_handshake_against_bundled_server(self):
        pytest.importorskip("mcp")
        from agent_evaluator.cli._integration_health import mcp_initialize_probe

        status, detail = mcp_initialize_probe(
            sys.executable,
            "agent_evaluator.integrations.violation_search_mcp",
            "search_violations",
        )
        assert status == "ok", detail
        assert "search_violations" in detail

    def test_missing_mcp_extra_is_a_warning_not_error(self):
        from agent_evaluator.cli._integration_health import mcp_initialize_probe

        # 존재하지 않는 모듈 → 서버가 못 뜸 → warn (never "ok")
        status, _ = mcp_initialize_probe(sys.executable, "no_such_mcp_module_xyz", "tool")
        assert status == "warn"
