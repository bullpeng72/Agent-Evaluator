"""
tests/test_golden_health_p58.py
===============================
SPEC-041 P58 — golden-set health: does the golden set still exercise the
failure modes being seen, and which cases are stale / duplicate.
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator.datasets.golden_health import (
    assess_golden_health,
    load_golden_cases,
)
from agent_evaluator.reporting.insights import build_insights


def _t(tid, comp, acc, ok, q, reason=None):
    return {"task_id": tid, "task_type": "qa", "completion_score": comp,
            "accuracy_score": acc, "success": ok, "question": q, "response": "r",
            "ground_truth": "x", "partial_reason": reason}


def _run_with_taxonomy(tasks):
    res = {"extra_metrics": {"harness_groups": {}}, "tasks": tasks}
    res["extra_metrics"]["insights"] = build_insights(res)
    return res


# ---- loader -----------------------------------------------------------------

def test_load_cases_forms():
    assert len(load_golden_cases([{"question": "a"}, {"question": "b"}])) == 2
    assert len(load_golden_cases({"items": [{"question": "a"}]})) == 1
    assert len(load_golden_cases({"cases": [{"question": "a"}]})) == 1
    assert load_golden_cases({"nope": 1}) == []


def test_load_from_path(tmp_path):
    p = tmp_path / "g.json"
    p.write_text(json.dumps({"items": [{"question": "q1"}]}))
    assert len(load_golden_cases(str(p))) == 1
    assert load_golden_cases(str(tmp_path / "missing.json")) == []


# ---- assess ---------------------------------------------------------------

def test_none_without_cases():
    assert assess_golden_health([], {"tasks": []}) is None


def test_uncovered_failure_modes_are_the_blind_spot():
    golden = {"items": [
        {"question": "How do I return an item?", "ground_truth": "14 days."},
        {"question": "What is your phone number?", "ground_truth": "1-800",
         "accuracy_score": 0.98},
    ]}
    tasks = [_t("p1", 1.0, 0.98, True, "What is your phone number?")]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, f"track order {i}",
                 "error: TimeoutError") for i in range(4)]
    tasks += [_t(f"m{i}", 0.3, 0.2, False, f"multi step warranty claim {i}",
                 "only part of a multi-step answer completed") for i in range(3)]
    h = assess_golden_health(golden, _run_with_taxonomy(tasks))
    codes = {u["code"] for u in h["uncovered_failure_modes"]}
    assert "RUNTIME_ERROR" in codes and "PREMATURE_STOP" in codes
    assert h["coverage_pct"] == 0.0
    assert h["n_cases"] == 2
    assert "not exercised" in h["note"]


def test_covered_mode_raises_coverage():
    golden = {"items": [
        {"question": "track order 1 please", "ground_truth": "use the portal"},
    ]}
    tasks = [_t("p1", 1.0, 0.9, True, "hello")]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, f"track order {i}",
                 "error: TimeoutError") for i in range(4)]
    h = assess_golden_health(golden, _run_with_taxonomy(tasks))
    assert h["coverage_pct"] == 100.0
    assert h["uncovered_failure_modes"] == []


def test_stale_case_flagged_and_streak(tmp_path):
    golden = {"items": [
        {"question": "what is your phone number", "ground_truth": "1-800"},
    ]}
    tasks = [_t("p1", 1.0, 0.97, True, "what is your phone number")]
    # history: 4 prior runs where the same question passed
    for i in range(4):
        (tmp_path / f"r{i}.json").write_text(json.dumps({
            "timestamp": f"2026-01-0{i + 1}T00:00:00",
            "tasks": [_t("p1", 1.0, 0.95, True, "what is your phone number")]}))
    h = assess_golden_health(golden, {"tasks": tasks, "extra_metrics": {}},
                             history_dir=str(tmp_path))
    assert h["stale_cases"]
    s = h["stale_cases"][0]
    assert s["passed_streak"] >= 4 and "phone number" in s["question"]


def test_redundant_near_duplicates():
    golden = {"items": [
        {"question": "how do I reset my password on the account settings page"},
        {"question": "how do I reset my password on the account settings page?"},
        {"question": "what are your opening hours"},
    ]}
    h = assess_golden_health(golden, {"tasks": [], "extra_metrics": {}})
    assert h["redundant_cases"]
    assert h["redundant_cases"][0]["duplicate_of"] == 0


# ---- build_insights + CLI ------------------------------------------------

def test_build_insights_golden_set_path(tmp_path):
    golden = {"items": [{"question": "track order", "ground_truth": "portal"}]}
    gp = tmp_path / "golden.json"
    gp.write_text(json.dumps(golden))
    tasks = [_t(f"to{i}", 0.0, 0.0, False, f"track order {i}",
                "error: TimeoutError") for i in range(4)]
    ins = build_insights({"extra_metrics": {"harness_groups": {}}, "tasks": tasks},
                         golden_set_path=str(gp))
    assert ins["golden_health"] is not None
    assert build_insights(
        {"extra_metrics": {"harness_groups": {}}, "tasks": tasks})["golden_health"] is None


def test_cli_dataset_health(tmp_path, capsys):
    from agent_evaluator.cli.dataset import _cmd_health

    golden = {"items": [
        {"question": "what is your phone number", "ground_truth": "1-800"},
    ]}
    gp = tmp_path / "golden.json"
    gp.write_text(json.dumps(golden))
    tasks = [_t(f"to{i}", 0.0, 0.0, False, f"track order {i}",
                "error: TimeoutError") for i in range(4)]
    rp = tmp_path / "result.json"
    rp.write_text(json.dumps({"extra_metrics": {"harness_groups": {}}, "tasks": tasks}))
    rc = _cmd_health(argparse.Namespace(
        golden_file=str(gp), against=str(rp), history=None, as_json=True))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["n_cases"] == 1 and out["uncovered_failure_modes"]


def test_report_render():
    from agent_evaluator.reporting.comprehensive_report import _build_golden_health

    gh = assess_golden_health(
        {"items": [{"question": "phone number", "ground_truth": "x"}]},
        _run_with_taxonomy([_t(f"to{i}", 0.0, 0.0, False, f"track {i}",
                               "error: TimeoutError") for i in range(4)]),
    )
    html = _build_golden_health(gh)
    assert "Golden-Set Health" in html and "coverage" in html.lower()
    assert _build_golden_health(None) == ""
