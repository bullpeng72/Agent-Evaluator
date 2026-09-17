"""
tests/test_autopilot_sdk_contract.py
=====================================
Harness Autopilot는 agent_evaluator 패키지 안에 있지만, 자기가 직접 채점/기록
하지 않는 두 SDK 내부 함수 — ``team_concurrency.load_active_claims()``와
``rca.decision_ledger.load_decisions()`` — 를 그대로 읽어서 화면에 낸다
(``serve/autopilot_app.py``의 운영 현황 페이지, ``gates/autopilot_state.py``의
``detect_repeated_undecided()``).

지금까지 이 의존은 코드 어딘가에 암묵적으로만 존재했다 — team_concurrency.py나
decision_ledger.py를 고치는 사람이 Autopilot 쪽 테스트를 몰랐다면, 반환 모양이
바뀌어도 Autopilot 전용 테스트가 없는 한 아무것도 안 알려줬다. 이 파일은 그
암묵적 의존을 SDK 쪽 함수 이름으로 직접 걸어 명시적 계약으로 만든다 — 이
테스트가 깨지면 "Autopilot도 같이 손봐야 한다"는 신호다.

이 계약은 Harness Autopilot이 나중에 별도 배포판으로 분리될 때도 유효하다 —
그 시점엔 여기서 고정하는 두 함수(와 ``.aoo/*.jsonl`` 파일 포맷 자체,
``Docs/specs/SPEC-AP-001-harness-autopilot.md`` §인터페이스)가 사실상 두 패키지
사이의 공개 API가 된다.
"""
from __future__ import annotations

from agent_evaluator.gates.team_concurrency import append_claim, load_active_claims
from agent_evaluator.rca.decision_ledger import (
    load_decisions,
    record_decision_outcome,
    record_gate_decision,
)


class TestClaimsContractForAutopilot:
    """``serve/autopilot_app.py::_safe_claims()``(운영 현황 페이지)가 기대하는 모양."""

    def test_active_claim_has_fields_autopilot_renders(self, tmp_path):
        path = tmp_path / "claims.jsonl"
        append_claim(
            path, claim_id="c-1", developer="수아", scope=["src/x.py"],
            started_at="2026-09-16T00:00:00+00:00", status="active",
        )
        claims = load_active_claims(path)
        assert len(claims) == 1
        # _ops_body()가 그대로 읽는 세 필드 — 이름이 바뀌면 대시보드가 깨진다
        assert {"developer", "scope", "claim_id"} <= claims[0].keys()
        assert isinstance(claims[0]["scope"], list)

    def test_released_claim_disappears_from_active_list(self, tmp_path):
        path = tmp_path / "claims.jsonl"
        append_claim(
            path, claim_id="c-1", developer="수아", scope=["src/x.py"],
            started_at="2026-09-16T00:00:00+00:00", status="active",
        )
        append_claim(path, claim_id="c-1", status="released")
        assert load_active_claims(path) == []

    def test_missing_file_is_empty_list_not_an_exception(self, tmp_path):
        # autopilot_app._safe_claims()는 이 함수가 예외를 던지지 않는다는 데 기댄다
        # (기대와 어긋나면 try/except가 조용히 삼키긴 하지만, 계약 자체는 이거다)
        assert load_active_claims(tmp_path / "nope.jsonl") == []


class TestDecisionLedgerContractForAutopilot:
    """``gates/autopilot_state.py::detect_repeated_undecided()``와

    ``serve/autopilot_app.py::_ops_body()``가 기대하는 모양.
    """

    def test_gate_run_entry_has_fields_autopilot_reads(self, tmp_path):
        path = tmp_path / "decisions.jsonl"
        record_gate_decision(
            path, result_file="r.json", agent_version="v1", exit_code=75,
            verdict_level="not_ready", decision_ready=False,
            undecided_reason="사유", gate_scores={"A": 0.7},
        )
        entries = load_decisions(path)
        assert len(entries) == 1
        entry = entries[0]
        # detect_repeated_undecided()가 그대로 읽는 필드들
        for field in ("kind", "id", "exit_code", "undecided_reason"):
            assert field in entry
        assert entry["kind"] == "gate_run"
        assert entry["exit_code"] == 75

    def test_missing_file_is_empty_list_not_an_exception(self, tmp_path):
        assert load_decisions(tmp_path / "nope.jsonl") == []

    def test_gate_run_and_outcome_entries_both_come_back_unfiltered(self, tmp_path):
        """detect_repeated_undecided()가 kind로 직접 걸러내므로,

        load_decisions()가 outcome 엔트리까지 섞어서 돌려줘도 괜찮아야 한다 —
        필터링 책임은 SDK가 아니라 Autopilot 쪽에 있다는 계약이다.
        """
        path = tmp_path / "decisions.jsonl"
        record_gate_decision(
            path, result_file="r.json", agent_version="v1", exit_code=0,
            verdict_level="ready", decision_ready=True,
        )
        record_decision_outcome(path, outcome="accepted", decided_by="pm")
        entries = load_decisions(path)
        assert len(entries) == 2
        assert {e["kind"] for e in entries} == {"gate_run", "outcome"}

    def test_exit_75_without_undecided_reason_is_still_readable(self, tmp_path):
        """undecided_reason은 선택 필드다 — detect_repeated_undecided()는

        이게 없는 gate_run 엔트리를 안전하게 건너뛰어야 한다(에러 아님).
        """
        path = tmp_path / "decisions.jsonl"
        record_gate_decision(
            path, result_file="r.json", agent_version="v1", exit_code=75,
            verdict_level="not_ready", decision_ready=False,
        )
        entries = load_decisions(path)
        assert "undecided_reason" not in entries[0]
