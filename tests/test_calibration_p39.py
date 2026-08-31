"""
tests/test_calibration_p39.py
=============================
SPEC-041 P39 — agent confidence calibration + abstention quality.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import _calibration_section, build_insights
from agent_evaluator.utils.confidence import (
    brier_score,
    expected_calibration_error,
    risk_coverage_points,
)

# ---- pure math -----------------------------------------------------------

def test_ece_perfect_calibration_is_zero():
    # confidence == accuracy in every bucket
    pairs = [(0.9, 1.0)] * 9 + [(0.9, 0.0)] * 1 + [(0.2, 0.0)] * 8 + [(0.2, 1.0)] * 2
    ece = expected_calibration_error(pairs)
    assert ece is not None
    assert ece["ece"] < 0.05


def test_ece_overconfident_is_large():
    pairs = [(0.95, 1.0 if i < 6 else 0.0) for i in range(10)]   # 95% stated, 60% real
    ece = expected_calibration_error(pairs)
    assert ece is not None
    assert ece["ece"] > 0.3
    assert ece["mce"] >= ece["ece"]


def test_brier_and_empty():
    assert brier_score([(1.0, 1.0), (1.0, 1.0)]) == 0.0
    assert brier_score([(1.0, 0.0)]) == 1.0
    assert brier_score([]) is None
    assert expected_calibration_error([]) is None
    assert risk_coverage_points([]) is None


def test_risk_coverage_falls_when_confidence_informative():
    # high confidence => right, low => wrong
    pairs = [(0.9, 1.0)] * 10 + [(0.3, 0.0)] * 10
    rc = risk_coverage_points(pairs)
    assert rc is not None
    assert rc[0]["risk"] > rc[-1]["risk"]        # keeping only the confident half -> less risk


# ---- section ------------------------------------------------------------

def _t(tid, acc, conf=None, abstained=False, gt="a real ground truth here"):
    d = {"task_id": tid, "task_type": "qa", "accuracy_score": acc,
         "completion_score": 1.0, "success": acc >= 0.6,
         "question": f"q {tid}", "ground_truth": gt, "extra": {}}
    if conf is not None:
        d["extra"]["confidence"] = conf
    if abstained:
        d["extra"]["abstained"] = True
    return d


def test_none_without_optin_data():
    tasks = [_t(f"t{i}", 0.9) for i in range(10)]
    assert _calibration_section(tasks) is None


def test_overconfident_verdict_and_bins():
    tasks = [_t(f"g{i}", 0.9, conf=0.7) for i in range(5)]          # under-stated, right
    tasks += [_t(f"b{i}", 0.1, conf=0.95) for i in range(6)]        # over-stated, wrong
    cal = _calibration_section(tasks)
    assert cal is not None
    assert cal["verdict"] == "overconfident"
    assert cal["confidence_gap"] > 0.1
    assert cal["n_with_confidence"] == 11
    assert any(b["hi"] == 1.0 and b["accuracy"] < 0.3 for b in cal["reliability_bins"])
    assert cal["confidence_signal"] in ("informative", "flat", "inverted")


def test_abstention_block():
    tasks = [_t(f"a{i}", 0.8, conf=0.8) for i in range(6)]
    tasks += [_t("ab1", 0.0, abstained=True, gt="proper ground truth")]
    tasks += [_t("ab2", 0.0, abstained=True, gt="x")]              # not answerable (short gt)
    cal = _calibration_section(tasks)
    assert cal is not None
    ab = cal["abstention"]
    assert ab["n_abstained"] == 2
    assert ab["abstained_when_answerable"] == 1
    assert ab["answered_accuracy_pct"] == 100.0


def test_end_to_end_and_narrative():
    tasks = [_t(f"g{i}", 0.95, conf=0.6) for i in range(6)]
    tasks += [_t(f"b{i}", 0.05, conf=0.97) for i in range(8)]
    cur = {"extra_metrics": {"harness_groups": {
        "A": {"score": 0.55, "status": "warn", "gate": "warn", "details": {}}}},
        "tasks": tasks}
    ins = build_insights(cur)
    assert ins["calibration"]["verdict"] == "overconfident"
    assert "overconfident" in ins["narrative"]


def test_report_section_renders():
    from agent_evaluator.reporting.comprehensive_report import _build_calibration

    cal = _calibration_section(
        [_t(f"g{i}", 0.9, conf=0.65) for i in range(5)]
        + [_t(f"b{i}", 0.1, conf=0.95) for i in range(6)]
        + [_t("ab1", 0.0, abstained=True, gt="a proper ground truth")]
    )
    html = _build_calibration(cal)
    assert "Confidence Calibration" in html
    assert "Reliability by confidence bucket" in html
    assert "Abstention" in html
