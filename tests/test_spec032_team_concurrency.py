"""
tests/test_spec032_team_concurrency.py
==========================================
SPEC-032: TeamConcurrencyConfig — 축소 범위 다중 세션 스코프 충돌 감지.

REQ-1: 승격된 check_scope_claim()/append_claim()/load_active_claims()가 초기 AOO 로컬
개발 루프 데모 시나리오(클레임 없음 → 겹침 감지 → 통과)와 동일한 결과를 내는지.
REQ-2/3/4: TeamConcurrencyConfig + LiveGuardrail 통합(1회 로드, read/edit/write만
검사, 경로 후보 키, shared_files).
REQ-5: record_blocked_attempt()와의 통합(신규 코드 없음, 재사용 확인).
REQ-6: refresh_team_claims().
"""
from __future__ import annotations

from agent_evaluator.gates.live_guardrail import LiveGuardrail
from agent_evaluator.gates.team_concurrency import (
    TeamConcurrencyConfig,
    append_claim,
    check_scope_claim,
    extract_path_param,
    load_active_claims,
)


class TestCheckScopeClaimPromotion:
    """REQ-1: 초기 AOO 로컬 개발 루프 데모와 동일한 시나리오 재현."""

    def test_no_claims_file_returns_empty(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        assert check_scope_claim(["agent_evaluator/gates/gate_d_performance/"], claims_path) == []

    def test_developer_b_overlap_detected(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c-demo-01", developer="sungwoo",
            scope=["agent_evaluator/gates/gate_d_performance/"],
            branch="feat/gate-d-cache", started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        conflicts = check_scope_claim(["agent_evaluator/gates/gate_d_performance/"], claims_path)
        assert len(conflicts) == 1
        assert conflicts[0]["developer"] == "sungwoo"

    def test_developer_c_non_overlap_allowed(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c-demo-01", developer="sungwoo",
            scope=["agent_evaluator/gates/gate_d_performance/"], status="active",
        )
        conflicts = check_scope_claim(["agent_evaluator/gates/gate_e_security/"], claims_path)
        assert conflicts == []

    def test_release_then_recheck_clears_conflict(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c-demo-01", developer="sungwoo",
            scope=["agent_evaluator/gates/gate_d_performance/"], status="active",
        )
        append_claim(claims_path, claim_id="c-demo-01", status="released")
        conflicts = check_scope_claim(["agent_evaluator/gates/gate_d_performance/"], claims_path)
        assert conflicts == []

    def test_only_latest_status_per_claim_id_is_valid(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(claims_path, claim_id="c1", developer="a", scope=["x/"], status="active")
        append_claim(claims_path, claim_id="c1", developer="a", scope=["x/"], status="released")
        append_claim(claims_path, claim_id="c1", developer="a", scope=["x/"], status="active")
        claims = load_active_claims(claims_path)
        assert len(claims) == 1


class TestExtractPathParam:
    def test_finds_first_matching_candidate_key(self):
        assert extract_path_param({"file": "a.py"}, ("file", "filePath", "path")) == "a.py"

    def test_tries_candidates_in_order(self):
        assert extract_path_param({"filePath": "b.py", "path": "c.py"}, ("file", "filePath", "path")) == "b.py"

    def test_none_when_no_candidate_present(self):
        assert extract_path_param({"content": "x"}, ("file", "filePath", "path")) is None

    def test_none_when_parameters_none(self):
        assert extract_path_param(None, ("file",)) is None

    def test_ignores_non_string_values(self):
        assert extract_path_param({"file": 123}, ("file",)) is None


class TestLiveGuardrailTeamConcurrencyIntegration:
    """REQ-3/4: LiveGuardrail 생성자 1회 로드 + check_before_tool_call() 검사."""

    def _make_claims(self, tmp_path, **fields):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(claims_path, **fields)
        return claims_path

    def test_none_by_default_no_behavior_change(self):
        """team_concurrency 생략 시 회귀 없음."""
        guardrail = LiveGuardrail()
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "anything.py"})
        assert verdict.block is False

    def test_conflicting_edit_is_blocked(self, tmp_path):
        claims_path = self._make_claims(
            tmp_path, claim_id="c1", developer="alice", scope=["src/module_a/"], status="active",
        )
        guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path)))
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "src/module_a/x.py"})
        assert verdict.block is True
        assert verdict.gate == "B"
        assert verdict.reason is not None
        assert "alice" in verdict.reason
        assert "c1" in verdict.reason

    def test_non_conflicting_edit_passes(self, tmp_path):
        claims_path = self._make_claims(
            tmp_path, claim_id="c1", developer="alice", scope=["src/module_a/"], status="active",
        )
        guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path)))
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "src/module_b/x.py"})
        assert verdict.block is False

    def test_bash_is_excluded_from_scoped_tool_names(self, tmp_path):
        claims_path = self._make_claims(
            tmp_path, claim_id="c1", developer="alice", scope=["src/module_a/"], status="active",
        )
        guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path)))
        verdict = guardrail.check_before_tool_call(
            "t1", "bash", {"command": "rm -rf src/module_a/"},
        )
        assert verdict.block is False

    def test_read_and_write_are_covered_by_default(self, tmp_path):
        claims_path = self._make_claims(
            tmp_path, claim_id="c1", developer="alice", scope=["src/module_a/"], status="active",
        )
        guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path)))
        assert guardrail.check_before_tool_call("t1", "read", {"file": "src/module_a/x.py"}).block is True
        assert guardrail.check_before_tool_call("t1", "write", {"file": "src/module_a/x.py"}).block is True

    def test_no_path_param_skips_check_without_error(self, tmp_path):
        claims_path = self._make_claims(
            tmp_path, claim_id="c1", developer="alice", scope=["src/module_a/"], status="active",
        )
        guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path)))
        verdict = guardrail.check_before_tool_call("t1", "edit", {"content": "no path key here"})
        assert verdict.block is False

    def test_fail_on_conflict_false_does_not_block(self, tmp_path):
        claims_path = self._make_claims(
            tmp_path, claim_id="c1", developer="alice", scope=["src/module_a/"], status="active",
        )
        guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(
            claims_path=str(claims_path), fail_on_conflict=False,
        ))
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "src/module_a/x.py"})
        assert verdict.block is False

    def test_claims_loaded_once_not_per_call(self, tmp_path):
        """생성자 시점 이후 claims_path에 추가된 클레임은 세션 중 반영되지 않는다."""
        claims_path = tmp_path / "claims.jsonl"
        guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path)))
        append_claim(claims_path, claim_id="c1", developer="alice", scope=["src/module_a/"], status="active")
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "src/module_a/x.py"})
        assert verdict.block is False  # 아직 캐시에 반영 안 됨

    def test_shared_files_block_regardless_of_claims(self, tmp_path):
        shared_path = tmp_path / "shared.txt"
        shared_path.write_text("src/shared_config.yaml\n", encoding="utf-8")
        guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(
            claims_path=str(tmp_path / "no_such_claims.jsonl"), shared_files_path=str(shared_path),
        ))
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "src/shared_config.yaml"})
        assert verdict.block is True
        assert verdict.reason is not None
        assert "shared file" in verdict.reason


class TestRecordBlockedAttemptIntegration:
    """REQ-5: 신규 차단 유형도 record_blocked_attempt()로 코드 변경 없이 기록된다."""

    def test_team_concurrency_block_recorded(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(claims_path, claim_id="c1", developer="alice", scope=["src/module_a/"], status="active")
        guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path)))
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "src/module_a/x.py"})
        guardrail.record_blocked_attempt("t1", "edit", verdict)
        assert guardrail.snapshot()["blocked_attempts"] == [
            {"tool_name": "edit", "gate": "B", "reason": verdict.reason},
        ]


class TestRefreshTeamClaims:
    """REQ-6: refresh_team_claims()."""

    def test_refresh_picks_up_new_claim(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        guardrail = LiveGuardrail(team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path)))
        append_claim(claims_path, claim_id="c1", developer="alice", scope=["src/module_a/"], status="active")

        before = guardrail.check_before_tool_call("t1", "edit", {"file": "src/module_a/x.py"})
        assert before.block is False

        guardrail.refresh_team_claims()
        after = guardrail.check_before_tool_call("t1", "edit", {"file": "src/module_a/x.py"})
        assert after.block is True

    def test_no_op_when_team_concurrency_not_configured(self):
        guardrail = LiveGuardrail()
        guardrail.refresh_team_claims()  # 예외 없이 아무 일도 하지 않음
