"""
tests/test_conversation_insights.py
=======================================
SPEC-041 P24 — multi-turn conversation insights (`insights.conversation`).
`insights` had zero coverage for a whole product category; this adds the
per-turn quality trajectory, the turn the agent starts to degrade, and
per-session goal drift.
"""
from __future__ import annotations

import json

import jsonschema

from agent_evaluator.reporting.insights import _conversation_section, build_insights


def _session(sid, turns, *, overall=0.7, ctx=0.7, topic=0.8):
    return {
        "session_id": sid, "turn_count": len(turns),
        "turns": [
            {"turn_index": i, "user": u, "agent": a, "timestamp": "2026", "metadata": {}}
            for i, (u, a) in enumerate(turns)
        ],
        "metrics": {
            "overall_score": overall, "context_retention": ctx,
            "topic_coherence": topic, "progressive_depth": 0.7,
            "session_completion": 0.8,
        },
    }


_GOOD = [
    ("How do I return an item?", "Unopened items within 14 days get a full refund."),
    ("What about opened items?", "Opened items within 14 days get store credit only."),
    ("Do I pay the return shipping?", "No — we email you a prepaid return label."),
    ("How long until I see the money?", "Refunds post within 3 business days of receipt."),
]
_DEGRADING = [
    ("How do I return an item?", "Unopened items within 14 days get a full refund."),
    ("What about opened items?", "Opened items within 14 days get store credit only."),
    ("Do I pay shipping?", "Sorry, could you clarify what you mean?"),
    ("The return shipping cost", "I am not able to help with that right now."),
    ("Hello?", "Hi."),
    ("Are you there", "Yes."),
]


class TestConversationSection:
    def test_none_without_sessions(self):
        assert _conversation_section({}) is None
        assert _conversation_section({"conversation_sessions": []}) is None

    def test_turn_trajectory_and_context_ref_decline(self):
        cv = _conversation_section({"conversation_sessions": [_session("s1", _DEGRADING)]})
        traj = cv["turn_quality_trajectory"]
        assert [x["turn"] for x in traj] == [1, 2, 3, 4, 5, 6]
        # context reference is high early, low late
        assert traj[0]["context_ref"] > traj[-1]["context_ref"]

    def test_degradation_after_turn_detected(self):
        cv = _conversation_section({"conversation_sessions": [_session("s1", _DEGRADING)]})
        assert isinstance(cv["degradation_after_turn"], int)
        assert 1 <= cv["degradation_after_turn"] <= 4

    def test_no_degradation_for_a_healthy_session(self):
        cv = _conversation_section({"conversation_sessions": [_session("ok", _GOOD)]})
        assert cv["degradation_after_turn"] is None

    def test_goal_drift_flagged_on_off_topic_last_turn(self):
        drift_sess = _session("d1", [
            ("What is your refund policy?", "Unopened, 14 days, full refund."),
            ("thanks", "welcome"),
            ("What will the weather in Tokyo be next Tuesday afternoon?",
             "I cannot check live weather."),
        ], topic=0.2)
        cv = _conversation_section({"conversation_sessions": [drift_sess]})
        assert any(d["session_id"] == "d1" for d in cv["goal_drift_sessions"])

    def test_trailing_filler_turn_is_not_drift(self):
        # a substantive conversation that ends with "ok bye" must NOT be flagged
        s = _session("s", _GOOD + [("ok bye", "Goodbye!")], topic=0.85)
        cv = _conversation_section({"conversation_sessions": [s]})
        assert cv["goal_drift_sessions"] == []

    def test_worst_session_is_lowest_overall(self):
        cv = _conversation_section({"conversation_sessions": [
            _session("hi", _GOOD, overall=0.9),
            _session("lo", _GOOD, overall=0.3),
        ]})
        assert cv["worst_session"]["session_id"] == "lo"


class TestBuildInsightsWiring:
    def test_key_present_and_schema_valid(self):
        rpt = {
            "extra_metrics": {"harness_groups": {
                "A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}},
            }},
            "tasks": [],
            "conversation_sessions": [_session("s1", _DEGRADING), _session("s2", _GOOD)],
        }
        ins = build_insights(rpt)
        assert ins["conversation"] is not None
        assert ins["conversation"]["n_sessions"] == 2
        json.dumps(ins)
        from pathlib import Path
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
             / "insights.schema.json").read_text()
        )
        jsonschema.validate(ins, schema)

    def test_null_without_conversation_data(self):
        assert build_insights({"tasks": [], "extra_metrics": {"harness_groups": {}}})[
            "conversation"
        ] is None

    def test_report_renders_section(self):
        from agent_evaluator import PerformanceMonitor, create_taskresult
        from agent_evaluator.core.trackers.conversation import ConversationSession
        from agent_evaluator.reporting.comprehensive_report import (
            generate_comprehensive_html_report,
        )

        m = PerformanceMonitor(output_dir="/tmp")
        for i in range(5):
            m.record_task(create_taskresult(
                task_id=f"t{i}", question="q", response="a", ground_truth="a",
                execution_time=1.0, task_type="qa",
            ))
        cs = ConversationSession(session_id="c1")
        for u, a in _DEGRADING:
            cs.add_turn(u, a)
        cs.compute_metrics()
        m.conversation_sessions.append(cs)
        html = generate_comprehensive_html_report(m)
        assert 'id="conversation"' in html
        assert "Per-turn context reference" in html
