"""
tests/test_multiagent_insight_p41.py
====================================
SPEC-041 P41 — insights.multiagent: per-agent contribution, hand-off retention,
bottleneck agent, communication graph, MAST candidates.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import _multiagent_section, build_insights


def _t(tid, ai, ok=True):
    return {"task_id": tid, "task_type": "qa", "accuracy_score": 0.9 if ok else 0.2,
            "completion_score": 1.0 if ok else 0.2, "success": ok,
            "question": f"q {tid}", "agent_interactions": ai}


def _crew(ok=True):
    return [
        {"from": "supervisor", "to": "researcher", "success": True,
         "message": "research the quarterly refund policy for bulk orders"},
        {"from": "researcher", "to": "writer", "success": ok,
         "message": "found: refunds within 14 days"},
        {"from": "writer", "to": "supervisor", "success": ok,
         "message": "Refunds are available within fourteen days of purchase."},
    ]


def test_none_without_agent_data():
    assert _multiagent_section([{"task_id": "a", "question": "q"}]) is None


def test_per_agent_and_bottleneck():
    tasks = [_t(f"ok{i}", _crew(True)) for i in range(3)]
    tasks += [_t(f"bad{i}", _crew(False)) for i in range(3)]
    ma = _multiagent_section(tasks)
    assert ma["n_agents"] == 3
    ids = {pa["agent_id"] for pa in ma["per_agent"]}
    assert ids == {"supervisor", "researcher", "writer"}
    sup = next(pa for pa in ma["per_agent"] if pa["agent_id"] == "supervisor")
    assert sup["contribution_score"] > 0
    # writer + researcher error out on the "bad" tasks -> one of them is the bottleneck
    assert ma["bottleneck_agent"] in ("writer", "researcher")


def test_handoffs_and_communication_graph():
    ma = _multiagent_section([_t(f"t{i}", _crew(True)) for i in range(4)])
    pairs = {(h["from"], h["to"]) for h in ma["handoffs"]}
    assert ("supervisor", "researcher") in pairs
    assert ("researcher", "writer") in pairs
    assert ma["communication_graph"]
    for h in ma["handoffs"]:
        assert h["context_retention_at_handoff"] is None or \
            0.0 <= h["context_retention_at_handoff"] <= 1.0


def test_low_retention_yields_mast_1_4():
    # sender messages share nothing with the receiver's follow-up
    ai = [
        {"from": "a", "to": "b", "success": True, "message": "alpha bravo charlie delta"},
        {"from": "b", "to": "c", "success": True, "message": "zulu yankee xray whiskey"},
        {"from": "c", "to": "a", "success": True, "message": "one two three four five"},
    ]
    ma = _multiagent_section([_t(f"t{i}", ai) for i in range(4)])
    codes = {m["code"] for m in ma["mast_candidates"]}
    assert "1.4" in codes


def test_ping_pong_cycle_yields_mast_1_5():
    ai = [
        {"from": "a", "to": "b", "success": True, "message": "do x"},
        {"from": "b", "to": "a", "success": True, "message": "need more info"},
        {"from": "a", "to": "b", "success": True, "message": "do x"},
        {"from": "b", "to": "a", "success": True, "message": "need more info"},
    ]
    ma = _multiagent_section([_t(f"t{i}", ai) for i in range(4)])
    codes = {m["code"] for m in ma["mast_candidates"]}
    assert "1.5" in codes


def test_end_to_end_and_report():
    from agent_evaluator.reporting.comprehensive_report import _build_multiagent

    tasks = [_t(f"ok{i}", _crew(True)) for i in range(3)]
    tasks += [_t(f"bad{i}", _crew(False)) for i in range(2)]
    cur = {"extra_metrics": {"harness_groups": {}}, "tasks": tasks}
    ma = build_insights(cur)["multiagent"]
    assert ma and ma["n_agents"] == 3
    html = _build_multiagent(ma)
    assert "Multi-Agent Coordination" in html
    assert "Hand-offs" in html
    assert _build_multiagent(None) == ""
