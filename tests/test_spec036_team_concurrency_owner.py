"""
tests/test_spec036_team_concurrency_owner.py
================================================
SPEC-036: TeamConcurrencyConfig.owner — 자기 자신의 클레임을 충돌로 오판하지 않기.

발견 경위: Ch29 §29.10 캡스톤 실습을 실제로 실행해 검증하던 중, 개발자가 자기
스코프를 클레임한 뒤 그 스코프를 편집하면 TeamConcurrencyConfig가 이를 차단하는
버그를 발견(자기 자신의 클레임도 무조건 "충돌"로 잡힘 — LiveGuardrail은 "이 세션이
누구의 것인지" 알 방법이 없었기 때문).

REQ-1/2: owner 설정 시 자기 자신의 클레임 제외, 다른 개발자 클레임은 여전히 차단.
REQ-2 회귀: owner 미설정(기본값) 시 기존 동작(자기 클레임도 차단) 그대로 보존.
REQ-3: shared_files_path 검사는 owner 예외의 영향을 받지 않는다.
"""
from __future__ import annotations

from agent_evaluator.gates.live_guardrail import LiveGuardrail
from agent_evaluator.gates.team_concurrency import TeamConcurrencyConfig, append_claim


class TestOwnerExcludesOwnClaim:
    def test_owner_not_blocked_by_own_claim(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="수아", scope=["configs.py"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        guardrail = LiveGuardrail(
            team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path), owner="수아"),
        )
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "configs.py"})
        assert verdict.block is False

    def test_owner_still_blocked_by_other_developer_claim(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="태호", scope=["evaluators.py"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        guardrail = LiveGuardrail(
            team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path), owner="수아"),
        )
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "evaluators.py"})
        assert verdict.block is True
        assert "태호" in verdict.reason

    def test_mixed_claims_own_excluded_others_still_conflict(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="수아", scope=["shared/"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        append_claim(
            claims_path, claim_id="c2", developer="태호", scope=["shared/"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        guardrail = LiveGuardrail(
            team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path), owner="수아"),
        )
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "shared/x.py"})
        # 태호의 겹치는 클레임이 남아 있으므로 여전히 차단돼야 함
        assert verdict.block is True
        assert "태호" in verdict.reason


class TestOwnerUnsetPreservesLegacyBehavior:
    def test_own_claim_still_blocks_when_owner_not_set(self, tmp_path):
        """회귀 확인: owner 미설정(기본값)이면 자기 자신의 클레임도 여전히
        (기존과 동일하게) 충돌로 잡힌다 — 이 테스트가 실패하면 기본 동작이
        의도치 않게 바뀐 것."""
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="수아", scope=["configs.py"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        guardrail = LiveGuardrail(
            team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path)),
        )
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "configs.py"})
        assert verdict.block is True


class TestOwnerDoesNotAffectSharedFiles:
    def test_shared_file_still_blocks_owner(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        claims_path.write_text("", encoding="utf-8")
        shared_path = tmp_path / "shared_files.txt"
        shared_path.write_text("critical/config.yaml\n", encoding="utf-8")
        guardrail = LiveGuardrail(
            team_concurrency=TeamConcurrencyConfig(
                claims_path=str(claims_path),
                shared_files_path=str(shared_path),
                owner="수아",
            ),
        )
        verdict = guardrail.check_before_tool_call(
            "t1", "edit", {"file": "critical/config.yaml"},
        )
        assert verdict.block is True
