"""
tests/test_phase4_recommendation_tracking.py
================================================
Phase 4(개선 엔진, 폐루프 학습) — rca.record_recommendation_outcome() /
load_recommendation_outcomes() / summarize_recommendation_outcomes()의 회귀 테스트.

이 모듈은 순수 로깅 계층(성공률 랭킹 없음, verify.py가 이미 경계한 그 선을 넘지
않는다)이라 전부 합성(synthetic) 데이터로 검증 가능하다 — 실사용 데이터 없이도
"기록한 그대로 조회되는가"·"집계가 산수적으로 맞는가"는 완전히 테스트할 수 있다.
"""
from __future__ import annotations

import json

from agent_evaluator.rca import (
    load_recommendation_outcomes,
    record_recommendation_outcome,
    summarize_recommendation_outcomes,
)


def _report(harness_groups: dict) -> dict:
    return {"extra_metrics": {"harness_groups": harness_groups}}


def _gate(score, **details):
    return {"score": score, "status": "pass", "gate": "pass", "details": details}


class TestRecordRecommendationOutcome:
    def test_appends_one_jsonl_line_with_verdict(self, tmp_path):
        log_path = tmp_path / "recs.jsonl"
        before = _report({"F": _gate(0.5)})
        after = _report({"F": _gate(0.85)})
        entry = record_recommendation_outcome(
            log_path, recommendation_id="mast-fm-3.2", target_gate="F",
            before=before, after=after,
        )
        assert entry["verdict"] == "confirmed"
        assert entry["recommendation_id"] == "mast-fm-3.2"
        assert "recorded_at" in entry

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["recommendation_id"] == "mast-fm-3.2"

    def test_creates_parent_directory(self, tmp_path):
        log_path = tmp_path / "nested" / "dir" / "recs.jsonl"
        before = _report({"A": _gate(0.5)})
        after = _report({"A": _gate(0.9)})
        record_recommendation_outcome(
            log_path, recommendation_id="r1", target_gate="A", before=before, after=after,
        )
        assert log_path.exists()

    def test_multiple_records_append_not_overwrite(self, tmp_path):
        log_path = tmp_path / "recs.jsonl"
        before = _report({"A": _gate(0.5)})
        after = _report({"A": _gate(0.9)})
        record_recommendation_outcome(
            log_path, recommendation_id="r1", target_gate="A", before=before, after=after,
        )
        record_recommendation_outcome(
            log_path, recommendation_id="r2", target_gate="A", before=before, after=after,
        )
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_note_and_target_field_recorded(self, tmp_path):
        log_path = tmp_path / "recs.jsonl"
        before = _report({"F": _gate(0.5, avg_consensus=0.4)})
        after = _report({"F": _gate(0.85, avg_consensus=0.9)})
        entry = record_recommendation_outcome(
            log_path, recommendation_id="r1", target_gate="F", before=before, after=after,
            target_field="avg_consensus", note="agent_role 프롬프트 재작성",
        )
        assert entry["note"] == "agent_role 프롬프트 재작성"
        assert entry["target_field_result"]["field"] == "avg_consensus"


class TestLoadRecommendationOutcomes:
    def test_empty_list_when_file_missing(self, tmp_path):
        assert load_recommendation_outcomes(tmp_path / "nonexistent.jsonl") == []

    def test_loads_all_entries_in_order(self, tmp_path):
        log_path = tmp_path / "recs.jsonl"
        before = _report({"A": _gate(0.5)})
        after = _report({"A": _gate(0.9)})
        record_recommendation_outcome(
            log_path, recommendation_id="r1", target_gate="A", before=before, after=after,
        )
        record_recommendation_outcome(
            log_path, recommendation_id="r2", target_gate="A", before=before, after=after,
        )
        outcomes = load_recommendation_outcomes(log_path)
        assert [o["recommendation_id"] for o in outcomes] == ["r1", "r2"]

    def test_filters_by_recommendation_id(self, tmp_path):
        log_path = tmp_path / "recs.jsonl"
        before = _report({"A": _gate(0.5)})
        after = _report({"A": _gate(0.9)})
        record_recommendation_outcome(
            log_path, recommendation_id="r1", target_gate="A", before=before, after=after,
        )
        record_recommendation_outcome(
            log_path, recommendation_id="r2", target_gate="A", before=before, after=after,
        )
        outcomes = load_recommendation_outcomes(log_path, recommendation_id="r1")
        assert len(outcomes) == 1
        assert outcomes[0]["recommendation_id"] == "r1"

    def test_filters_by_target_gate(self, tmp_path):
        log_path = tmp_path / "recs.jsonl"
        before_a = _report({"A": _gate(0.5)})
        after_a = _report({"A": _gate(0.9)})
        before_f = _report({"F": _gate(0.5)})
        after_f = _report({"F": _gate(0.9)})
        record_recommendation_outcome(
            log_path, recommendation_id="r1", target_gate="A", before=before_a, after=after_a,
        )
        record_recommendation_outcome(
            log_path, recommendation_id="r2", target_gate="F", before=before_f, after=after_f,
        )
        outcomes = load_recommendation_outcomes(log_path, target_gate="F")
        assert len(outcomes) == 1
        assert outcomes[0]["target_gate"] == "F"

    def test_skips_corrupted_lines_without_raising(self, tmp_path):
        log_path = tmp_path / "recs.jsonl"
        log_path.write_text(
            '{"recommendation_id": "good", "target_gate": "A", "verdict": "confirmed"}\n'
            "not valid json\n"
            "\n",
            encoding="utf-8",
        )
        outcomes = load_recommendation_outcomes(log_path)
        assert len(outcomes) == 1
        assert outcomes[0]["recommendation_id"] == "good"


class TestSummarizeRecommendationOutcomes:
    def test_empty_list_yields_zero_counts(self):
        summary = summarize_recommendation_outcomes([])
        assert summary["total"] == 0
        assert summary["confirmed"] == 0
        assert summary["by_gate"] == {}

    def test_counts_by_verdict(self):
        outcomes = [
            {"target_gate": "A", "verdict": "confirmed"},
            {"target_gate": "A", "verdict": "confirmed"},
            {"target_gate": "A", "verdict": "refuted"},
            {"target_gate": "F", "verdict": "inconclusive"},
        ]
        summary = summarize_recommendation_outcomes(outcomes)
        assert summary["total"] == 4
        assert summary["confirmed"] == 2
        assert summary["refuted"] == 1
        assert summary["inconclusive"] == 1

    def test_by_gate_breakdown(self):
        outcomes = [
            {"target_gate": "A", "verdict": "confirmed"},
            {"target_gate": "A", "verdict": "refuted"},
            {"target_gate": "F", "verdict": "confirmed"},
        ]
        summary = summarize_recommendation_outcomes(outcomes)
        assert summary["by_gate"]["A"] == {
            "total": 2, "confirmed": 1, "refuted": 1, "inconclusive": 0,
        }
        assert summary["by_gate"]["F"] == {
            "total": 1, "confirmed": 1, "refuted": 0, "inconclusive": 0,
        }

    def test_no_ranking_or_rate_fields_present(self):
        """의도적 범위 제한 확인 — 순위·비율(성공률) 필드가 없어야 한다
        (verify.py가 경계한 "검증 불가능한 통계"를 만들지 않는다)."""
        summary = summarize_recommendation_outcomes([{"target_gate": "A", "verdict": "confirmed"}])
        assert "rank" not in summary
        assert "success_rate" not in summary
        assert "ranking" not in summary

    def test_integration_with_load_recommendation_outcomes(self, tmp_path):
        log_path = tmp_path / "recs.jsonl"
        before = _report({"A": _gate(0.5)})
        confirmed_after = _report({"A": _gate(0.9)})
        refuted_after = _report({"A": _gate(0.2)})
        record_recommendation_outcome(
            log_path, recommendation_id="r1", target_gate="A", before=before, after=confirmed_after,
        )
        record_recommendation_outcome(
            log_path, recommendation_id="r2", target_gate="A", before=before, after=refuted_after,
        )
        summary = summarize_recommendation_outcomes(load_recommendation_outcomes(log_path))
        assert summary["confirmed"] == 1
        assert summary["refuted"] == 1
