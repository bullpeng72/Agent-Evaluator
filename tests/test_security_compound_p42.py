"""
tests/test_security_compound_p42.py
===================================
SPEC-041 P42 — security findings gain `succeeded`, compound (multi-tracker)
findings escalate severity, and `security_posture` summarises the attack surface.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _attack_succeeded,
    _bump_severity,
    _security_findings_section,
    _security_posture_section,
    build_insights,
)


def _sec_current(*, priv=False, dparams=False, inj=False, blocked=None):
    sec: dict = {}
    if inj:
        sec["input_sanitizer"] = {"evaluations": [
            {"task_id": "t1", "threat_count": 1, "has_prompt_injection": True,
             "risk_level": "medium",
             **({"blocked": blocked} if blocked is not None else {})},
        ]}
    if priv:
        sec["privilege_escalation_detector"] = {"detections": [
            {"task_id": "t1", "escalation_detected": True, "risk_score": 6,
             "initial_privilege": "read", "max_privilege": "execute"},
        ]}
    if dparams:
        sec["tool_authorizer"] = {"evaluations": [
            {"task_id": "t1", "has_dangerous_params": True, "is_authorized": True,
             "tool_name": "shell"},
        ]}
    return {"evaluators": {"security": sec}}


def _tasks(tool_ok=True):
    return [{"task_id": "t1", "task_type": "qa", "question": "q",
             "tool_calls": [{"tool_name": "shell", "success": tool_ok}]}]


def test_bump_severity():
    assert _bump_severity("medium") == "high"
    assert _bump_severity("high") == "critical"
    assert _bump_severity("critical") == "critical"
    assert _bump_severity("nonsense") == "high"


def test_attack_succeeded_prefers_explicit_field():
    assert _attack_succeeded({"blocked": True}, None) == "no"
    assert _attack_succeeded({"blocked": False}, None) == "yes"
    assert _attack_succeeded({"executed": True}, None) == "yes"
    assert _attack_succeeded({}, {"tool_calls": [{"success": True}]}) == "likely"
    assert _attack_succeeded({}, {"tool_calls": [{"success": False}]}) == "unknown"
    assert _attack_succeeded({}, None) == "unknown"


def test_single_finding_carries_succeeded():
    sf = _security_findings_section(_sec_current(inj=True, blocked=True), _tasks())
    assert sf and sf[0]["succeeded"] == "no"           # explicitly blocked


def test_compound_finding_escalates():
    sf = _security_findings_section(
        _sec_current(priv=True, dparams=True), _tasks(tool_ok=True),
    )
    comp = [f for f in sf if f.get("kind") == "compound"]
    assert len(comp) == 1
    c = comp[0]
    assert c["severity"] == "critical"                 # high (priv) bumped up
    assert set(c["components"]) == {"privilege_escalation", "dangerous_params"}
    assert isinstance(c["cwe"], list) and len(c["cwe"]) == 2
    assert c["succeeded"] == "likely"
    # compound sorts first
    assert sf[0]["kind"] == "compound"


def test_no_compound_for_single_tracker():
    sf = _security_findings_section(_sec_current(priv=True), _tasks())
    assert not any(f.get("kind") == "compound" for f in sf)


def test_security_posture_summary():
    sf = _security_findings_section(
        _sec_current(priv=True, dparams=True), _tasks(tool_ok=True),
    )
    p = _security_posture_section(
        _sec_current(priv=True, dparams=True), _tasks(tool_ok=True), sf,
    )
    assert p["n_findings"] == 2
    assert p["n_tasks_affected"] == 1
    assert p["n_compound"] == 1
    assert any(t["tool"] == "shell" for t in p["tools_implicated"])
    assert p["landed_or_likely"]              # priv-esc / dparams "likely" landed


def test_end_to_end_and_report():
    from agent_evaluator.reporting.comprehensive_report import _build_security_findings

    cur = {**_sec_current(priv=True, dparams=True), "tasks": _tasks(tool_ok=True)}
    ins = build_insights(cur)
    assert ins["security_posture"]["n_compound"] == 1
    assert any(f.get("kind") == "compound" for f in ins["security_findings"])
    html = _build_security_findings(cur)
    assert "COMPOUND" in html and "Attack surface" in html and "Outcome" in html
