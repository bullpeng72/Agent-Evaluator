"""
tests/test_spec015_alert_retry_backoff.py
=============================================
SPEC-015: 알림 핸들러 재시도/백오프 및 알림 폭풍 방지 검증.

REQ-1: _send_with_retry() — 1s/2s/4s 백오프, 최대 3회.
REQ-2: 재시도 소진 시 warning 로그 + get_failed_send_count() 증가.
REQ-3: async_dispatch — 기본 False(동기, 기존과 100% 동일), True면 백그라운드 스레드.
REQ-4: rule.mark_fired()는 여전히 발송 이전에 호출(변경 없음).
REQ-5: max_alerts_per_window — 전역 알림 폭풍 방지, get_suppressed_count().
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator.alerts.engine import AlertEngine, AlertRule, _send_with_retry


def _mock_evaluator(tcr: float = 10.0) -> MagicMock:
    ev = MagicMock()
    ev.get_stats.return_value = {
        "count": 10, "tcr": tcr, "avg_latency": 1.0,
        "p95_latency": 2.0, "error_rate": 5.0, "avg_tokens": 100.0, "window_seconds": 300,
    }
    return ev


def _always_true(_ev: Any) -> bool:
    return True


def _make_rule(name: str, handler: Any, cooldown: int = 0) -> AlertRule:
    return AlertRule(name=name, condition=_always_true, handler=handler, cooldown=cooldown)


class TestSendWithRetry:
    def test_succeeds_on_first_attempt_no_sleep(self):
        handler = MagicMock()
        event = MagicMock(rule_name="r1")
        with patch("time.sleep") as mock_sleep:
            result = _send_with_retry(handler, event, max_retries=3)
        assert result is True
        handler.send.assert_called_once_with(event)
        mock_sleep.assert_not_called()

    def test_succeeds_after_two_failures_with_backoff(self):
        handler = MagicMock()
        handler.send.side_effect = [ConnectionError("boom"), ConnectionError("boom"), None]
        event = MagicMock(rule_name="r1")
        with patch("time.sleep") as mock_sleep:
            result = _send_with_retry(handler, event, max_retries=3)
        assert result is True
        assert handler.send.call_count == 3
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    def test_all_retries_exhausted_returns_false(self):
        handler = MagicMock()
        handler.send.side_effect = ConnectionError("permanently down")
        event = MagicMock(rule_name="r1")
        with patch("time.sleep"):
            result = _send_with_retry(handler, event, max_retries=3)
        assert result is False
        assert handler.send.call_count == 4  # 최초 시도 + 3회 재시도


class TestFailedSendCounter:
    def test_failed_send_increments_counter(self, tmp_path):
        handler = MagicMock()
        handler.send.side_effect = ConnectionError("down")
        engine = AlertEngine(history_dir=str(tmp_path))
        engine.add_rule(_make_rule("r1", handler))

        with patch("time.sleep"):
            engine.evaluate(_mock_evaluator())

        assert engine.get_failed_send_count() == 1

    def test_successful_send_does_not_increment_counter(self, tmp_path):
        handler = MagicMock()
        engine = AlertEngine(history_dir=str(tmp_path))
        engine.add_rule(_make_rule("r1", handler))

        engine.evaluate(_mock_evaluator())

        assert engine.get_failed_send_count() == 0
        handler.send.assert_called_once()


class TestAsyncDispatchDefaultUnchanged:
    def test_sync_default_calls_handler_before_evaluate_returns(self, tmp_path):
        """REQ-3: async_dispatch 기본값 False — 기존 test_evaluate_calls_handler_send와
        동일하게 evaluate() 반환 시점에 이미 handler.send()가 호출되어 있어야 한다."""
        handler = MagicMock()
        engine = AlertEngine(history_dir=str(tmp_path))
        engine.add_rule(_make_rule("r1", handler))

        engine.evaluate(_mock_evaluator())
        handler.send.assert_called_once()

    def test_async_dispatch_true_defers_send_to_background_thread(self, tmp_path):
        handler = MagicMock()
        engine = AlertEngine(history_dir=str(tmp_path), async_dispatch=True)
        engine.add_rule(_make_rule("r1", handler))

        engine.evaluate(_mock_evaluator())
        # 스레드가 시작되긴 했지만 즉시 완료를 보장하지 않음 — 짧게 대기 후 확인.
        for _ in range(50):
            if handler.send.called:
                break
            time.sleep(0.02)
        handler.send.assert_called_once()

    def test_async_dispatch_true_retries_do_not_block_evaluate(self, tmp_path):
        """async_dispatch=True에서는 재시도 백오프(최대 ~7초)가 evaluate() 반환을
        블로킹하지 않아야 한다."""
        handler = MagicMock()
        handler.send.side_effect = ConnectionError("down")
        engine = AlertEngine(history_dir=str(tmp_path), async_dispatch=True)
        engine.add_rule(_make_rule("r1", handler))

        start = time.monotonic()
        engine.evaluate(_mock_evaluator())
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, "async_dispatch=True인데 evaluate()가 재시도 대기로 블로킹됨"


class TestMarkFiredTimingUnchanged:
    def test_mark_fired_called_even_when_send_ultimately_fails(self, tmp_path):
        """REQ-4: 발송이 실패해도 규칙은 쿨다운에 들어간다(기존 동작 유지)."""
        handler = MagicMock()
        handler.send.side_effect = ConnectionError("down")
        engine = AlertEngine(history_dir=str(tmp_path))
        rule = _make_rule("r1", handler, cooldown=300)
        engine.add_rule(rule)

        with patch("time.sleep"):
            fired1 = engine.evaluate(_mock_evaluator())
        assert len(fired1) == 1
        assert rule.is_on_cooldown()

        # 쿨다운 중이므로 재평가해도 다시 발화하지 않음.
        fired2 = engine.evaluate(_mock_evaluator())
        assert fired2 == []


class TestAlertStormSuppression:
    def test_third_alert_in_window_is_suppressed(self, tmp_path):
        handlers = [MagicMock() for _ in range(3)]
        engine = AlertEngine(
            history_dir=str(tmp_path), max_alerts_per_window=2, window_seconds=60,
        )
        for i, h in enumerate(handlers):
            engine.add_rule(_make_rule(f"r{i}", h, cooldown=0))

        fired = engine.evaluate(_mock_evaluator())

        assert len(fired) == 3  # 히스토리/fired 리스트에는 3건 모두 기록
        handlers[0].send.assert_called_once()
        handlers[1].send.assert_called_once()
        handlers[2].send.assert_not_called()  # 3번째는 억제
        assert engine.get_suppressed_count() == 1

    def test_history_records_suppressed_alert_too(self, tmp_path):
        handlers = [MagicMock() for _ in range(2)]
        engine = AlertEngine(
            history_dir=str(tmp_path), max_alerts_per_window=1, window_seconds=60,
        )
        for i, h in enumerate(handlers):
            engine.add_rule(_make_rule(f"r{i}", h, cooldown=0))

        engine.evaluate(_mock_evaluator())

        history_events = engine.history.get_today()
        assert len(history_events) == 2  # 억제된 것도 감사 이력에는 남음

    def test_max_alerts_per_window_none_disables_throttle(self, tmp_path):
        """REQ-5: max_alerts_per_window 기본값(None) — 전역 스로틀 비활성, 기존과 동일."""
        handlers = [MagicMock() for _ in range(5)]
        engine = AlertEngine(history_dir=str(tmp_path))
        for i, h in enumerate(handlers):
            engine.add_rule(_make_rule(f"r{i}", h, cooldown=0))

        engine.evaluate(_mock_evaluator())

        for h in handlers:
            h.send.assert_called_once()
        assert engine.get_suppressed_count() == 0

    def test_window_expiry_allows_new_alerts(self, tmp_path):
        handler1 = MagicMock()
        handler2 = MagicMock()
        engine = AlertEngine(
            history_dir=str(tmp_path), max_alerts_per_window=1, window_seconds=0.05,
        )
        engine.add_rule(_make_rule("r1", handler1, cooldown=0))
        engine.evaluate(_mock_evaluator())
        handler1.send.assert_called_once()

        # r1을 제거해 두 번째 evaluate()가 r1 재발화로 윈도우 슬롯을 소모하지 않게 한다.
        engine.remove_rule("r1")
        time.sleep(0.1)  # 윈도우 만료 대기

        engine.add_rule(_make_rule("r2", handler2, cooldown=0))
        engine.evaluate(_mock_evaluator())
        handler2.send.assert_called_once()
        assert engine.get_suppressed_count() == 0
