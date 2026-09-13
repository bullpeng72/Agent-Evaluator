"""
SPEC-041: blocked-attempt detail — arg_excerpt capture + search_violations→show_violation
chaining + `agent-eval {claude,opencode} violations|blocked-detail`, tested across both hosts.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3

import pytest

from agent_evaluator import create_taskresult
from agent_evaluator.gates.live_guardrail import LiveGuardrail, LiveVerdict
from agent_evaluator.storage import sqlite_backend as sb

_RF = "rm " + "-rf "  # keep the literal out of this file's own source for the hook


def _v(gate="B", reason="dangerous tool parameters: ['Bash']"):
    return LiveVerdict(block=True, gate=gate, reason=reason)


# --------------------------------------------------------------------------- LiveGuardrail


class TestCaptureInLiveGuardrail:
    def test_default_enabled_redacts_and_hashes(self):
        g = LiveGuardrail()
        e = g.record_blocked_attempt(
            "t", "Bash", _v(), tool_input={"command": _RF + "/x  # mail me@example.com"}
        )
        assert e["arg_excerpt"] and e["arg_sha256"]
        assert "me@example.com" not in e["arg_excerpt"]
        assert "[REDACTED:email]" in e["arg_excerpt"]

    def test_disabled_keeps_pre_spec041_shape(self):
        g = LiveGuardrail(blocked_attempt_capture={"enabled": False})
        e = g.record_blocked_attempt("t", "Bash", _v(), tool_input={"command": _RF + "/"})
        assert set(e) == {"tool_name", "gate", "reason"}

    def test_truncation_and_no_redact(self):
        g = LiveGuardrail(blocked_attempt_capture={"max_chars": 15, "redact_pii": False})
        e = g.record_blocked_attempt(
            "t", "Bash", _v(), tool_input={"command": _RF + "/a/very/long/path/x"}
        )
        assert e["arg_excerpt"].endswith("…") and len(e["arg_excerpt"]) <= 16

    def test_report_max_chars_overrides_capture_ceiling(self):
        """SPEC-045 REQ-7: report_max_chars(옵트인)가 max_chars보다 크면 캡처는 그
        큰 쪽까지 저장한다 — CLI 목록/검색은 그 저장값을 display 시점에 더 잘라 쓰고
        (truncate_excerpt), 리포트/blocked-detail은 저장된 만큼 그대로 보여준다."""
        long_path = "x" * 300
        g = LiveGuardrail(
            blocked_attempt_capture={"max_chars": 20, "report_max_chars": 250, "redact_pii": False}
        )
        e = g.record_blocked_attempt(
            "t", "Bash", _v(), tool_input={"command": _RF + long_path}
        )
        # 저장은 report_max_chars(250)까지 — max_chars(20)로 잘리지 않는다.
        assert len(e["arg_excerpt"]) > 20
        assert len(e["arg_excerpt"]) <= 251  # +1 for the trailing "…"

    def test_report_max_chars_omitted_falls_back_to_max_chars(self):
        """report_max_chars를 안 주면 명시적으로 좁힌 max_chars 의도를 그대로 존중한다
        (자동으로 더 크게 캡처하지 않음 — 놀람 방지)."""
        g = LiveGuardrail(blocked_attempt_capture={"max_chars": 15, "redact_pii": False})
        e = g.record_blocked_attempt(
            "t", "Bash", _v(), tool_input={"command": _RF + "/a/very/long/path/x"}
        )
        assert e["arg_excerpt"].endswith("…") and len(e["arg_excerpt"]) <= 16

    def test_precomputed_excerpt_used_verbatim(self):
        g = LiveGuardrail()
        e = g.record_blocked_attempt(
            "t", "Bash", _v(), arg_excerpt="PRE", arg_sha256="deadbeef"
        )
        assert e["arg_excerpt"] == "PRE" and e["arg_sha256"] == "deadbeef"

    def test_string_input_and_no_input(self):
        g = LiveGuardrail()
        e = g.record_blocked_attempt("t", "Bash", _v(), tool_input=_RF + "/e")
        assert e["arg_excerpt"] == _RF + "/e"
        assert "arg_excerpt" not in g.record_blocked_attempt("t", "Bash", _v())

    def test_snapshot_carries_excerpt(self):
        g = LiveGuardrail()
        g.record_blocked_attempt("t", "Bash", _v(), tool_input={"command": _RF + "/x"})
        assert g.snapshot()["blocked_attempts"][0]["arg_excerpt"]

    def test_block_false_still_raises(self):
        with pytest.raises(ValueError):
            LiveGuardrail().record_blocked_attempt("t", "Bash", LiveVerdict(block=False))


# --------------------------------------------------------------------------- sqlite_backend


class TestSqliteBackend:
    def test_fresh_schema_has_arg_excerpt(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "s.db"))
        sb._ensure_schema(conn)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(blocked_violations)")]
        assert "arg_excerpt" in cols
        conn.close()

    def test_migration_preserves_old_rows(self, tmp_path):
        db = str(tmp_path / "old.db")
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        c.execute("INSERT INTO schema_version VALUES (1)")
        c.execute(
            "CREATE TABLE tasks (task_id TEXT PRIMARY KEY, task_type TEXT NOT NULL, "
            "success INTEGER NOT NULL, timestamp TEXT NOT NULL, data_json TEXT NOT NULL)"
        )
        c.execute("CREATE VIRTUAL TABLE violation_search USING fts5(task_id UNINDEXED, summary)")
        c.execute(
            "CREATE VIRTUAL TABLE blocked_violations USING fts5("
            "task_id UNINDEXED, tool_name UNINDEXED, gate UNINDEXED, reason)"
        )
        c.execute(
            "INSERT INTO blocked_violations (task_id, tool_name, gate, reason) "
            "VALUES ('old', 'Bash', 'B', 'dangerous tool parameters')"
        )
        c.commit()
        c.close()

        c2 = sqlite3.connect(db)
        sb._ensure_schema(c2)
        cols = [r[1] for r in c2.execute("PRAGMA table_info(blocked_violations)")]
        assert "arg_excerpt" in cols
        rows = c2.execute(
            "SELECT task_id, tool_name, gate, reason, arg_excerpt FROM blocked_violations"
        ).fetchall()
        assert rows == [("old", "Bash", "B", "dangerous tool parameters", "")]
        c2.close()

    def _save(self, db, task_id, attempts):
        t = create_taskresult(
            task_id=task_id, task_type="qa", question="q", response="r",
            extra={"blocked_attempts": attempts},
        )
        sb.save_tasks_to_db(db, [t])

    def test_search_matches_command_text_with_detail(self, tmp_path):
        db = str(tmp_path / "s.db")
        self._save(db, "A", [
            {"tool_name": "Bash", "gate": "B", "reason": "dangerous tool parameters: ['Bash']",
             "arg_excerpt": '{"command": "' + _RF + '/tmp/x"}'},
        ])
        r = sb.search_violations(db, _RF.strip(), include_blocked=True, detail=True)
        assert any(x["task_id"] == "A" and x.get("blocked") for x in r)
        assert any("arg_excerpt" in x for x in r if x.get("blocked"))

    def test_search_without_detail_is_backcompat(self, tmp_path):
        db = str(tmp_path / "s.db")
        self._save(db, "A", [
            {"tool_name": "Bash", "gate": "B", "reason": "dangerous tool parameters",
             "arg_excerpt": _RF + "/tmp"},
        ])
        r = sb.search_violations(db, "dangerous", include_blocked=True)
        assert r and all("arg_excerpt" not in x for x in r)

    def test_show_violation_found_and_missing(self, tmp_path):
        db = str(tmp_path / "s.db")
        self._save(db, "A", [
            {"tool_name": "Bash", "gate": "B", "reason": "r1", "arg_excerpt": "cmd1"},
            {"tool_name": "Bash", "gate": "E", "reason": "r2", "arg_excerpt": ""},
        ])
        sv = sb.show_violation(db, "A")
        assert sv["found"] and len(sv["blocked"]) == 2
        assert sv["blocked"][0]["arg_excerpt"] == "cmd1"
        miss = sb.show_violation(db, "zzz")
        assert miss["found"] is False and miss["blocked"] == []


# --------------------------------------------------------------------------- stdio bridge


class TestStdioBridge:
    def _run(self, reqs):
        import io

        from agent_evaluator.integrations import live_guardrail_stdio as brg

        out = io.StringIO()
        brg.run(io.StringIO("\n".join(json.dumps(r) for r in reqs) + "\n"), out)
        return [json.loads(x) for x in out.getvalue().splitlines()]

    def test_record_blocked_with_parameters_returns_excerpt(self):
        resp = self._run([
            {"op": "init", "scope": {"forbidden_tools": ["rm"], "fail_on_violation": True}},
            {"op": "record_blocked", "task_id": "t", "tool_name": "rm", "gate": "B",
             "reason": "scope violation", "parameters": {"command": _RF + "/x # a@b.com"}},
            {"op": "snapshot"},
        ])
        assert resp[1]["ok"] and "[REDACTED:email]" in resp[1]["arg_excerpt"]
        assert resp[2]["extra"]["blocked_attempts"][0]["arg_excerpt"]

    def test_record_blocked_without_parameters_is_backcompat(self):
        resp = self._run([
            {"op": "init", "scope": {"forbidden_tools": ["rm"], "fail_on_violation": True}},
            {"op": "record_blocked", "task_id": "t", "tool_name": "rm", "gate": "B",
             "reason": "scope violation"},
        ])
        assert resp[1] == {"ok": True}

    def test_capture_disabled_via_init(self):
        resp = self._run([
            {"op": "init", "scope": {"forbidden_tools": ["rm"], "fail_on_violation": True},
             "blocked_attempt_capture": {"enabled": False}},
            {"op": "record_blocked", "task_id": "t", "tool_name": "rm", "gate": "B",
             "reason": "scope violation", "parameters": {"command": _RF + "/x"}},
        ])
        assert resp[1] == {"ok": True}


# --------------------------------------------------------------------------- claude hook


class TestClaudeHook:
    def _setup(self, tmp_path, capture=True):
        from agent_evaluator.integrations import claude_code_hook as hook

        state_dir = tmp_path / ".claude" / ".agent-evaluator"
        state_dir.mkdir(parents=True)
        cfg = {
            "tool_parameter_safety": {
                "dangerous_patterns": [r"\brm\s+-[a-z]*r[a-z]*f"],
                "scope_tool_names": ["Bash"], "fail_on_dangerous": True,
            },
            "circuit_breaker_after": 5,
            "output_dir": str(tmp_path / "results" / "claude_code_live_guardrail"),
        }
        if not capture:
            cfg["blocked_attempt_capture"] = {"enabled": False}
        (state_dir / "guardrail_config.json").write_text(json.dumps(cfg))
        return hook, state_dir

    def test_block_writes_excerpt_and_sessionend_folds_it(self, tmp_path):
        hook, state_dir = self._setup(tmp_path)
        pre = hook.handle_pre_tool_use(
            {"session_id": "CC", "tool_name": "Bash",
             "tool_input": {"command": _RF + "/tmp/victim  # ssn 123-45-6789"}},
            state_dir,
        )
        assert pre["hookSpecificOutput"]["permissionDecision"] == "deny"
        bf = state_dir / "sessions" / "CC.blocked.json"
        rec = json.loads(bf.read_text().splitlines()[0])
        assert rec["arg_excerpt"] and "123-45-6789" not in rec["arg_excerpt"]

        end = hook.handle_session_end({"session_id": "CC", "reason": "clear"}, state_dir)
        assert end.get("ok")
        assert not bf.exists()
        dbp = tmp_path / "results" / "claude_code_live_guardrail" / "claude_code_sessions.db"
        sv = sb.show_violation(str(dbp), "CC")
        assert sv["found"] and sv["blocked"][0]["arg_excerpt"]

    def test_capture_disabled(self, tmp_path):
        hook, state_dir = self._setup(tmp_path, capture=False)
        hook.handle_pre_tool_use(
            {"session_id": "CC2", "tool_name": "Bash", "tool_input": {"command": _RF + "/x"}},
            state_dir,
        )
        rec = json.loads(
            (state_dir / "sessions" / "CC2.blocked.json").read_text().splitlines()[0]
        )
        assert "arg_excerpt" not in rec


# --------------------------------------------------------------------------- _blocked_detail


class TestBlockedDetailRecovery:
    def test_looks_like_block_is_strict(self):
        from agent_evaluator.integrations._blocked_detail import _looks_like_block

        assert _looks_like_block("dangerous tool parameters: ['Bash'] (task_id=x)")
        assert _looks_like_block("→ tool_authorization: dangerous_params")
        # a codebase grep whose OUTPUT quotes the phrase must NOT count
        assert not _looks_like_block("62:## dangerous tool parameters appears in docs here")

    def test_claude_transcript_recovery(self, tmp_path, monkeypatch):
        from agent_evaluator.integrations import _blocked_detail as bd

        proj = tmp_path / "projects" / "-Users-x-proj"
        proj.mkdir(parents=True)
        tid = "sess-xyz"
        lines = [
            {"message": {"content": [
                {"type": "tool_use", "id": "tu1", "name": "Bash",
                 "input": {"command": _RF + "/tmp/a", "description": "clean"}},
            ]}},
            {"message": {"content": [
                {"type": "tool_result", "tool_use_id": "tu1", "is_error": True,
                 "content": "dangerous tool parameters: ['Bash'] (task_id=sess-xyz)"},
            ]}},
            # a benign grep whose output mentions the phrase — must be ignored
            {"message": {"content": [
                {"type": "tool_use", "id": "tu2", "name": "Bash",
                 "input": {"command": "grep -n dangerous ."}},
            ]}},
            {"message": {"content": [
                {"type": "tool_result", "tool_use_id": "tu2", "is_error": False,
                 "content": "12: dangerous tool parameters mentioned"},
            ]}},
        ]
        (proj / f"{tid}.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
        monkeypatch.setattr(bd, "_claude_projects_root", lambda: tmp_path / "projects")

        rec = bd.recover_blocked_commands(tid, host="claude")
        assert rec["source"] == "claude-transcript"
        assert len(rec["items"]) == 1
        assert _RF.strip() in rec["items"][0]["command"]

    def test_opencode_db_recovery(self, tmp_path, monkeypatch):
        from agent_evaluator.integrations import _blocked_detail as bd

        db = tmp_path / "opencode.db"
        c = sqlite3.connect(str(db))
        c.execute(
            "CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT, "
            "time_created INTEGER, time_updated INTEGER, data TEXT)"
        )
        c.execute(
            "INSERT INTO part (id, session_id, time_created, data) VALUES (?,?,?,?)",
            ("p1", "oc-1", 1, json.dumps({
                "type": "tool", "tool": "bash", "callID": "c1",
                "state": {
                    "status": "error", "input": {"command": _RF + "/srv"},
                    "error": "[agent-evaluator] blocked by Gate B: dangerous tool parameters",
                },
            })),
        )
        c.execute(
            "INSERT INTO part (id, session_id, time_created, data) VALUES (?,?,?,?)",
            ("p2", "oc-1", 2, json.dumps({
                "type": "tool", "tool": "bash", "callID": "c2",
                "state": {"status": "completed", "input": {"command": "ls"}},
            })),
        )
        c.commit()
        c.close()
        monkeypatch.setattr(bd, "_opencode_db_path", lambda: db)

        rec = bd.recover_blocked_commands("oc-1", host="opencode")
        assert rec["source"] == "opencode-db"
        assert len(rec["items"]) == 1
        assert _RF.strip() in rec["items"][0]["command"]

    def test_format_blocked_detail_variants(self, tmp_path):
        from agent_evaluator.integrations._blocked_detail import format_blocked_detail

        # has excerpt
        sv = {"task_id": "A", "found": True, "task_type": "qa", "timestamp": "t",
              "observed_summary": None,
              "blocked": [{"tool_name": "Bash", "gate": "B", "reason": "r",
                           "arg_excerpt": _RF + "/x"}]}
        txt = format_blocked_detail(sv)
        assert "command: " + _RF + "/x" in txt
        # not found
        assert "No blocked-attempt history" in format_blocked_detail(
            {"task_id": "Z", "found": False, "blocked": []}
        )


# --------------------------------------------------------------------------- MCP server


class TestMcpServer:
    # the stdio MCP server needs the optional [mcp] extra (not in CI's [dev,serve] install)
    pytestmark = pytest.mark.skipif(
        importlib.util.find_spec("mcp") is None, reason="requires the [mcp] extra"
    )

    @pytest.mark.asyncio
    async def test_both_tools_registered(self, tmp_path):
        from agent_evaluator.integrations.violation_search_mcp import build_server

        srv = build_server(str(tmp_path / "s.db"))
        names = sorted(t.name for t in await srv.list_tools())
        # SPEC-045 REQ-5: list_violations added as the keyword-free entry point.
        assert names == ["list_violations", "search_violations", "show_violation"]

    @pytest.mark.asyncio
    async def test_search_hint_and_show_violation(self, tmp_path):
        from agent_evaluator.integrations.violation_search_mcp import build_server

        db = str(tmp_path / "s.db")
        t = create_taskresult(
            task_id="A", task_type="qa", question="q", response="r",
            extra={"blocked_attempts": [
                {"tool_name": "Bash", "gate": "B", "reason": "dangerous tool parameters: ['Bash']",
                 "arg_excerpt": '{"command": "' + _RF + '/x"}'},
            ]},
        )
        sb.save_tasks_to_db(db, [t])
        srv = build_server(db)

        s = await srv.call_tool("search_violations", {"query": _RF.strip()})
        text = s[0][0].text if isinstance(s, tuple) else str(s)
        assert "command:" in text and 'show_violation (task_id="A")' in text

        d = await srv.call_tool("show_violation", {"task_id": "A"})
        dtext = d[0][0].text if isinstance(d, tuple) else str(d)
        assert "Blocked-attempt detail" in dtext and _RF.strip() in dtext


# --------------------------------------------------------------------------- CLI (both hosts)


class TestCliParity:
    @pytest.mark.parametrize(
        "host,expected_dir,expected_file",
        [
            ("claude", "results/claude_code_live_guardrail", "claude_code_sessions.db"),
            ("opencode", "results/opencode_live_guardrail", "opencode_sessions.db"),
        ],
    )
    def test_resolve_db_path_per_host(
        self, host, expected_dir, expected_file, monkeypatch, tmp_path
    ):
        from agent_evaluator.cli import _violations_detail as vd

        monkeypatch.delenv("AGENT_EVALUATOR_OUTPUT_DIR", raising=False)
        monkeypatch.setattr(vd, "_project_root", lambda *a, **k: tmp_path)
        p = vd.resolve_db_path(host)
        assert p == str(tmp_path / expected_dir / expected_file)
        assert vd.resolve_db_path(host, "/x/y.db") == "/x/y.db"
        monkeypatch.setenv("AGENT_EVALUATOR_OUTPUT_DIR", "/custom/out")
        assert vd.resolve_db_path(host) == f"/custom/out/{expected_file}"

    @pytest.mark.parametrize("host", ["claude", "opencode"])
    def test_subcommands_registered(self, host):
        import argparse

        from agent_evaluator.cli.claude import build_claude_subparser
        from agent_evaluator.cli.opencode import build_opencode_subparser

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        (build_claude_subparser if host == "claude" else build_opencode_subparser)(sub)
        ns = parser.parse_args([host, "blocked-detail", "abc"])
        assert ns.task_id == "abc"
        ns2 = parser.parse_args([host, "violations", "rm -rf", "--detail"])
        assert ns2.query == "rm -rf" and ns2.detail is True
        # SPEC-045 REQ-6: query is now optional — omitting it selects browse mode.
        ns3 = parser.parse_args([host, "violations"])
        assert ns3.query is None
        ns4 = parser.parse_args([host, "violations", "--since", "2026-09-08", "--gate", "B"])
        assert ns4.query is None and ns4.since == "2026-09-08" and ns4.gate == "B"

    @pytest.mark.parametrize("host", ["claude", "opencode"])
    def test_run_blocked_detail_exit_codes(self, host, tmp_path, capsys):
        from agent_evaluator.cli._violations_detail import run_blocked_detail

        db = str(tmp_path / f"{host}.db")
        t = create_taskresult(
            task_id="S", task_type="qa", question="q", response="r",
            extra={"blocked_attempts": [
                {"tool_name": "Bash", "gate": "B", "reason": "r", "arg_excerpt": "cmd"},
            ]},
        )
        sb.save_tasks_to_db(db, [t])
        assert run_blocked_detail(host, "S", db=db) == 0
        assert run_blocked_detail(host, "nope", db=db) == 1
        out = capsys.readouterr().out
        assert "cmd" in out

    @pytest.mark.parametrize("host", ["claude", "opencode"])
    def test_run_violations_no_db(self, host, tmp_path, capsys):
        from agent_evaluator.cli._violations_detail import run_violations

        rc = run_violations(host, "x", db=str(tmp_path / "absent.db"))
        assert rc == 1
        assert "No batch-report database" in capsys.readouterr().out

    @pytest.mark.parametrize("host", ["claude", "opencode"])
    def test_run_violations_browse_mode_no_query(self, host, tmp_path, capsys):
        """SPEC-045 REQ-6: query 생략 시 키워드 없이 최근 이력을 나열한다."""
        from agent_evaluator.cli._violations_detail import run_violations

        db = str(tmp_path / f"{host}.db")
        t = create_taskresult(
            task_id="S", task_type="qa", question="q", response="r",
            extra={"blocked_attempts": [
                {"tool_name": "Bash", "gate": "B", "reason": "dangerous tool parameters"},
            ]},
        )
        sb.save_tasks_to_db(db, [t])

        rc = run_violations(host, None, db=db)
        assert rc == 0
        out = capsys.readouterr().out
        assert "S" in out and "no keyword filter" in out

    @pytest.mark.parametrize("host", ["claude", "opencode"])
    def test_run_violations_browse_mode_empty_db_message(self, host, tmp_path, capsys):
        from agent_evaluator.cli._violations_detail import run_violations

        db = str(tmp_path / f"{host}.db")
        sb.save_tasks_to_db(db, [])  # schema only

        rc = run_violations(host, None, db=db)
        assert rc == 0
        assert "nothing to list" in capsys.readouterr().out


# --------------------------------------------------------------------------- doctor


class TestDoctorProbe:
    def test_probe_ok(self):
        from agent_evaluator.cli._integration_health import probe_blocked_capture

        st, detail = probe_blocked_capture({})
        assert st == "ok" and "redacted" in detail

    def test_probe_info_when_disabled(self):
        from agent_evaluator.cli._integration_health import probe_blocked_capture

        st, _ = probe_blocked_capture({"blocked_attempt_capture": {"enabled": False}})
        assert st == "info"

    @pytest.mark.parametrize("host", ["claude", "opencode"])
    def test_doctor_reports_capture_check(self, host):
        import subprocess
        import sys

        out = subprocess.run(
            [sys.executable, "-m", "agent_evaluator.cli.main", host, "doctor", "--json"],
            capture_output=True, text=True, timeout=90,
        ).stdout
        data = json.loads(out)
        assert any(c["label"] == "blocked-attempt capture" for c in data["checks"])

    @pytest.mark.parametrize("host", ["claude", "opencode"])
    def test_doctor_reports_violation_audit_db_check(self, host):
        """SPEC-045 REQ-9: doctor는 감사 DB의 존재/건수를 능동적으로 알려준다."""
        import subprocess
        import sys

        out = subprocess.run(
            [sys.executable, "-m", "agent_evaluator.cli.main", host, "doctor", "--json"],
            capture_output=True, text=True, timeout=90,
        ).stdout
        data = json.loads(out)
        assert any(c["label"] == "violation/blocked-attempt audit" for c in data["checks"])


class TestProbeViolationAuditDb:
    """SPEC-045 REQ-9: probe_violation_audit_db() — doctor의 존재 신호 헬퍼."""

    def test_no_db_yet_is_info_not_a_problem(self, tmp_path, monkeypatch):
        from agent_evaluator.cli._integration_health import probe_violation_audit_db

        monkeypatch.delenv("AGENT_EVALUATOR_OUTPUT_DIR", raising=False)
        monkeypatch.setenv("AGENT_EVALUATOR_OUTPUT_DIR", str(tmp_path / "nope"))
        st, detail = probe_violation_audit_db("claude")
        assert st == "info"
        assert "no audit DB yet" in detail

    def test_db_with_rows_reports_counts_and_points_at_violations_command(
        self, tmp_path, monkeypatch
    ):
        from agent_evaluator.cli._integration_health import probe_violation_audit_db

        monkeypatch.setenv("AGENT_EVALUATOR_OUTPUT_DIR", str(tmp_path))
        t = create_taskresult(
            task_id="S", task_type="qa", question="q", response="r",
            extra={"blocked_attempts": [
                {"tool_name": "Bash", "gate": "B", "reason": "dangerous tool parameters"},
            ]},
        )
        sb.save_tasks_to_db(str(tmp_path / "claude_code_sessions.db"), [t])

        st, detail = probe_violation_audit_db("claude")
        assert st == "info"
        assert "1 blocked" in detail
        assert "agent-eval claude violations" in detail

    def test_empty_db_no_rows_is_info(self, tmp_path, monkeypatch):
        from agent_evaluator.cli._integration_health import probe_violation_audit_db

        monkeypatch.setenv("AGENT_EVALUATOR_OUTPUT_DIR", str(tmp_path))
        sb.save_tasks_to_db(str(tmp_path / "claude_code_sessions.db"), [])  # schema only

        st, detail = probe_violation_audit_db("claude")
        assert st == "info"
        assert "no violation/blocked rows yet" in detail
