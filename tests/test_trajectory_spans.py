"""
tests/test_trajectory_spans.py
==================================
SPEC-041 P25 — span timeline / waterfall trace.

`parse_span_timeline()` turns a flat step list into a nested timeline with
per-span self-time, the critical path, and the bottleneck; `insights.trajectories`
surfaces it for the worst-N tasks and the HTML report draws an inline-SVG
waterfall above the existing flat step table.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from agent_evaluator.reporting.insights import (
    _trajectories_section,
    build_insights,
    parse_span_timeline,
)

_ABS = [
    {"id": "a", "name": "plan", "start_ms": 0, "end_ms": 1200, "tokens": 300, "cost": 0.002},
    {"id": "b", "parent": "a", "name": "retrieve", "start_ms": 100, "end_ms": 700, "tokens": 120},
    {"id": "c", "parent": "a", "name": "llm.generate", "start_ms": 720, "end_ms": 1180,
     "tokens": 800, "cost": 0.01},
    {"id": "d", "name": "verify", "start_ms": 1200, "end_ms": 1500},
]
_DUR_MS = [
    {"name": "step1", "duration_ms": 400},
    {"name": "step2", "duration_ms": 900},
    {"name": "step3", "duration_ms": 150},
]


class TestParseSpanTimeline:
    def test_none_without_timing(self):
        assert parse_span_timeline([]) is None
        assert parse_span_timeline([{"name": "x"}, {"name": "y"}]) is None

    def test_absolute_timing_total_and_bottleneck(self):
        tl = parse_span_timeline(_ABS)
        assert tl is not None
        assert tl["total_ms"] == 1500.0
        assert tl["n_spans"] == 4
        # retrieve (600ms self) is the single biggest self-time span
        assert tl["bottleneck"]["name"] == "retrieve"
        assert tl["bottleneck"]["self_ms"] == 600.0

    def test_parent_nesting_gives_depth_and_self_time(self):
        tl = parse_span_timeline(_ABS)
        assert tl is not None
        by_name = {s["name"]: s for s in tl["spans"]}
        assert by_name["retrieve"]["depth"] == 1
        assert by_name["verify"]["depth"] == 0
        # plan spans 1200ms but 1060ms is covered by its two children
        assert by_name["plan"]["self_ms"] == 140.0

    def test_critical_path_covers_most_of_the_wall_clock(self):
        tl = parse_span_timeline(_ABS)
        assert tl is not None
        cp = tl["critical_path"]
        assert "retrieve" in cp and "llm.generate" in cp
        assert "plan" not in cp  # 140ms self-time — not a time sink

    def test_relative_duration_layout(self):
        tl = parse_span_timeline(_DUR_MS)
        assert tl is not None
        assert tl["total_ms"] == 1450.0
        assert tl["spans"][1]["start_ms"] == 400.0
        assert tl["spans"][2]["start_ms"] == 1300.0

    def test_bare_duration_seconds_scaled_to_ms(self):
        tl = parse_span_timeline([
            {"name": "s1", "duration": 0.4}, {"name": "s2", "duration": 1.1},
        ])
        assert tl is not None
        assert tl["total_ms"] == 1500.0

    def test_millisecond_keys_are_trusted_as_is(self):
        # a genuine 2ms step must not be inflated to 2000ms
        tl = parse_span_timeline([
            {"name": "fast", "duration_ms": 2}, {"name": "slow", "duration_ms": 40},
        ])
        assert tl is not None
        assert tl["total_ms"] == 42.0

    def test_cost_and_token_totals(self):
        tl = parse_span_timeline(_ABS)
        assert tl is not None
        assert tl["total_tokens"] == 1220
        assert abs(tl["total_cost_usd"] - 0.012) < 1e-9


class TestTrajectoriesSection:
    def test_prefers_failing_tasks(self):
        tasks = [
            {"task_id": "ok", "success": True, "accuracy_score": 0.95, "tool_calls": _DUR_MS},
            {"task_id": "bad", "success": False, "accuracy_score": 0.2, "tool_calls": _ABS},
        ]
        sec = _trajectories_section(tasks)
        assert sec is not None
        assert sec[0]["task_id"] == "bad"
        assert sec[0]["source"] == "tool_calls"

    def test_none_when_no_task_has_timing(self):
        assert _trajectories_section([
            {"task_id": "t", "success": False, "tool_calls": [{"tool_name": "x"}]},
        ]) is None

    def test_falls_back_to_chain_steps(self):
        sec = _trajectories_section([
            {"task_id": "t", "success": False, "chain_steps": _DUR_MS},
        ])
        assert sec is not None
        assert sec[0]["source"] == "chain_steps"


class TestBuildInsightsWiring:
    def test_key_present_and_schema_valid(self):
        rpt = {
            "extra_metrics": {"harness_groups": {
                "A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}},
            }},
            "tasks": [
                {"task_id": "t1", "success": False, "accuracy_score": 0.2, "tool_calls": _ABS},
            ],
        }
        ins = build_insights(rpt)
        assert ins["trajectories"] and ins["trajectories"][0]["task_id"] == "t1"
        json.dumps(ins)
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
             / "insights.schema.json").read_text()
        )
        jsonschema.validate(ins, schema)

    def test_null_without_timing(self):
        ins = build_insights({
            "tasks": [{"task_id": "t", "success": False, "tool_calls": [{"tool_name": "x"}]}],
            "extra_metrics": {"harness_groups": {}},
        })
        assert ins["trajectories"] is None


class TestReportWaterfall:
    def test_waterfall_svg_rendered_when_timing_present(self):
        from agent_evaluator.reporting.comprehensive_report import (
            _build_trajectory,
            _build_waterfall,
        )

        wf = _build_waterfall(_ABS)
        assert "<svg" in wf and "bottleneck" in wf and "retrieve" in wf
        tr = _build_trajectory(
            {"tool_calls": _ABS, "chain_steps": [], "agent_interactions": []}
        )
        assert "<svg" in tr and "Trajectory" in tr

    def test_flat_table_only_without_timing(self):
        from agent_evaluator.reporting.comprehensive_report import _build_trajectory

        tr = _build_trajectory(
            {"tool_calls": [{"tool_name": "search"}], "chain_steps": [],
             "agent_interactions": []}
        )
        assert "Trajectory" in tr and "<svg" not in tr
