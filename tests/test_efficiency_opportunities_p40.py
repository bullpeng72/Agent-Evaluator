"""
tests/test_efficiency_opportunities_p40.py
==========================================
SPEC-041 P40 — insights.efficiency_opportunities: cost/latency reporting turned
into concrete moves (model routing / step gating / retry reduction).
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _efficiency_opportunities_section,
    build_insights,
)


def _t(tid, acc, ok, *, extra=None, tokens=None, tool_calls=None, attempts=1):
    d = {"task_id": tid, "task_type": "qa", "accuracy_score": acc,
         "completion_score": 1.0 if ok else 0.2, "success": ok,
         "question": f"q {tid}", "attempts": attempts,
         "extra": extra or {}, "tokens_used": tokens or {"input": 500, "output": 300}}
    if tool_calls is not None:
        d["tool_calls"] = tool_calls
    return d


def test_none_when_no_signal():
    tasks = [_t(f"t{i}", 0.9, True) for i in range(6)]
    assert _efficiency_opportunities_section(tasks, {}, None, None, None) is None


def test_model_routing_when_cheap_variant_is_close():
    cur = {"pricing": {"input": 0.001, "output": 0.002}}
    tasks = []
    for i in range(8):
        tasks.append(_t(f"big{i}", 0.9, True, extra={"model_variant": "big"},
                        tokens={"input": 4000, "output": 2000}))
    for i in range(8):
        tasks.append(_t(f"sm{i}", 0.87, i < 7, extra={"model_variant": "small"},
                        tokens={"input": 400, "output": 200}))
    ms = [{"dimension": "extra.model_variant", "slices": [
        {"value": "big", "n": 8, "tcr_pct": 100.0},
        {"value": "small", "n": 8, "tcr_pct": 96.0},
    ]}]
    ce = build_insights({**cur, "tasks": tasks})["cost_economics"]
    eo = _efficiency_opportunities_section(tasks, cur, ce, ms, None)
    assert eo is not None
    kinds = {o["kind"] for o in eo}
    assert "model_routing" in kinds
    r = next(o for o in eo if o["kind"] == "model_routing")
    assert r["projected_saving_pct"] > 0
    assert "small" in r["title"]


def test_model_routing_suppressed_when_tcr_loss_too_big():
    cur = {"pricing": {"input": 0.001, "output": 0.002}}
    tasks = [_t(f"b{i}", 0.9, True, extra={"model_variant": "big"},
                tokens={"input": 4000, "output": 2000}) for i in range(8)]
    tasks += [_t(f"s{i}", 0.5, i < 4, extra={"model_variant": "small"},
                 tokens={"input": 400, "output": 200}) for i in range(8)]
    ms = [{"dimension": "extra.model_variant", "slices": [
        {"value": "big", "n": 8, "tcr_pct": 100.0},
        {"value": "small", "n": 8, "tcr_pct": 50.0},          # -50pp: not worth it
    ]}]
    ce = build_insights({**cur, "tasks": tasks})["cost_economics"]
    eo = _efficiency_opportunities_section(tasks, cur, ce, ms, None) or []
    assert not any(o["kind"] == "model_routing" for o in eo)


def test_step_gating_flags_ubiquitous_non_core_step():
    tc = [
        {"tool_name": "retrieve", "start_ms": 0.0, "end_ms": 300.0, "success": True},
        {"tool_name": "generate", "start_ms": 300.0, "end_ms": 2300.0, "success": True},
    ]
    tasks = [_t(f"t{i}", 0.9, True, tool_calls=tc) for i in range(6)]
    eo = _efficiency_opportunities_section(tasks, {}, {}, None, None) or []
    sg = [o for o in eo if o["kind"] == "step_gating"]
    assert sg and "retrieve" in sg[0]["title"]        # not "generate" (the core step)


def test_retry_reduction_uses_cost_economics():
    ce = {"retry_cost_pct": 18.0, "retry_cost_usd": 0.9, "cost_per_task_usd": 0.01}
    fc = [{"signature": "error: TimeoutError", "count": 4},
          {"signature": "low accuracy", "count": 2}]
    tasks = [_t(f"t{i}", 0.9, True) for i in range(10)]
    eo = _efficiency_opportunities_section(tasks, {}, ce, None, fc)
    assert eo is not None
    r = next(o for o in eo if o["kind"] == "retry_reduction")
    assert "18%" in r["title"]
    assert "error: TimeoutError" in r["detail"]
    assert r["evidence"]["clusters"] == ["error: TimeoutError"]


def test_report_section_renders():
    from agent_evaluator.reporting.comprehensive_report import (
        _build_efficiency_opportunities,
    )

    html = _build_efficiency_opportunities([
        {"kind": "retry_reduction", "title": "20% of spend is retries",
         "detail": "d", "projected_saving_pct": 20.0,
         "projected_saving_per_100k_usd": 500.0, "risk": "r"},
    ])
    assert "Efficiency Opportunities" in html and "Retry reduction" in html
    assert "~20% cost" in html
    assert _build_efficiency_opportunities(None) == ""
