"""Tests for AlertEngine, AlertRule, AlertHistory, and AlertEvent.

Covers rule management, cooldown logic, evaluate() triggering,
AlertHistory file I/O (via temp directories), and severity levels.
All file I/O is directed to temporary directories.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_evaluator.alerts.engine import AlertEngine, AlertEvent, AlertHistory, AlertRule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(tmp_path: str | None = None) -> AlertEngine:
    return AlertEngine(history_dir=tmp_path)


def _always_true(_ev: Any) -> bool:
    return True


def _always_false(_ev: Any) -> bool:
    return False


def _mock_evaluator(tcr: float = 95.0) -> MagicMock:
    """Build a minimal mock StreamingEvaluator."""
    ev = MagicMock()
    ev.get_stats.return_value = {
        "count": 10,
        "tcr": tcr,
        "avg_latency": 1.0,
        "p95_latency": 2.0,
        "error_rate": 5.0,
        "avg_tokens": 100.0,
        "window_seconds": 300,
    }
    return ev


def _noop_handler() -> MagicMock:
    handler = MagicMock()
    handler.send = MagicMock()
    return handler


# ---------------------------------------------------------------------------
# AlertEvent
# ---------------------------------------------------------------------------

def test_alert_event_to_dict_has_required_keys():
    event = AlertEvent(rule_name="test_rule", severity="warning", message="msg", value={"tcr": 90})
    d = event.to_dict()
    for key in ("rule_name", "severity", "message", "value", "triggered_at"):
        assert key in d


def test_alert_event_to_dict_values_match():
    event = AlertEvent(rule_name="rule_x", severity="critical", message="hello", value=42)
    d = event.to_dict()
    assert d["rule_name"] == "rule_x"
    assert d["severity"] == "critical"
    assert d["message"] == "hello"
    assert d["value"] == 42


# ---------------------------------------------------------------------------
# AlertEngine.__init__()
# ---------------------------------------------------------------------------

def test_alert_engine_init_has_empty_rules(tmp_path):
    engine = _make_engine(str(tmp_path))
    assert engine.get_rules() == []


# ---------------------------------------------------------------------------
# add_rule() / remove_rule() / get_rules()
# ---------------------------------------------------------------------------

def test_add_rule_appends_to_engine(tmp_path):
    engine = _make_engine(str(tmp_path))
    rule = AlertRule(name="r1", condition=_always_true, handler=_noop_handler())
    engine.add_rule(rule)
    assert len(engine.get_rules()) == 1
    assert engine.get_rules()[0]["name"] == "r1"


def test_add_rule_returns_engine_for_chaining(tmp_path):
    engine = _make_engine(str(tmp_path))
    rule = AlertRule(name="r1", condition=_always_true, handler=_noop_handler())
    result = engine.add_rule(rule)
    assert result is engine


def test_remove_rule_by_name(tmp_path):
    engine = _make_engine(str(tmp_path))
    engine.add_rule(AlertRule(name="r1", condition=_always_true, handler=_noop_handler()))
    engine.add_rule(AlertRule(name="r2", condition=_always_false, handler=_noop_handler()))
    engine.remove_rule("r1")
    rules = engine.get_rules()
    assert len(rules) == 1
    assert rules[0]["name"] == "r2"


def test_remove_nonexistent_rule_does_not_raise(tmp_path):
    engine = _make_engine(str(tmp_path))
    engine.remove_rule("ghost")  # must not raise


def test_get_rules_returns_list_of_dicts(tmp_path):
    engine = _make_engine(str(tmp_path))
    engine.add_rule(AlertRule(name="r1", condition=_always_true, handler=_noop_handler(), severity="critical"))
    rules = engine.get_rules()
    assert isinstance(rules, list)
    assert isinstance(rules[0], dict)
    assert rules[0]["severity"] == "critical"


# ---------------------------------------------------------------------------
# evaluate()
# ---------------------------------------------------------------------------

def test_evaluate_returns_fired_events_when_condition_true(tmp_path):
    engine = _make_engine(str(tmp_path))
    engine.add_rule(AlertRule(
        name="always_fire",
        condition=_always_true,
        handler=_noop_handler(),
        cooldown=0,
    ))
    ev = _mock_evaluator()
    fired = engine.evaluate(ev)
    assert len(fired) == 1
    assert fired[0].rule_name == "always_fire"


def test_evaluate_returns_empty_when_condition_false(tmp_path):
    engine = _make_engine(str(tmp_path))
    engine.add_rule(AlertRule(
        name="never_fire",
        condition=_always_false,
        handler=_noop_handler(),
    ))
    ev = _mock_evaluator()
    fired = engine.evaluate(ev)
    assert fired == []


def test_evaluate_calls_handler_send(tmp_path):
    handler = _noop_handler()
    engine = _make_engine(str(tmp_path))
    engine.add_rule(AlertRule(name="r1", condition=_always_true, handler=handler, cooldown=0))
    engine.evaluate(_mock_evaluator())
    handler.send.assert_called_once()


def test_evaluate_respects_cooldown(tmp_path):
    """Same rule must not fire twice within cooldown period."""
    engine = _make_engine(str(tmp_path))
    engine.add_rule(AlertRule(
        name="slow_rule",
        condition=_always_true,
        handler=_noop_handler(),
        cooldown=3600,  # 1-hour cooldown
    ))
    ev = _mock_evaluator()
    fired1 = engine.evaluate(ev)
    fired2 = engine.evaluate(ev)
    assert len(fired1) == 1
    assert len(fired2) == 0  # blocked by cooldown


def test_evaluate_fires_again_after_cooldown_expires(tmp_path):
    """After cooldown expires the rule must fire again."""
    engine = _make_engine(str(tmp_path))
    rule = AlertRule(
        name="short_cooldown",
        condition=_always_true,
        handler=_noop_handler(),
        cooldown=0,
    )
    engine.add_rule(rule)
    ev = _mock_evaluator()
    fired1 = engine.evaluate(ev)
    fired2 = engine.evaluate(ev)
    assert len(fired1) == 1
    assert len(fired2) == 1  # zero cooldown — fires every time


def test_evaluate_uses_custom_message_fn(tmp_path):
    engine = _make_engine(str(tmp_path))
    rule = AlertRule(
        name="custom_msg",
        condition=_always_true,
        handler=_noop_handler(),
        cooldown=0,
        message_fn=lambda _ev: "custom alert message",
    )
    engine.add_rule(rule)
    fired = engine.evaluate(_mock_evaluator())
    assert fired[0].message == "custom alert message"


def test_evaluate_uses_severity_from_rule(tmp_path):
    engine = _make_engine(str(tmp_path))
    engine.add_rule(AlertRule(
        name="critical_rule",
        condition=_always_true,
        handler=_noop_handler(),
        cooldown=0,
        severity="critical",
    ))
    fired = engine.evaluate(_mock_evaluator())
    assert fired[0].severity == "critical"


def test_evaluate_condition_exception_is_swallowed(tmp_path):
    """A rule whose condition raises must not propagate the exception."""
    def bad_condition(_ev: Any) -> bool:
        raise RuntimeError("boom")

    engine = _make_engine(str(tmp_path))
    engine.add_rule(AlertRule(name="bad", condition=bad_condition, handler=_noop_handler()))
    fired = engine.evaluate(_mock_evaluator())
    assert fired == []


# ---------------------------------------------------------------------------
# AlertHistory — file I/O
# ---------------------------------------------------------------------------

def test_alert_history_record_creates_file(tmp_path):
    history = AlertHistory(history_dir=str(tmp_path))
    event = AlertEvent(rule_name="r1", severity="warning", message="test", value={"tcr": 80})
    history.record(event)
    today_file = tmp_path / f"{__import__('datetime').date.today().isoformat()}.jsonl"
    assert today_file.exists()


def test_alert_history_get_today_returns_recorded_event(tmp_path):
    history = AlertHistory(history_dir=str(tmp_path))
    event = AlertEvent(rule_name="r1", severity="critical", message="alert!", value=99)
    history.record(event)
    today = history.get_today()
    assert len(today) == 1
    assert today[0]["rule_name"] == "r1"
    assert today[0]["severity"] == "critical"


def test_alert_history_get_today_empty_when_no_file(tmp_path):
    history = AlertHistory(history_dir=str(tmp_path))
    assert history.get_today() == []


def test_alert_history_record_multiple_events(tmp_path):
    history = AlertHistory(history_dir=str(tmp_path))
    for i in range(3):
        event = AlertEvent(rule_name=f"rule_{i}", severity="warning", message=f"msg {i}", value=i)
        history.record(event)
    today = history.get_today()
    assert len(today) == 3


def test_alert_history_jsonl_each_line_valid_json(tmp_path):
    history = AlertHistory(history_dir=str(tmp_path))
    event = AlertEvent(rule_name="r1", severity="warning", message="hi", value=1)
    history.record(event)
    import datetime
    today_file = tmp_path / f"{datetime.date.today().isoformat()}.jsonl"
    lines = today_file.read_text(encoding="utf-8").strip().splitlines()
    for line in lines:
        parsed = json.loads(line)
        assert "rule_name" in parsed
