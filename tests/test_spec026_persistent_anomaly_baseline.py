"""
tests/test_spec026_persistent_anomaly_baseline.py
====================================================
SPEC-026 REQ-1: PerformanceMonitor.rehydrate_from_storage() — SQLite 재수화로
재시작 생존 이상탐지 기준선.
SPEC-026 REQ-5: AnomalyDetector._check_feedback_negativity — 부정 피드백 급증 탐지.
SPEC-026 REQ-2: StreamingEvaluator — 기존 flush 스레드에 얹은 주기적 이상탐지 스캔.
SPEC-026 REQ-3: AlertEngine.dispatch_anomaly_events — AnomalyEvent를 기존 쿨다운/
재시도-백오프 인프라로 발송.
"""
from __future__ import annotations

import dataclasses
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.alerts.engine import AlertEngine
from agent_evaluator.anomaly import AnomalyDetector
from agent_evaluator.anomaly.detector import AnomalyEvent
from agent_evaluator.streaming.evaluator import StreamingEvaluator
from agent_evaluator.storage.sqlite_backend import save_tasks_to_db


def _make_task(task_id: str, execution_time: float = 1.0, accuracy_score: float = 0.9):
    return create_taskresult(
        task_id=task_id, question=f"q-{task_id}", response=f"r-{task_id}",
        execution_time=execution_time, task_type="qa",
    )


class TestRehydrateFromStorage:
    def test_replays_all_tasks_by_default(self, tmp_path):
        db_path = tmp_path / "history.db"
        save_tasks_to_db(db_path, [_make_task(f"t{i}") for i in range(5)])

        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        n = monitor.rehydrate_from_storage(str(db_path))

        assert n == 5
        assert len(monitor.tcr_tracker.tasks) == 5

    def test_empty_db_returns_zero(self, tmp_path):
        db_path = tmp_path / "empty.db"
        save_tasks_to_db(db_path, [])

        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        n = monitor.rehydrate_from_storage(str(db_path))

        assert n == 0
        assert len(monitor.tcr_tracker.tasks) == 0

    def test_limit_replays_only_last_n(self, tmp_path):
        db_path = tmp_path / "history.db"
        tasks = [_make_task(f"t{i}") for i in range(5)]
        save_tasks_to_db(db_path, tasks)

        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        n = monitor.rehydrate_from_storage(str(db_path), limit=2)

        assert n == 2
        assert len(monitor.tcr_tracker.tasks) == 2
        replayed_ids = {t.task_id for t in monitor.tcr_tracker.tasks}
        # load_tasks_from_db()는 timestamp 오름차순 — limit=2는 가장 최근 2개(t3,t4)여야 한다.
        assert replayed_ids == {"t3", "t4"}

    def test_anomaly_detector_has_baseline_immediately_after_rehydrate(self, tmp_path):
        """재수화 직후(신규 record_task 호출 전) AnomalyDetector가 이미 과거 데이터를 본다."""
        db_path = tmp_path / "history.db"
        save_tasks_to_db(db_path, [_make_task(f"t{i}", execution_time=1.0) for i in range(10)])

        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        monitor.rehydrate_from_storage(str(db_path))

        assert len(monitor.latency_tracker.latencies) == 10
        # scan()이 재수화된 이력을 기준선으로 사용해 에러 없이 동작하는지 확인
        events = AnomalyDetector(baseline_window=10, detection_window=5).scan(monitor)
        assert isinstance(events, list)

    def test_llm_judge_field_preserved_when_not_reenabled(self, tmp_path):
        """enable_llm_judge=False(기본값)인 모니터로 재수화하면, 이미 채점된
        task.llm_judge 값이 재평가 없이 그대로 보존되어야 한다(비용 재발생 없음)."""
        db_path = tmp_path / "history.db"
        original = _make_task("t1")
        original_with_judge = dataclasses.replace(
            original,
            llm_judge={"scores": {"overall": 4.5}, "reasoning": "이미 채점됨", "model": "x"},
        )
        save_tasks_to_db(db_path, [original_with_judge])

        monitor = PerformanceMonitor(output_dir=str(tmp_path))  # enable_llm_judge 기본 False
        monitor.rehydrate_from_storage(str(db_path))

        replayed = monitor.tcr_tracker.tasks[0]
        assert replayed.llm_judge == {"scores": {"overall": 4.5}, "reasoning": "이미 채점됨", "model": "x"}

    def test_rehydrate_then_record_new_tasks_accumulates(self, tmp_path):
        db_path = tmp_path / "history.db"
        save_tasks_to_db(db_path, [_make_task(f"t{i}") for i in range(3)])

        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        monitor.rehydrate_from_storage(str(db_path))
        monitor.record_task(_make_task("new1"))

        assert len(monitor.tcr_tracker.tasks) == 4


def _feedback_entry(is_positive: bool) -> dict:
    return {"task_id": "t", "is_positive": is_positive}


def _make_feedback_monitor(feedbacks: list) -> MagicMock:
    monitor = MagicMock()
    monitor.feedback_tracker.feedbacks = feedbacks
    # scan()이 다른 체크에서 크래시하지 않도록 나머지 소스는 비워둔다.
    monitor.latency_tracker.latencies = []
    monitor.accuracy_evaluator.evaluations = []
    monitor.token_tracker.usage_log = []
    monitor.tcr_tracker.tasks = []
    monitor.input_sanitizer = None
    return monitor


class TestCheckFeedbackNegativity:
    """SPEC-026 REQ-5: AnomalyDetector._check_feedback_negativity."""

    def test_no_feedback_no_anomaly(self):
        detector = AnomalyDetector()
        monitor = _make_feedback_monitor([])
        assert detector._check_feedback_negativity(monitor) == []

    def test_negative_surge_detected(self):
        detector = AnomalyDetector(baseline_window=40, detection_window=10)
        # baseline: 30건 전부 긍정
        baseline = [_feedback_entry(is_positive=True)] * 30
        # recent: 10건 중 8건 부정 (80% 부정율)
        recent = [_feedback_entry(is_positive=False)] * 8 + [_feedback_entry(is_positive=True)] * 2
        monitor = _make_feedback_monitor(baseline + recent)
        events = detector._check_feedback_negativity(monitor)
        assert len(events) == 1
        assert events[0].type == "feedback_negativity"
        assert events[0].algorithm == "ratio"

    def test_low_negative_rate_ignored(self):
        detector = AnomalyDetector(baseline_window=100, detection_window=10)
        feedbacks = [_feedback_entry(is_positive=True)] * 100
        monitor = _make_feedback_monitor(feedbacks)
        assert detector._check_feedback_negativity(monitor) == []

    def test_critical_severity_above_30_percent(self):
        detector = AnomalyDetector(baseline_window=40, detection_window=10)
        baseline = [_feedback_entry(is_positive=True)] * 30
        recent = [_feedback_entry(is_positive=False)] * 10  # 100% 부정율
        monitor = _make_feedback_monitor(baseline + recent)
        events = detector._check_feedback_negativity(monitor)
        assert len(events) == 1
        assert events[0].severity == "critical"

    def test_missing_feedback_tracker_returns_empty(self):
        """feedback_tracker 자체가 없는(구버전 monitor 등) 경우에도 크래시하지 않는다."""
        detector = AnomalyDetector()
        monitor = SimpleNamespace(feedback_tracker=None)
        assert detector._check_feedback_negativity(monitor) == []  # type: ignore[arg-type] — only monitor.feedback_tracker is read; SimpleNamespace simulates a monitor without one

    def test_scan_includes_feedback_negativity(self):
        """scan()의 6개 체크 중 하나로 정상 등록되어 있는지 확인."""
        detector = AnomalyDetector(baseline_window=40, detection_window=10)
        baseline = [_feedback_entry(is_positive=True)] * 30
        recent = [_feedback_entry(is_positive=False)] * 10
        monitor = _make_feedback_monitor(baseline + recent)
        events = detector.scan(monitor)
        types = {e.type for e in events}
        assert "feedback_negativity" in types

    def test_existing_scan_tests_unaffected_by_bare_magicmock(self):
        """feedback_tracker를 명시적으로 설정하지 않은 기존 스타일의 MagicMock monitor에도
        크래시 없이 빈 리스트를 반환해야 한다(기존 test_anomaly_detector.py의 _make_monitor
        패턴과의 호환성 확인)."""
        detector = AnomalyDetector()
        monitor = MagicMock()
        monitor.tcr_tracker.tasks = []
        assert detector._check_feedback_negativity(monitor) == []

    def test_explain_event_has_suggestion(self):
        from agent_evaluator.anomaly.detector import AnomalyEvent

        detector = AnomalyDetector()
        event = AnomalyEvent(
            type="feedback_negativity", severity="warning", detail="d", value=0.5, threshold=0.2,
        )
        explanation = detector.explain_event(event)
        assert "suggested_action" in explanation
        assert explanation["suggested_action"] != "Analyze this metric in detail."


def _make_streaming_evaluator(**kwargs) -> StreamingEvaluator:
    return StreamingEvaluator(monitor=MagicMock(), **kwargs)


class _StubDetector:
    """실제 AnomalyDetector 대신 호출 여부/반환값을 통제하는 테스트용 스텁."""

    def __init__(self, events=None, raise_error=False):
        self._events = events if events is not None else []
        self._raise_error = raise_error
        self.call_count = 0

    def scan(self, monitor):
        self.call_count += 1
        if self._raise_error:
            raise RuntimeError("scan boom")
        return self._events


class TestStreamingEvaluatorAnomalyScan:
    """SPEC-026 REQ-2: StreamingEvaluator(anomaly_detector=..., anomaly_scan_interval=...)."""

    def test_default_anomaly_detector_none(self):
        ev = _make_streaming_evaluator(flush_interval=3600)
        assert ev.anomaly_detector is None
        assert ev._last_anomalies == []

    def test_maybe_scan_skips_when_no_detector(self):
        ev = _make_streaming_evaluator(flush_interval=3600)
        ev._last_anomaly_scan_time = 0.0  # 충분히 과거
        ev._maybe_scan_anomalies()
        assert ev._last_anomalies == []

    def test_maybe_scan_runs_when_interval_elapsed(self):
        stub = _StubDetector(events=["anomaly-1"])
        ev = _make_streaming_evaluator(
            flush_interval=3600, anomaly_detector=stub, anomaly_scan_interval=1,
        )
        ev._last_anomaly_scan_time = 0.0  # 충분히 과거 → 즉시 스캔 대상
        ev._maybe_scan_anomalies()
        assert stub.call_count == 1
        assert ev._last_anomalies == ["anomaly-1"]
        assert ev._last_anomaly_scan_time > 0.0

    def test_maybe_scan_skips_when_interval_not_elapsed(self):
        stub = _StubDetector(events=["anomaly-1"])
        ev = _make_streaming_evaluator(
            flush_interval=3600, anomaly_detector=stub, anomaly_scan_interval=300,
        )
        ev._last_anomaly_scan_time = time.time()  # 방금 스캔함
        ev._maybe_scan_anomalies()
        assert stub.call_count == 0
        assert ev._last_anomalies == []

    def test_scan_exception_is_caught_and_ignored(self):
        stub = _StubDetector(raise_error=True)
        ev = _make_streaming_evaluator(
            flush_interval=3600, anomaly_detector=stub, anomaly_scan_interval=1,
        )
        ev._last_anomaly_scan_time = 0.0
        ev._maybe_scan_anomalies()  # 예외를 던지지 않아야 한다
        assert stub.call_count == 1
        assert ev._last_anomalies == []  # 실패 시 이전 값(빈 리스트) 유지

    def test_previous_anomalies_kept_on_scan_failure(self):
        """직전 스캔 결과가 있는 상태에서 이후 스캔이 실패하면, 오래된 결과라도
        무의미한 초기화보다 그대로 유지하는 편이 낫다는 설계를 확인한다."""
        stub = _StubDetector(events=["first"])
        ev = _make_streaming_evaluator(
            flush_interval=3600, anomaly_detector=stub, anomaly_scan_interval=1,
        )
        ev._last_anomaly_scan_time = 0.0
        ev._maybe_scan_anomalies()
        assert ev._last_anomalies == ["first"]

        stub._raise_error = True
        ev._last_anomaly_scan_time = 0.0
        ev._maybe_scan_anomalies()
        assert ev._last_anomalies == ["first"]  # 실패해도 직전 값 유지

    def test_start_sets_last_anomaly_scan_time_to_now(self):
        ev = _make_streaming_evaluator(flush_interval=3600)
        before = time.time()
        ev.start()
        try:
            assert ev._last_anomaly_scan_time >= before
        finally:
            ev.stop()

    def test_flush_loop_invokes_periodic_scan(self):
        """실제 백그라운드 스레드(flush_interval)가 짧은 anomaly_scan_interval을
        실제로 트리거하는지 통합 확인 — 매우 짧은 간격을 쓰고 넉넉한 타임아웃으로
        폴링한다."""
        stub = _StubDetector(events=["e"])
        ev = _make_streaming_evaluator(
            flush_interval=0.05, anomaly_detector=stub, anomaly_scan_interval=0.01,
        )
        ev.start()
        try:
            deadline = time.time() + 2.0
            while stub.call_count == 0 and time.time() < deadline:
                time.sleep(0.02)
            assert stub.call_count >= 1
            assert ev._last_anomalies == ["e"]
        finally:
            ev.stop()

    def test_real_anomaly_detector_integration(self):
        """실제 AnomalyDetector.scan()과의 통합 — monitor에 데이터가 없으면 빈 리스트."""
        from agent_evaluator.anomaly import AnomalyDetector as _RealDetector

        real_monitor = MagicMock()
        real_monitor.latency_tracker.latencies = []
        real_monitor.accuracy_evaluator.evaluations = []
        real_monitor.token_tracker.usage_log = []
        real_monitor.tcr_tracker.tasks = []
        real_monitor.input_sanitizer = None
        real_monitor.feedback_tracker = None

        ev = StreamingEvaluator(
            monitor=real_monitor, flush_interval=3600,
            anomaly_detector=_RealDetector(), anomaly_scan_interval=1,
        )
        ev._last_anomaly_scan_time = 0.0
        ev._maybe_scan_anomalies()
        assert ev._last_anomalies == []


def _make_alert_engine(tmp_path) -> AlertEngine:
    return AlertEngine(history_dir=str(tmp_path))


def _noop_handler() -> MagicMock:
    handler = MagicMock()
    handler.send = MagicMock()
    return handler


def _anomaly(type_: str = "latency_trend", severity: str = "warning", value: float = 0.5) -> AnomalyEvent:
    return AnomalyEvent(
        type=type_, severity=severity, detail=f"{type_} detected", value=value, threshold=0.2,
    )


class TestDispatchAnomalyEvents:
    """SPEC-026 REQ-3: AlertEngine.dispatch_anomaly_events()."""

    def test_dispatches_and_calls_handler_send(self, tmp_path):
        engine = _make_alert_engine(tmp_path)
        handler = _noop_handler()
        fired = engine.dispatch_anomaly_events([_anomaly()], handler=handler, cooldown=0)
        assert len(fired) == 1
        handler.send.assert_called_once()
        assert fired[0].rule_name == "anomaly:latency_trend"
        assert fired[0].severity == "warning"
        assert fired[0].message == "latency_trend detected"
        assert fired[0].value == 0.5

    def test_respects_cooldown_per_type(self, tmp_path):
        engine = _make_alert_engine(tmp_path)
        handler = _noop_handler()
        fired1 = engine.dispatch_anomaly_events([_anomaly("latency_trend")], handler, cooldown=3600)
        fired2 = engine.dispatch_anomaly_events([_anomaly("latency_trend")], handler, cooldown=3600)
        assert len(fired1) == 1
        assert len(fired2) == 0  # 쿨다운 내 재발화 차단

    def test_different_types_have_independent_cooldowns(self, tmp_path):
        engine = _make_alert_engine(tmp_path)
        handler = _noop_handler()
        fired = engine.dispatch_anomaly_events(
            [_anomaly("latency_trend"), _anomaly("token_spike")], handler, cooldown=3600,
        )
        assert len(fired) == 2  # 서로 다른 type — 독립적인 쿨다운

        fired_again = engine.dispatch_anomaly_events(
            [_anomaly("latency_trend"), _anomaly("token_spike")], handler, cooldown=3600,
        )
        assert len(fired_again) == 0  # 둘 다 이미 쿨다운 중

    def test_zero_cooldown_fires_every_time(self, tmp_path):
        engine = _make_alert_engine(tmp_path)
        handler = _noop_handler()
        fired1 = engine.dispatch_anomaly_events([_anomaly()], handler, cooldown=0)
        fired2 = engine.dispatch_anomaly_events([_anomaly()], handler, cooldown=0)
        assert len(fired1) == 1
        assert len(fired2) == 1

    def test_does_not_pollute_get_rules(self, tmp_path):
        """anomaly 전용 규칙 캐시(_anomaly_rules)는 evaluate()가 순회하는 self._rules와
        분리되어 있어야 한다 — get_rules()에 노출되지 않는다."""
        engine = _make_alert_engine(tmp_path)
        engine.dispatch_anomaly_events([_anomaly()], handler=_noop_handler(), cooldown=0)
        assert engine.get_rules() == []

    def test_does_not_trigger_via_evaluate(self, tmp_path):
        """dispatch_anomaly_events()가 만든 내부 규칙이 evaluate() 폴링에서
        재발화되면 안 된다(조건이 항상 True인 더미라 사고가 나기 쉬운 지점)."""
        engine = _make_alert_engine(tmp_path)
        handler = _noop_handler()
        engine.dispatch_anomaly_events([_anomaly()], handler=handler, cooldown=0)
        handler.send.reset_mock()

        mock_evaluator = MagicMock()
        mock_evaluator.get_stats.return_value = {"tcr": 100, "p95_latency": 0, "error_rate": 0}
        fired = engine.evaluate(mock_evaluator)

        assert fired == []
        handler.send.assert_not_called()

    def test_empty_events_returns_empty(self, tmp_path):
        engine = _make_alert_engine(tmp_path)
        assert engine.dispatch_anomaly_events([], handler=_noop_handler(), cooldown=0) == []

    def test_records_to_history(self, tmp_path):
        engine = _make_alert_engine(tmp_path)
        engine.dispatch_anomaly_events([_anomaly()], handler=_noop_handler(), cooldown=0)
        today = engine.history.get_today()
        assert len(today) == 1
        assert today[0]["rule_name"] == "anomaly:latency_trend"

    def test_storm_suppression_blocks_send_but_still_reports_fired(self, tmp_path):
        """SPEC-015 알림폭풍 방지 재사용 — 억제되어도 fired 목록에는 남는다(evaluate()와
        동일한 기존 동작)."""
        engine = AlertEngine(history_dir=str(tmp_path), max_alerts_per_window=1)
        handler = _noop_handler()
        fired = engine.dispatch_anomaly_events(
            [_anomaly("latency_trend"), _anomaly("token_spike")], handler, cooldown=0,
        )
        assert len(fired) == 2
        assert handler.send.call_count == 1  # 두 번째는 억제됨
        assert engine.get_suppressed_count() == 1


class TestStreamingEvaluatorDispatchWiring:
    """SPEC-026 REQ-4: StreamingEvaluator가 REQ-2(스캔)와 REQ-3(dispatch)을 잇는 배선."""

    def test_no_dispatch_when_last_anomalies_empty(self):
        ev = _make_streaming_evaluator(flush_interval=3600)
        ev.alert_handler = MagicMock()
        ev.anomaly_alert_handler = MagicMock()
        ev._last_anomalies = []
        ev._maybe_dispatch_anomalies()
        ev.alert_handler.dispatch_anomaly_events.assert_not_called()

    def test_no_dispatch_when_alert_handler_missing(self):
        ev = _make_streaming_evaluator(flush_interval=3600)
        ev.alert_handler = None
        ev.anomaly_alert_handler = MagicMock()
        ev._last_anomalies = [_anomaly()]
        ev._maybe_dispatch_anomalies()  # 크래시하지 않아야 한다

    def test_no_dispatch_when_anomaly_alert_handler_missing(self):
        ev = _make_streaming_evaluator(flush_interval=3600)
        ev.alert_handler = MagicMock()
        ev.anomaly_alert_handler = None
        ev._last_anomalies = [_anomaly()]
        ev._maybe_dispatch_anomalies()
        ev.alert_handler.dispatch_anomaly_events.assert_not_called()

    def test_dispatch_called_with_events_and_handler(self):
        ev = _make_streaming_evaluator(flush_interval=3600)
        ev.alert_handler = MagicMock()
        notify_handler = MagicMock()
        ev.anomaly_alert_handler = notify_handler
        events = [_anomaly("latency_trend"), _anomaly("token_spike")]
        ev._last_anomalies = events
        ev._maybe_dispatch_anomalies()
        ev.alert_handler.dispatch_anomaly_events.assert_called_once_with(events, handler=notify_handler)

    def test_dispatch_exception_is_caught(self):
        ev = _make_streaming_evaluator(flush_interval=3600)
        ev.alert_handler = MagicMock()
        ev.alert_handler.dispatch_anomaly_events.side_effect = RuntimeError("boom")
        ev.anomaly_alert_handler = MagicMock()
        ev._last_anomalies = [_anomaly()]
        ev._maybe_dispatch_anomalies()  # 예외를 전파하지 않아야 한다

    def test_end_to_end_scan_then_dispatch_via_real_alert_engine(self, tmp_path):
        """실제 AnomalyDetector.scan()이 이상을 발견하면, 실제 AlertEngine을 거쳐
        handler.send()까지 호출되는 전 구간을 확인한다(REQ-2→REQ-3→REQ-4 통합)."""
        stub_detector = _StubDetector(events=[_anomaly("latency_trend")])
        real_engine = AlertEngine(history_dir=str(tmp_path))
        notify_handler = _noop_handler()

        ev = _make_streaming_evaluator(
            flush_interval=3600,
            alert_handler=real_engine,
            anomaly_detector=stub_detector,
            anomaly_scan_interval=1,
            anomaly_alert_handler=notify_handler,
        )
        ev._last_anomaly_scan_time = 0.0
        ev._maybe_scan_anomalies()

        assert len(ev._last_anomalies) == 1
        assert ev._last_anomalies[0].type == "latency_trend"
        notify_handler.send.assert_called_once()

    def test_scan_without_anomalies_does_not_dispatch(self, tmp_path):
        stub_detector = _StubDetector(events=[])  # 이상 없음
        real_engine = AlertEngine(history_dir=str(tmp_path))
        notify_handler = _noop_handler()

        ev = _make_streaming_evaluator(
            flush_interval=3600,
            alert_handler=real_engine,
            anomaly_detector=stub_detector,
            anomaly_scan_interval=1,
            anomaly_alert_handler=notify_handler,
        )
        ev._last_anomaly_scan_time = 0.0
        ev._maybe_scan_anomalies()

        assert ev._last_anomalies == []
        notify_handler.send.assert_not_called()

    def test_default_anomaly_alert_handler_is_none(self):
        ev = _make_streaming_evaluator(flush_interval=3600)
        assert ev.anomaly_alert_handler is None
