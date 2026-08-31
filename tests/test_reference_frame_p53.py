"""
tests/test_reference_frame_p53.py
=================================
SPEC-041 P53 — external reference frame: .aoo/reference.json + insights.
reference_frame (percentile + gap to the frontier).
"""
from __future__ import annotations

import json

from agent_evaluator.reporting.insights import _reference_frame_section, build_insights
from agent_evaluator.utils.reference import (
    load_reference,
    percentile_of,
    percentiles_from_values,
    reference_frontier,
    reference_median,
    save_reference,
)


def _tasks(n=20, fail_every=4):
    return [{"task_id": f"t{i}", "task_type": "qa",
             "completion_score": 0.2 if i % fail_every == 0 else 1.0,
             "accuracy_score": 0.8, "success": i % fail_every != 0,
             "question": "q", "response": "r"} for i in range(n)]


def _hg(a=0.72, e=0.9):
    return {"A": {"score": a, "status": "warn", "gate": "warn", "details": {}},
            "E": {"score": e, "status": "pass", "gate": "pass", "details": {}}}


# ---- utils/reference ----------------------------------------------------------

def test_percentiles_from_values():
    p = percentiles_from_values([0.6, 0.7, 0.75, 0.8, 0.85, 0.9])
    assert p["p10"] < p["p50"] < p["p90"]
    assert set(p) == {"p10", "p25", "p50", "p75", "p90"}


def test_percentile_of_list_and_dict():
    lst = [0.6, 0.7, 0.75, 0.8, 0.85, 0.9]
    assert percentile_of(0.6, lst) == 8      # below all -> low
    assert percentile_of(0.95, lst) == 100
    d = {"p10": 62, "p25": 70, "p50": 78, "p75": 85, "p90": 91}
    assert percentile_of(78, d) == 50
    assert percentile_of(50, d) == 10        # clamped to p10
    assert percentile_of(200, d) == 90       # clamped to p90


def test_percentile_of_bare_number_is_none():
    assert percentile_of(0.8, 0.75) is None


def test_median_and_frontier():
    assert reference_median(0.75) == 0.75
    assert reference_median({"p50": 0.8, "p90": 0.9}) == 0.8
    assert reference_median([0.7, 0.8, 0.9]) == 0.8
    assert reference_frontier({"p50": 0.8, "p90": 0.92}) == 0.92
    assert reference_frontier(0.75) == 0.75


def test_save_load_roundtrip_and_coercion(tmp_path):
    path = tmp_path / "reference.json"
    save_reference({"label": "x", "tcr_pct": 78,
                    "gate_scores": {"A": [0.7, 0.8], "z": 5}}, path)
    ref = load_reference(path)
    assert ref["label"] == "x" and ref["tcr_pct"] == 78.0
    assert "A" in ref["gate_scores"] and "Z" not in ref["gate_scores"]
    # deep-merge on gate_scores
    save_reference({"gate_scores": {"E": 0.95}}, path)
    ref2 = load_reference(path)
    assert set(ref2["gate_scores"]) == {"A", "E"}


def test_load_missing_or_empty(tmp_path):
    assert load_reference(tmp_path / "nope.json") is None
    (tmp_path / "empty.json").write_text("{}")
    assert load_reference(tmp_path / "empty.json") is None


# ---- _reference_frame_section ----------------------------------------------

def test_none_without_reference():
    assert _reference_frame_section({}, {}, _tasks(), None) is None
    assert _reference_frame_section({}, {}, _tasks(), {"label": "x"}) is None


def test_section_shape_and_weakest():
    ref = {"label": "support-rag",
           "tcr_pct": {"p10": 62, "p25": 70, "p50": 78, "p75": 85, "p90": 91},
           "gate_scores": {"A": [0.71, 0.74, 0.77, 0.80, 0.83], "E": 0.95}}
    rf = _reference_frame_section({}, _hg(0.72, 0.9), _tasks(), ref)
    assert rf["label"] == "support-rag"
    tcr = next(m for m in rf["metrics"] if m["metric"] == "tcr")
    assert isinstance(tcr["percentile"], int)
    ga = next(m for m in rf["metrics"] if m["metric"] == "gate_a")
    assert ga["verdict"] == "below reference" and ga["percentile"] < 50
    # E is a bare point ref -> no percentile
    ge = next(m for m in rf["metrics"] if m["metric"] == "gate_e")
    assert ge["percentile"] is None
    # weakest = lowest percentile among those that have one -> gate_a
    assert rf["furthest_from_frontier"]["metric"] == "gate_a"
    assert "Gate A is the weakest at p" in rf["summary"]


def test_above_reference_summary():
    ref = {"label": "r", "tcr_pct": [30, 35, 40, 45, 50]}   # low bar
    rf = _reference_frame_section({}, {}, _tasks(), ref)
    tcr = rf["metrics"][0]
    assert tcr["verdict"] == "above reference" and tcr["percentile"] == 100


# ---- end to end -----------------------------------------------------------

def test_build_insights_wires_and_narrates():
    ref = {"label": "support-rag",
           "tcr_pct": {"p10": 62, "p25": 70, "p50": 78, "p75": 85, "p90": 91},
           "gate_scores": {"A": [0.71, 0.74, 0.77, 0.80, 0.83]}}
    cur = {"extra_metrics": {"harness_groups": _hg(0.72)}, "tasks": _tasks()}
    ins = build_insights(cur, reference=ref)
    assert ins["reference_frame"] is not None
    assert "reference" in ins["narrative"].lower()
    assert build_insights(cur)["reference_frame"] is None


def test_report_render():
    from agent_evaluator.reporting.comprehensive_report import _build_reference_frame

    ref = {"label": "support-rag", "tcr_pct": {"p10": 62, "p50": 78, "p90": 91},
           "gate_scores": {"A": [0.71, 0.77, 0.83]}}
    rf = _reference_frame_section({}, _hg(0.72), _tasks(), ref)
    html = _build_reference_frame(rf)
    assert 'id="reference-frame"' in html and "Percentile" in html
    assert "support-rag" in html
    assert _build_reference_frame(None) == ""


def test_cli_benchmark_from_results(tmp_path, capsys):
    import argparse

    from agent_evaluator.cli.benchmark import cmd_benchmark

    # two fake result JSONs with harness_groups
    for i, tcr in enumerate([0.7, 0.8]):
        (tmp_path / f"r{i}.json").write_text(json.dumps({
            "timestamp": f"2026-01-0{i + 1}T00:00:00",
            "accuracy_metrics": {"tcr": {"tcr": tcr * 100}},
            "extra_metrics": {"harness_groups": {
                "A": {"score": 0.7 + i * 0.1}, "overall": {"score": 0.75}}},
            "tasks": [{"task_id": "t", "completion_score": tcr}],
        }))
    ref_path = tmp_path / "reference.json"
    ns = argparse.Namespace(
        benchmark_command="set", path=str(ref_path), from_results=str(tmp_path),
        gate=[], tcr=None, accuracy=None, label=None, source=None, note=None,
    )
    assert cmd_benchmark(ns) == 0
    ref = load_reference(ref_path)
    assert "tcr_pct" in ref and isinstance(ref["tcr_pct"], dict)
    assert "A" in ref.get("gate_scores", {})
