"""
tests/test_reporting_history.py
===================================
SPEC-041 P13 — longitudinal view. ``reporting/history.py`` scans sibling result
JSON files so a single static report can say "Gate D is down N runs in a row"
without a database.
"""
from __future__ import annotations

import json

from agent_evaluator.reporting.history import (
    load_change_ledger,
    scan_history,
    trend_summary,
)


def _write_run(d, name, gate_scores, *, tcr=80.0, ts="2026-08-30T10:00:00"):
    data = {
        "timestamp": ts,
        "accuracy_metrics": {"tcr": {"tcr": tcr}},
        "tasks": [],
        "extra_metrics": {
            "harness_groups": {
                **{g: {"score": s} for g, s in gate_scores.items()},
                "overall": {"score": sum(gate_scores.values()) / len(gate_scores)},
            }
        },
    }
    (d / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


class TestScanHistory:
    def test_orders_by_timestamp_and_reads_scores(self, tmp_path):
        _write_run(tmp_path, "b", {"A": 0.7, "D": 0.6}, ts="2026-08-30T11:00:00")
        _write_run(tmp_path, "a", {"A": 0.9, "D": 0.9}, ts="2026-08-30T09:00:00")
        hist = scan_history(tmp_path)
        assert [r["file"] for r in hist] == ["a.json", "b.json"]
        assert hist[0]["gate_scores"]["D"] == 0.9

    def test_skips_baseline_and_bad_files(self, tmp_path):
        _write_run(tmp_path, "run1", {"A": 0.8})
        (tmp_path / "baseline.json").write_text('{"x":1}', encoding="utf-8")
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        hist = scan_history(tmp_path)
        assert [r["file"] for r in hist] == ["run1.json"]

    def test_excludes_current_file(self, tmp_path):
        _write_run(tmp_path, "old", {"A": 0.8}, ts="2026-08-30T09:00:00")
        _write_run(tmp_path, "cur", {"A": 0.5}, ts="2026-08-30T10:00:00")
        hist = scan_history(tmp_path, exclude=tmp_path / "cur.json")
        assert [r["file"] for r in hist] == ["old.json"]

    def test_missing_dir_returns_empty(self, tmp_path):
        assert scan_history(tmp_path / "nope") == []


class TestTrendSummary:
    def test_counts_trailing_consecutive_declines(self, tmp_path):
        for i, d in enumerate([0.9, 0.8, 0.7, 0.6]):
            _write_run(tmp_path, f"r{i}", {"D": d}, ts=f"2026-08-30T1{i}:00:00")
        summ = trend_summary(scan_history(tmp_path))
        assert summ["gates"]["D"]["consecutive_decline"] == 3
        assert summ["gates"]["D"]["slope"] == -0.3

    def test_recovery_breaks_the_streak(self, tmp_path):
        for i, d in enumerate([0.9, 0.6, 0.7, 0.75]):
            _write_run(tmp_path, f"r{i}", {"D": d}, ts=f"2026-08-30T1{i}:00:00")
        summ = trend_summary(scan_history(tmp_path))
        assert summ["gates"]["D"]["consecutive_decline"] == 0

    def test_fewer_than_two_runs_no_gates(self, tmp_path):
        _write_run(tmp_path, "only", {"D": 0.9})
        assert trend_summary(scan_history(tmp_path))["gates"] == {}


class TestChangeLedger:
    def test_reads_jsonl_newest_first(self, tmp_path):
        lines = [
            {"recorded_at": "2026-08-01T00:00:00", "target_gate": "A", "verdict": "refuted"},
            {"recorded_at": "2026-08-02T00:00:00", "target_gate": "D", "verdict": "confirmed"},
        ]
        (tmp_path / "recommendation_outcomes.jsonl").write_text(
            "\n".join(json.dumps(x) for x in lines), encoding="utf-8"
        )
        led = load_change_ledger(tmp_path)
        assert led[0]["target_gate"] == "D"
        assert len(led) == 2

    def test_absent_file_is_empty(self, tmp_path):
        assert load_change_ledger(tmp_path) == []

    def test_tolerates_a_corrupt_line(self, tmp_path):
        (tmp_path / "recommendation_outcomes.jsonl").write_text(
            '{"target_gate": "A"}\n{bad\n{"target_gate": "B"}\n', encoding="utf-8"
        )
        led = load_change_ledger(tmp_path)
        assert {r["target_gate"] for r in led} == {"A", "B"}


class TestReportIntegration:
    def test_report_shows_trend_and_ledger(self, tmp_path):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.core.trackers.base import TaskResult
        from agent_evaluator.reporting.comprehensive_report import (
            generate_comprehensive_html_report,
        )

        for run in range(4):
            m = PerformanceMonitor(output_dir=str(tmp_path))
            for i in range(10):
                ok = i < (8 - run)
                m.record_task(TaskResult(
                    task_id=f"t{i}", task_type="qa", success=ok,
                    completion_score=1.0 if ok else 0.0,
                    accuracy_score=0.9 if ok else 0.2,
                    execution_time=1.0 + run * 3.0, tokens_used={"total": 100},
                    tool_calls=[], attempts=1, errors=[], question="q",
                    response="a", ground_truth="a",
                ))
            m.save_to_file(f"run{run}")
        (tmp_path / "recommendation_outcomes.jsonl").write_text(
            json.dumps({
                "recorded_at": "2026-08-30T10:00:00", "recommendation_id": "add SLAConfig",
                "target_gate": "D", "verdict": "confirmed", "gate_delta": 0.1,
            }) + "\n", encoding="utf-8",
        )
        html = generate_comprehensive_html_report(m)
        assert 'id="history-trend"' in html
        assert "<polyline" in html
        assert 'id="change-ledger"' in html
        assert "add SLAConfig" in html
