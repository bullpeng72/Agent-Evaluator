"""
tests/test_spec034_claim_audit.py
=====================================
SPEC-034: audit_claims() — 클레임 로그 CI 감사.

REQ-1: load_active_claims()(SPEC-032) 재사용 — 해제된 클레임은 위반 대상에서 제외.
REQ-2: TTL 판정(타임존 offset-aware/naive 둘 다 예외 없이 처리).
REQ-3: 스코프 겹침 판정(_scopes_overlap() prefix 매칭 재사용, set&set 완전 일치 아님).
REQ-4: 위반 없으면 빈 리스트, sys.exit() 호출 없음.
"""
from __future__ import annotations

from agent_evaluator.gates.team_concurrency import append_claim, audit_claims


class TestAuditClaimsReleasedClaimsExcluded:
    """REQ-1: load_active_claims()의 latest-per-claim_id 규칙을 재사용 — 해제된
    클레임을 다시 위반으로 잡는 회귀를 방지한다(외부 검토안에서 발견한 버그 재현)."""

    def test_released_claim_not_flagged_for_ttl(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["x/"],
            started_at="2020-01-01T00:00:00+09:00", status="active",  # 오래전 — TTL 초과 조건
        )
        append_claim(claims_path, claim_id="c1", status="released")
        violations = audit_claims(claims_path, ttl_hours=8)
        assert violations == []

    def test_released_claim_not_flagged_for_overlap(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["x/"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        append_claim(claims_path, claim_id="c1", status="released")
        append_claim(
            claims_path, claim_id="c2", developer="alice", scope=["x/"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        violations = audit_claims(claims_path, ttl_hours=8)
        assert violations == []


class TestAuditClaimsTTL:
    def test_old_claim_flagged_with_tz_aware_timestamp(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["x/"],
            started_at="2020-01-01T00:00:00+09:00", status="active",
        )
        violations = audit_claims(claims_path, ttl_hours=8)
        assert len(violations) == 1
        assert violations[0]["type"] == "ttl_exceeded"
        assert violations[0]["claim_id"] == "c1"

    def test_old_claim_flagged_with_naive_timestamp(self, tmp_path):
        """타임존 오프셋이 없는(naive) 타임스탬프도 예외 없이 처리된다."""
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["x/"],
            started_at="2020-01-01T00:00:00", status="active",
        )
        violations = audit_claims(claims_path, ttl_hours=8)
        assert len(violations) == 1
        assert violations[0]["type"] == "ttl_exceeded"

    def test_recent_claim_not_flagged(self, tmp_path):
        from datetime import datetime, timezone

        claims_path = tmp_path / "claims.jsonl"
        now_iso = datetime.now(timezone.utc).isoformat()
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["x/"],
            started_at=now_iso, status="active",
        )
        violations = audit_claims(claims_path, ttl_hours=8)
        assert violations == []

    def test_missing_started_at_skipped_without_error(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(claims_path, claim_id="c1", developer="sungwoo", scope=["x/"], status="active")
        violations = audit_claims(claims_path, ttl_hours=8)  # 예외 없이 통과
        assert violations == []

    def test_malformed_started_at_skipped_without_error(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["x/"],
            started_at="not-a-timestamp", status="active",
        )
        violations = audit_claims(claims_path, ttl_hours=8)
        assert violations == []


class TestAuditClaimsOverlap:
    def test_exact_scope_overlap_detected(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["x/"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        append_claim(
            claims_path, claim_id="c2", developer="alice", scope=["x/"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        violations = audit_claims(claims_path, ttl_hours=8)
        overlaps = [v for v in violations if v["type"] == "overlapping_claims"]
        assert len(overlaps) == 1
        assert {overlaps[0]["developer_a"], overlaps[0]["developer_b"]} == {"sungwoo", "alice"}

    def test_prefix_overlap_detected_not_just_exact_match(self, tmp_path):
        """set & set(완전 일치만)이 아니라 prefix 매칭으로 겹침을 잡는다 —
        외부 검토안(set 교집합만 확인)이 놓치는 케이스."""
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["gates/gate_d/"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        append_claim(
            claims_path, claim_id="c2", developer="alice", scope=["gates/gate_d/aggregate.py"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        violations = audit_claims(claims_path, ttl_hours=8)
        overlaps = [v for v in violations if v["type"] == "overlapping_claims"]
        assert len(overlaps) == 1

    def test_non_overlapping_scopes_not_flagged(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["x/"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        append_claim(
            claims_path, claim_id="c2", developer="alice", scope=["y/"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        violations = audit_claims(claims_path, ttl_hours=8)
        assert violations == []

    def test_three_claims_pair_not_double_reported(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        for cid, dev in [("c1", "a"), ("c2", "b"), ("c3", "c")]:
            append_claim(
                claims_path, claim_id=cid, developer=dev, scope=["x/"],
                started_at="2026-07-08T09:00:00+09:00", status="active",
            )
        violations = audit_claims(claims_path, ttl_hours=8)
        overlaps = [v for v in violations if v["type"] == "overlapping_claims"]
        assert len(overlaps) == 3  # (c1,c2) (c1,c3) (c2,c3) — 각 쌍 정확히 1회


class TestAuditClaimsEmptyOrClean:
    def test_no_claims_file_returns_empty_list(self, tmp_path):
        claims_path = tmp_path / "no_such_file.jsonl"
        assert audit_claims(claims_path, ttl_hours=8) == []

    def test_clean_non_overlapping_recent_claims_return_empty(self, tmp_path):
        from datetime import datetime, timezone

        claims_path = tmp_path / "claims.jsonl"
        now_iso = datetime.now(timezone.utc).isoformat()
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["x/"],
            started_at=now_iso, status="active",
        )
        append_claim(
            claims_path, claim_id="c2", developer="alice", scope=["y/"],
            started_at=now_iso, status="active",
        )
        assert audit_claims(claims_path, ttl_hours=8) == []

    def test_returns_list_not_raises_and_no_sys_exit(self, tmp_path):
        """audit_claims() 자체는 sys.exit()을 호출하지 않는다 — 호출자의 몫."""
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="sungwoo", scope=["x/"],
            started_at="2020-01-01T00:00:00+09:00", status="active",
        )
        result = audit_claims(claims_path, ttl_hours=8)
        assert isinstance(result, list)
        assert len(result) > 0  # 위반이 있어도 예외 없이 리스트로 반환
