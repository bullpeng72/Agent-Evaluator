"""
tests/test_report_gen_malformed_input.py
============================================
Report-generation robustness — a hand-written / older-SDK / partially-written
result JSON that carries an explicit ``null`` (or a non-dict) where the code
expects a nested object must NOT crash report generation with an
``AttributeError`` / ``TypeError``. It should degrade to a clean report.

``dict.get(k, {})`` returns the stored ``None`` — not the default — when the key
is present with a null value, which is the recurring root cause here.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from agent_evaluator.reporting.comprehensive_report import (
    _build_gate_a,
    _build_gate_b,
    _build_gate_c,
    _build_gate_d,
    _build_gate_e_from_rf,
    _build_gate_f,
    _build_gate_g,
    _build_header,
    generate_html_from_result_file,
)
from agent_evaluator.serve.loader import parse_file


def _parse(raw: dict):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(raw, f)
        p = f.name
    try:
        return parse_file(Path(p))
    finally:
        os.unlink(p)


class TestGateBuildersTolerateNullGateData:
    """``harness_groups.get("A", {})`` returns ``None`` when the JSON has
    ``harness_groups: {"A": null}`` — every _build_gate_* helper must cope."""

    def test_each_gate_builder_accepts_none(self):
        assert isinstance(_build_gate_a(80.0, 0.8, 0.75, {}, None, {}), str)
        assert isinstance(_build_gate_b({}, False, None), str)
        assert isinstance(_build_gate_c({}, None, {}, None), str)
        assert isinstance(_build_gate_d({}, {}, None, [], {}), str)
        assert isinstance(_build_gate_e_from_rf(object(), None), str)
        assert isinstance(_build_gate_f({}, {}, False, None), str)
        assert isinstance(_build_gate_g({}, None, None), str)

    def test_header_accepts_null_gate_values(self):
        html = _build_header(10, 60.0, 0.5, 1.0, {"A": None, "B": {"status": "pass"}}, {})
        assert "Gate B" in html  # the one valid gate still renders a badge


class TestGenerateHtmlFromMalformedResultFile:
    @pytest.mark.parametrize("raw", [
        # per-gate null inside harness_groups
        {"accuracy_metrics": {"tcr": {"tcr": 60}},
         "extra_metrics": {"harness_groups": {"A": None, "B": {"score": 0.8, "status": "pass"}}},
         "tasks": [{"task_id": "t1", "success": False,
                    "completion_score": 0.3, "accuracy_score": 0.2}]},
        # every gate null
        {"extra_metrics": {"harness_groups": {g: None for g in "ABCDEFG"}}, "tasks": []},
        # "report" wrapper is null / non-dict
        {"report": None, "accuracy_metrics": {"tcr": {"tcr": 77}}, "tasks": []},
        {"report": [], "extra_metrics": {"harness_groups": {"A": None}}, "tasks": None},
        # "tasks" explicit null
        {"accuracy_metrics": {"tcr": {"tcr": 50}}, "tasks": None},
        # everything null
        {"report": None, "extra_metrics": None, "accuracy_metrics": None,
         "efficiency_metrics": None, "tasks": None},
    ])
    def test_report_generation_never_crashes(self, raw):
        rf = _parse(raw)
        html = generate_html_from_result_file(rf)
        assert html.lstrip().startswith("<")
        assert "</html>" in html

    def test_flat_metrics_win_when_report_wrapper_is_null(self):
        rf = _parse({"report": None, "accuracy_metrics": {"tcr": {"tcr": 77}}, "tasks": []})
        assert round(rf.tcr, 1) == 77.0
        assert "77" in generate_html_from_result_file(rf)


class TestNonFiniteNumbersAreScrubbed:
    """``json.loads`` accepts the non-standard ``NaN`` / ``Infinity`` tokens. They
    must not ride a metric into ``round()`` / an f-string / the rendered page, nor
    into a re-serialised insight object (``JSON.parse`` / strict parsers reject
    ``NaN``). Scrubbed to ``null`` at ingest + on write."""

    _NAN_JSON = (
        '{"accuracy_metrics": {"tcr": {"tcr": NaN}, '
        '"accuracy_scores": {"overall_accuracy": Infinity}}, '
        '"efficiency_metrics": {"latency": {"mean": NaN, "p95": Infinity}}, '
        '"extra_metrics": {"harness_groups": {"A": {"score": NaN, "status": "fail", '
        '"details": {"tcr_pct": NaN}}}}, '
        '"tasks": [{"task_id": "t0", "success": true, "completion_score": NaN, '
        '"accuracy_score": Infinity, "execution_time": NaN}]}'
    )

    def test_parse_file_scrubs_nan_tokens(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(self._NAN_JSON)
            p = f.name
        try:
            rf = parse_file(Path(p))
        finally:
            os.unlink(p)
        import math
        for v in (rf.tcr, rf.accuracy, rf.avg_latency, rf.p95_latency):
            assert math.isfinite(v)
        assert math.isfinite(rf.tasks[0].completion_score)
        assert math.isfinite(rf.tasks[0].accuracy_score)
        # the rendered page must not carry a literal "nan%" / "infs"
        html = generate_html_from_result_file(rf)
        assert "nan%" not in html.lower()
        assert "infs" not in html.lower() and "inf%" not in html.lower()

    def test_build_insights_output_is_strict_json(self):
        from agent_evaluator.reporting.insights import build_insights

        raw = json.loads(self._NAN_JSON)  # dict now holds real float nan / inf
        ins = build_insights(raw)
        dumped = json.dumps(ins)  # default allow_nan=True would emit NaN tokens
        assert "NaN" not in dumped and "Infinity" not in dumped

    def test_save_to_file_writes_strict_json_with_nan_in_extra(self):
        from agent_evaluator import PerformanceMonitor, create_taskresult

        d = tempfile.mkdtemp()
        m = PerformanceMonitor(output_dir=d)
        for i in range(3):
            m.record_task(create_taskresult(
                task_id=f"t{i}", question="q", response="r", ground_truth="r",
                execution_time=1.0, task_type="qa",
            ))
        # NaN in a free-form place TaskResult validation does not reach
        m.record_task(create_taskresult(
            task_id="x", question="q", response="r", ground_truth="r",
            execution_time=1.0, task_type="qa",
            extra={"custom_metric": float("nan"), "ratio": float("inf")},
        ))
        m.save_to_file("eval")
        txt = Path(d, "eval.json").read_text()
        assert "NaN" not in txt and "Infinity" not in txt
        # strict parse (reject NaN/Infinity like JSON.parse does)
        json.loads(
            txt,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"strict reject: {x}")),
        )

    def test_save_to_file_streaming_path_also_strict(self):
        import agent_evaluator.core.trackers.monitor as _mon
        from agent_evaluator import PerformanceMonitor, create_taskresult

        d = tempfile.mkdtemp()
        _orig = _mon._STREAMING_THRESHOLD
        _mon._STREAMING_THRESHOLD = 2
        try:
            m = PerformanceMonitor(output_dir=d)
            for i in range(5):
                m.record_task(create_taskresult(
                    task_id=f"s{i}", question="q", response="r", ground_truth="r",
                    execution_time=1.0, task_type="qa",
                    extra=({"m": float("nan")} if i == 1 else None),
                ))
            m.save_to_file("ev2")
        finally:
            _mon._STREAMING_THRESHOLD = _orig
        txt = Path(d, "ev2.json").read_text()
        assert "NaN" not in txt
        json.loads(
            txt,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError("strict reject")),
        )
