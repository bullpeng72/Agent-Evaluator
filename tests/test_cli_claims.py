"""
tests/test_cli_claims.py
============================
SPEC-038: `agent-eval claims` CLI (add/list/release/audit).

이 서브커맨드는 append_claim()/load_active_claims()/audit_claims()
(SPEC-032/034/036/037)를 감싸는 얇은 레이어다 — 새 판정 로직은 없으므로
여기서는 ① argparse.Namespace → 함수 호출 배선이 올바른지, ② CLI 특유의
편의 동작(claim_id 자동 생성, developer="auto" 해석, 종료 코드)이 맞는지만
확인한다.
"""
from __future__ import annotations

import argparse
import json
from unittest.mock import patch

from agent_evaluator.cli.claims import (
    _cmd_claims_add,
    _cmd_claims_audit,
    _cmd_claims_enable_live_check,
    _cmd_claims_list,
    _cmd_claims_release,
    cmd_claims,
)
from agent_evaluator.gates.team_concurrency import append_claim, load_active_claims


class _FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def _ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


class TestClaimsAdd:
    def test_add_with_explicit_developer(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        code = _cmd_claims_add(_ns(
            scope=["configs.py"], developer="수아",
            claims_path=str(claims_path), claim_id=None,
        ))
        assert code == 0
        active = load_active_claims(claims_path)
        assert len(active) == 1
        assert active[0]["developer"] == "수아"
        assert active[0]["scope"] == ["configs.py"]

    def test_add_with_explicit_claim_id(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        _cmd_claims_add(_ns(
            scope=["x.py"], developer="수아",
            claims_path=str(claims_path), claim_id="c-fixed-01",
        ))
        active = load_active_claims(claims_path)
        assert active[0]["claim_id"] == "c-fixed-01"

    def test_add_auto_generates_claim_id_when_omitted(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        _cmd_claims_add(_ns(
            scope=["x.py"], developer="수아",
            claims_path=str(claims_path), claim_id=None,
        ))
        active = load_active_claims(claims_path)
        assert active[0]["claim_id"].startswith("c-")
        assert len(active[0]["claim_id"]) == len("c-") + 8

    def test_add_developer_auto_literal_resolves_via_git(self, tmp_path):
        """--developer auto (명시적 리터럴)도 --developer 생략과 동일하게
        git config user.name으로 해석돼야 한다 — `or` 단락평가로 "auto"
        문자열 그대로 저장되는 회귀를 방지하는 테스트."""
        claims_path = tmp_path / "claims.jsonl"
        with patch(
            "subprocess.run",
            return_value=_FakeCompletedProcess("Sungwoo Kim\n", 0),
        ):
            code = _cmd_claims_add(_ns(
                scope=["x.py"], developer="auto",
                claims_path=str(claims_path), claim_id=None,
            ))
        assert code == 0
        active = load_active_claims(claims_path)
        assert active[0]["developer"] == "Sungwoo Kim"

    def test_add_developer_omitted_resolves_via_git(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        with patch(
            "subprocess.run",
            return_value=_FakeCompletedProcess("Sungwoo Kim\n", 0),
        ):
            code = _cmd_claims_add(_ns(
                scope=["x.py"], developer=None,
                claims_path=str(claims_path), claim_id=None,
            ))
        assert code == 0
        active = load_active_claims(claims_path)
        assert active[0]["developer"] == "Sungwoo Kim"

    def test_add_fails_when_developer_omitted_and_git_unavailable(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        with patch("subprocess.run", side_effect=FileNotFoundError("no git")):
            code = _cmd_claims_add(_ns(
                scope=["x.py"], developer=None,
                claims_path=str(claims_path), claim_id=None,
            ))
        assert code == 1
        assert load_active_claims(claims_path) == []

    def test_add_creates_parent_directory(self, tmp_path):
        claims_path = tmp_path / "nested" / "dir" / "claims.jsonl"
        code = _cmd_claims_add(_ns(
            scope=["x.py"], developer="수아",
            claims_path=str(claims_path), claim_id=None,
        ))
        assert code == 0
        assert claims_path.exists()

    def test_add_multiple_scope_paths(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        _cmd_claims_add(_ns(
            scope=["a.py", "b.py", "dir/"], developer="수아",
            claims_path=str(claims_path), claim_id=None,
        ))
        active = load_active_claims(claims_path)
        assert active[0]["scope"] == ["a.py", "b.py", "dir/"]

    def test_add_warns_but_does_not_block_on_overlap(self, tmp_path, capsys):
        """docs/AUTOPILOT_IMPROVEMENTS.md §5 — add()가 겹침을 add 시점에
        경고조차 안 하던 공백. 여전히 exit 0이어야 한다 — 차단은 audit의 몫."""
        claims_path = tmp_path / "claims.jsonl"
        _cmd_claims_add(_ns(
            scope=["src/ask/"], developer="ms",
            claims_path=str(claims_path), claim_id=None,
        ))
        capsys.readouterr()
        code = _cmd_claims_add(_ns(
            scope=["src/ask/generate.py"], developer="sj",
            claims_path=str(claims_path), claim_id=None,
        ))
        out = capsys.readouterr().out
        assert code == 0
        assert "overlaps an existing active claim" in out
        assert len(load_active_claims(claims_path)) == 2  # 둘 다 열림 — 안 막음

    def test_add_no_warning_when_no_overlap(self, tmp_path, capsys):
        claims_path = tmp_path / "claims.jsonl"
        _cmd_claims_add(_ns(
            scope=["src/ask/"], developer="ms",
            claims_path=str(claims_path), claim_id=None,
        ))
        capsys.readouterr()
        _cmd_claims_add(_ns(
            scope=["src/check/"], developer="sj",
            claims_path=str(claims_path), claim_id=None,
        ))
        out = capsys.readouterr().out
        assert "overlaps" not in out


class TestClaimsList:
    def test_list_empty_returns_0(self, tmp_path, capsys):
        claims_path = tmp_path / "claims.jsonl"
        code = _cmd_claims_list(_ns(claims_path=str(claims_path)))
        assert code == 0
        assert "No active claims" in capsys.readouterr().out

    def test_list_filters_by_developer(self, tmp_path, capsys):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="ms", scope=["a.py"],
            started_at="2026-07-08T00:00:00+00:00", status="active",
        )
        append_claim(
            claims_path, claim_id="c2", developer="sj", scope=["b.py"],
            started_at="2026-07-08T00:00:00+00:00", status="active",
        )
        code = _cmd_claims_list(_ns(claims_path=str(claims_path), developer="sj"))
        out = capsys.readouterr().out
        assert code == 0
        assert "c2" in out
        assert "c1" not in out

    def test_list_developer_filter_no_match(self, tmp_path, capsys):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="ms", scope=["a.py"],
            started_at="2026-07-08T00:00:00+00:00", status="active",
        )
        code = _cmd_claims_list(_ns(claims_path=str(claims_path), developer="ghost"))
        out = capsys.readouterr().out
        assert code == 0
        assert "No active claims" in out

    def test_list_shows_active_claims(self, tmp_path, capsys):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="수아", scope=["a.py"],
            started_at="2026-07-08T00:00:00+00:00", status="active",
        )
        code = _cmd_claims_list(_ns(claims_path=str(claims_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "c1" in out
        assert "수아" in out
        assert "a.py" in out

    def test_list_excludes_released_claims(self, tmp_path, capsys):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="수아", scope=["a.py"],
            started_at="2026-07-08T00:00:00+00:00", status="active",
        )
        append_claim(claims_path, claim_id="c1", status="released")
        _cmd_claims_list(_ns(claims_path=str(claims_path)))
        assert "No active claims" in capsys.readouterr().out

    def test_list_handles_unparseable_started_at(self, tmp_path, capsys):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="수아", scope=["a.py"],
            started_at="not-a-timestamp", status="active",
        )
        code = _cmd_claims_list(_ns(claims_path=str(claims_path)))
        assert code == 0  # 파싱 실패해도 크래시하지 않음


class TestClaimsRelease:
    def test_release_active_claim(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="수아", scope=["a.py"],
            started_at="2026-07-08T00:00:00+00:00", status="active",
        )
        code = _cmd_claims_release(_ns(
            claim_id="c1", claims_path=str(claims_path), force=False,
        ))
        assert code == 0
        assert load_active_claims(claims_path) == []

    def test_release_unknown_id_without_force_returns_1(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        code = _cmd_claims_release(_ns(
            claim_id="c-nope", claims_path=str(claims_path), force=False,
        ))
        assert code == 1
        # force 없이는 이벤트 자체를 기록하지 않는다
        assert claims_path.exists() is False or claims_path.read_text() == ""

    def test_release_unknown_id_with_force_records_event(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        code = _cmd_claims_release(_ns(
            claim_id="c-nope", claims_path=str(claims_path), force=True,
        ))
        assert code == 0
        lines = claims_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["claim_id"] == "c-nope"
        assert event["status"] == "released"


class TestClaimsAudit:
    def test_audit_clean_returns_0(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="수아", scope=["a.py"],
            started_at="2026-07-08T00:00:00+00:00", status="active",
        )
        code = _cmd_claims_audit(_ns(claims_path=str(claims_path), ttl_hours=8760.0))
        assert code == 0

    def test_audit_ttl_violation_returns_1(self, tmp_path, capsys):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="수아", scope=["a.py"],
            started_at="2020-01-01T00:00:00+00:00", status="active",
        )
        code = _cmd_claims_audit(_ns(claims_path=str(claims_path), ttl_hours=8.0))
        assert code == 1
        assert "TTL exceeded" in capsys.readouterr().out

    def test_audit_overlap_violation_returns_1(self, tmp_path, capsys):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="수아", scope=["shared/"],
            started_at="2026-07-08T00:00:00+00:00", status="active",
        )
        append_claim(
            claims_path, claim_id="c2", developer="태호", scope=["shared/"],
            started_at="2026-07-08T00:00:00+00:00", status="active",
        )
        code = _cmd_claims_audit(_ns(claims_path=str(claims_path), ttl_hours=8760.0))
        assert code == 1
        assert "Overlapping scope" in capsys.readouterr().out


class TestClaimsEnableLiveCheck:
    """docs/AUTOPILOT_IMPROVEMENTS.md §5 — TeamConcurrencyConfig를 켜는

    CLI/마법사가 없어 수동 JSON 편집만 가능했다."""

    def test_merges_team_concurrency_into_existing_config(self, tmp_path):
        cfg = tmp_path / "agent-evaluator.config.json"
        cfg.write_text(json.dumps({"loop_detection": {"consecutive_repeat_threshold": 3}}))

        code = _cmd_claims_enable_live_check(_ns(
            config=str(cfg), owner="auto", claims_path=".aoo/claims.jsonl",
        ))
        assert code == 0
        data = json.loads(cfg.read_text())
        assert data["team_concurrency"] == {"owner": "auto", "claims_path": ".aoo/claims.jsonl"}
        assert data["loop_detection"] == {"consecutive_repeat_threshold": 3}  # preserved

    def test_missing_config_file_fails(self, tmp_path):
        code = _cmd_claims_enable_live_check(_ns(
            config=str(tmp_path / "nope.json"), owner="auto",
            claims_path=".aoo/claims.jsonl",
        ))
        assert code == 1

    def test_invalid_json_fails(self, tmp_path):
        cfg = tmp_path / "bad.json"
        cfg.write_text("{not json")
        code = _cmd_claims_enable_live_check(_ns(
            config=str(cfg), owner="auto", claims_path=".aoo/claims.jsonl",
        ))
        assert code == 1

    def test_existing_owner_value_is_not_overwritten(self, tmp_path):
        """이미 있는 하위 키(owner)는 절대 덮어쓰지 않는다 — claims_path처럼

        없는 하위 키만 채운다(``deep_merge_defaults`` 그대로, 재귀 병합)."""
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"team_concurrency": {"owner": "sw"}}))

        code = _cmd_claims_enable_live_check(_ns(
            config=str(cfg), owner="auto", claims_path=".aoo/claims.jsonl",
        ))
        assert code == 0
        data = json.loads(cfg.read_text())
        assert data["team_concurrency"]["owner"] == "sw"  # untouched
        assert data["team_concurrency"]["claims_path"] == ".aoo/claims.jsonl"  # filled in

    def test_fully_configured_team_concurrency_reports_nothing_to_add(self, tmp_path, capsys):
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps(
            {"team_concurrency": {"owner": "sw", "claims_path": ".aoo/claims.jsonl"}}
        ))

        code = _cmd_claims_enable_live_check(_ns(
            config=str(cfg), owner="auto", claims_path=".aoo/claims.jsonl",
        ))
        assert code == 0
        assert "nothing to add" in capsys.readouterr().out

    def test_dispatch_via_cmd_claims(self, tmp_path):
        cfg = tmp_path / "cfg.json"
        cfg.write_text("{}")
        code = cmd_claims(_ns(
            claims_command="enable-live-check", config=str(cfg), owner="auto",
            claims_path=".aoo/claims.jsonl",
        ))
        assert code == 0


class TestClaimsDispatcher:
    def test_dispatcher_routes_to_add(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        code = cmd_claims(_ns(
            claims_command="add", scope=["a.py"], developer="수아",
            claims_path=str(claims_path), claim_id=None,
        ))
        assert code == 0

    def test_dispatcher_missing_subcommand_returns_1(self):
        code = cmd_claims(_ns(claims_command=None))
        assert code == 1

    def test_dispatcher_unknown_subcommand_returns_1(self):
        code = cmd_claims(_ns(claims_command="bogus"))
        assert code == 1
