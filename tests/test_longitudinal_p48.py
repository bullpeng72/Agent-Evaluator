"""
tests/test_longitudinal_p48.py
==============================
SPEC-041 P48 — insights.longitudinal: cross-run intelligence built from the
sibling result JSONs in a directory (recurring / flapping failure signatures,
eval-set TCR noise band, run cadence).
"""
from __future__ import annotations

import json
from pathlib import Path

from agent_evaluator.reporting.insights import _longitudinal_section, build_insights


def _run(tid_fail: set[str], *, ts: str, n: int = 8) -> dict:
    tasks = []
    for i in range(n):
        tid = f"t{i}"
        failing = tid in tid_fail
        tasks.append({
            "task_id": tid, "task_type": "qa", "question": f"question number {i}",
            "response": "r", "ground_truth": "g",
            "success": not failing,
            "accuracy_score": 0.3 if failing else 0.9,
            "completion_score": 0.2 if failing else 1.0,
            "partial_reason": "error: TimeoutError" if failing else "",
        })
    return {"timestamp": ts, "extra_metrics": {"harness_groups": {}}, "tasks": tasks}


def _write_series(d: Path, specs: list[tuple[str, set[str], str]]) -> None:
    for name, fails, ts in specs:
        (d / f"{name}.json").write_text(json.dumps(_run(fails, ts=ts)),
                                        encoding="utf-8")


def test_none_when_dir_missing_or_too_few(tmp_path):
    assert _longitudinal_section(None) is None
    assert _longitudinal_section(tmp_path / "nope") is None
    _write_series(tmp_path, [
        ("a", {"t1"}, "2026-01-01T00:00:00"),
        ("b", {"t1"}, "2026-01-08T00:00:00"),
    ])
    # 2 runs < _LONG_MIN_RUNS
    assert _longitudinal_section(tmp_path) is None


def test_recurring_and_chronic_classification(tmp_path):
    _write_series(tmp_path, [
        ("r1", {"t1", "t2"}, "2026-01-01T00:00:00"),
        ("r2", {"t1", "t3"}, "2026-01-08T00:00:00"),
        ("r3", {"t1"},       "2026-01-15T00:00:00"),
        ("r4", {"t1", "t2"}, "2026-01-22T00:00:00"),
        ("r5", {"t1", "t2"}, "2026-01-29T00:00:00"),
    ])
    lg = _longitudinal_section(tmp_path)
    assert lg is not None
    assert lg["n_runs"] == 5
    rec = lg["recurring_failures"]
    assert rec, "expected at least one recurring signature"
    # t1 fails every run -> its signature is chronic, ranked first
    top = rec[0]
    assert top["kind"] == "chronic"
    assert top["in_n_runs"] == 5 and top["of_runs"] == 5
    assert top["currently_failing"] is True
    assert "every one of the last 5" in top["note"]


def test_current_file_is_excluded(tmp_path):
    _write_series(tmp_path, [
        ("r1", {"t1"}, "2026-01-01T00:00:00"),
        ("r2", {"t1"}, "2026-01-08T00:00:00"),
        ("r3", {"t1"}, "2026-01-15T00:00:00"),
        ("r4", {"t1"}, "2026-01-22T00:00:00"),
        ("cur", {"t1"}, "2026-01-29T00:00:00"),
    ])
    lg = _longitudinal_section(tmp_path, tmp_path / "cur.json")
    assert lg is not None
    assert lg["n_runs"] == 4
    assert "cur.json" not in lg["run_files"]


def test_eval_set_stability_and_cadence(tmp_path):
    # identical question set across all -> same fingerprint -> stability computed
    _write_series(tmp_path, [
        ("r1", set(),        "2026-01-01T00:00:00"),
        ("r2", {"t0"},       "2026-01-08T00:00:00"),
        ("r3", {"t0", "t1"}, "2026-01-15T00:00:00"),
        ("r4", {"t1"},       "2026-01-22T00:00:00"),
    ])
    lg = _longitudinal_section(tmp_path)
    assert lg is not None
    st = lg["eval_set_stability"]
    assert st and st["n_runs_same_eval_set"] == 4
    assert st["detectable_change_pp"] >= 0
    assert "eval set" in st["note"]
    cad = lg["cadence"]
    assert cad["median_days_between_runs"] == 7
    assert cad["last_gap_days"] == 7
    assert cad["n_intervals"] == 3


def test_baseline_json_is_skipped(tmp_path):
    _write_series(tmp_path, [
        ("r1", {"t1"}, "2026-01-01T00:00:00"),
        ("r2", {"t1"}, "2026-01-08T00:00:00"),
        ("r3", {"t1"}, "2026-01-15T00:00:00"),
        ("r4", {"t1"}, "2026-01-22T00:00:00"),
    ])
    (tmp_path / "baseline.json").write_text(
        json.dumps(_run({"t1", "t2", "t3"}, ts="2020-01-01T00:00:00")),
        encoding="utf-8",
    )
    lg = _longitudinal_section(tmp_path)
    assert lg is not None
    assert "baseline.json" not in lg["run_files"]
    assert lg["n_runs"] == 4


def test_end_to_end_build_insights_and_report(tmp_path):
    from agent_evaluator.reporting.comprehensive_report import _build_longitudinal

    _write_series(tmp_path, [
        ("r1", {"t1", "t2"}, "2026-01-01T00:00:00"),
        ("r2", {"t1"},       "2026-01-08T00:00:00"),
        ("r3", {"t1", "t2"}, "2026-01-15T00:00:00"),
        ("r4", {"t1"},       "2026-01-22T00:00:00"),
        ("r5", {"t1", "t2"}, "2026-01-29T00:00:00"),
    ])
    cur = json.loads((tmp_path / "r5.json").read_text())
    ins = build_insights(cur, history_dir=tmp_path, current_file=tmp_path / "r5.json")
    lg = ins["longitudinal"]
    assert lg and lg["n_runs"] == 4
    html = _build_longitudinal(lg)
    assert "Across Runs" in html and "Failure signature" in html
    assert _build_longitudinal(None) == ""


def test_never_raises_on_garbage(tmp_path):
    (tmp_path / "bad.json").write_text("{ not json", encoding="utf-8")
    (tmp_path / "empty.json").write_text("{}", encoding="utf-8")
    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    assert _longitudinal_section(tmp_path) is None
