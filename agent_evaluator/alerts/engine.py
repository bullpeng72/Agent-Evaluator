"""
AlertEngine — Phase 2-B 알림 시스템

품질 임계값 위반 시 즉시 알림을 발송한다.
규칙 기반 평가: AlertRule(name, condition, handler, cooldown, severity)
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agent_evaluator.anomaly.detector import AnomalyEvent
    from agent_evaluator.streaming.evaluator import StreamingEvaluator


def _send_with_retry(handler: Any, event: AlertEvent, max_retries: int = 3) -> bool:
    """(SPEC-015 REQ-1) 핸들러 전송 실패 시 지수 백오프로 재시도한다.

    ``LLMJudge._call_with_retry()``(SPEC-006, ``integrations/llm_judge.py``)와 동일한
    1s/2s/4s 간격 패턴을 재사용한다. rate-limit 여부를 구분하지 않고 모든 예외를 일시적
    실패로 간주해 재시도한다 — 알림 핸들러(Slack/Webhook/Email)는 rate-limit 전용 신호
    체계가 없어 재시도 대상을 더 세분화할 근거가 없기 때문이다.

    Returns:
        bool: 재시도 내 어느 시도에서든 성공하면 ``True``, 모든 시도가 실패하면 ``False``.
    """
    attempt = 0
    while True:
        try:
            handler.send(event)
            return True
        except Exception as e:
            if attempt >= max_retries:
                logger.warning(
                    "AlertEngine: handler.send() 최종 실패 — 규칙 '%s', %d회 재시도 소진: %s",
                    event.rule_name, max_retries, e,
                )
                return False
            delay = 2 ** attempt  # 1s, 2s, 4s, ...
            logger.debug(
                "AlertEngine: handler.send() 실패 — %ds 대기 후 재시도 (%d/%d): %s",
                delay, attempt + 1, max_retries, e,
            )
            time.sleep(delay)
            attempt += 1


@dataclass
class AlertEvent:
    """발화된 알림 이벤트."""
    rule_name: str
    severity: str
    message: str
    value: Any
    triggered_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "severity": self.severity,
            "message": self.message,
            "value": self.value,
            "triggered_at": self.triggered_at,
        }


@dataclass
class AlertRule:
    """알림 규칙.

    Args:
        name: 규칙 이름.
        condition: StreamingEvaluator를 인자로 받아 bool 반환하는 callable.
        handler: 알림 발송 핸들러 (SlackHandler, WebhookHandler 등).
        cooldown: 중복 알림 방지 쿨다운 (초). Default 300.
        severity: "warning" 또는 "critical". Default "warning".
        message_fn: 커스텀 메시지 생성 함수 (선택).
    """
    name: str
    condition: Callable[[StreamingEvaluator], bool]
    handler: Any
    cooldown: int = 300
    severity: str = "warning"
    message_fn: Callable[[StreamingEvaluator], str] | None = None
    _last_fired: float = field(default=0.0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def is_on_cooldown(self) -> bool:
        import time
        with self._lock:
            return (time.time() - self._last_fired) < self.cooldown

    def mark_fired(self) -> None:
        import time
        with self._lock:
            self._last_fired = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity,
            "cooldown": self.cooldown,
            "last_fired": datetime.fromtimestamp(self._last_fired).isoformat() if self._last_fired > 0 else None,
            "on_cooldown": self.is_on_cooldown(),
        }


class AlertHistory:
    """알림 히스토리 — results/alerts/YYYY-MM-DD.jsonl 파일에 저장."""

    def __init__(self, history_dir: str | None = None) -> None:
        if history_dir is None:
            from agent_evaluator.utils.path_helpers import get_evaluation_results_dir
            results_dir = get_evaluation_results_dir(create=False)
            history_dir = str(Path(results_dir) / "alerts")
        self.history_dir = Path(history_dir)
        self._lock = threading.Lock()

    def record(self, event: AlertEvent) -> None:
        with self._lock:
            self.history_dir.mkdir(parents=True, exist_ok=True)
            today = date.today().isoformat()
            path = self.history_dir / f"{today}.jsonl"
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def get_today(self) -> list[dict[str, Any]]:
        today = date.today().isoformat()
        return self._read_file(self.history_dir / f"{today}.jsonl")

    def get_recent(self, days: int = 7) -> list[dict[str, Any]]:
        results = []
        for i in range(days):
            d = (datetime.now() - timedelta(days=i)).date().isoformat()
            results.extend(self._read_file(self.history_dir / f"{d}.jsonl"))
        return results

    def _read_file(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except OSError:
            pass
        return records


class AlertEngine:
    """알림 엔진.

    Args:
        history_dir: 알림 히스토리 저장 디렉토리. None이면 기본 경로 사용.
        async_dispatch: (SPEC-015 REQ-3) ``True``이면 재시도-백오프를 포함한
            ``handler.send()`` 호출을 백그라운드 스레드로 디스패치해 ``evaluate()``가
            네트워크 I/O를 기다리지 않고 즉시 반환한다. 기본값 ``False``는 기존과 100%
            동일한 동기 발송(이번 스펙의 재시도-백오프는 적용되되 ``evaluate()`` 반환
            전에 완료됨).
        max_alerts_per_window: (SPEC-015 REQ-5) 트레일링 윈도우 내 전역 발송 상한.
            ``None``(기본값)이면 전역 스로틀 비활성 — 기존 동작과 100% 동일. 값이
            설정되면 윈도우 내 발송 한도 초과 시 이후 발화된 규칙은 히스토리에는
            기록되지만 ``handler.send()`` 디스패치는 건너뛴다("알림 폭풍 방지").
        window_seconds: 전역 스로틀의 윈도우 길이(초). Default 60.

    Example::
        engine = AlertEngine()
        engine.add_rule(AlertRule(
            name="TCR 급락",
            condition=lambda ev: ev.get_stats("5m")["tcr"] < 70,
            handler=SlackHandler(webhook_url="https://..."),
            cooldown=300,
            severity="critical",
        ))
        engine.evaluate(streaming_evaluator)
    """

    def __init__(
        self,
        history_dir: str | None = None,
        async_dispatch: bool = False,
        max_alerts_per_window: int | None = None,
        window_seconds: int = 60,
    ) -> None:
        self.history = AlertHistory(history_dir)
        self._rules: list[AlertRule] = []
        self._lock = threading.Lock()
        self.async_dispatch = async_dispatch
        self.max_alerts_per_window = max_alerts_per_window
        self.window_seconds = window_seconds
        self._failed_send_count = 0
        self._suppressed_count = 0
        self._dispatch_timestamps: list[float] = []
        self._counter_lock = threading.Lock()

        # SPEC-026 REQ-3: AnomalyEvent.type별 AlertRule 캐시 — evaluate()가 순회하는
        # self._rules와 의도적으로 분리한다. 이 캐시의 rule.condition은 항상 True를
        # 반환하는 더미라, self._rules에 섞이면 evaluate() 폴링마다 매번 재발화되는
        # 버그가 생긴다(이 캐시는 dispatch_anomaly_events()가 직접 조회할 때만 쓰인다).
        self._anomaly_rules: dict[str, AlertRule] = {}

    def add_rule(self, rule: AlertRule) -> AlertEngine:
        with self._lock:
            self._rules.append(rule)
        return self

    def remove_rule(self, name: str) -> None:
        with self._lock:
            self._rules = [r for r in self._rules if r.name != name]

    def get_rules(self) -> list[dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._rules]

    def get_failed_send_count(self) -> int:
        """(SPEC-015 REQ-2) 재시도를 모두 소진하고 최종 실패한 발송 횟수."""
        with self._counter_lock:
            return self._failed_send_count

    def get_suppressed_count(self) -> int:
        """(SPEC-015 REQ-5) 전역 스로틀에 의해 발송이 억제된 횟수."""
        with self._counter_lock:
            return self._suppressed_count

    def _should_suppress_for_storm(self) -> bool:
        """(SPEC-015 REQ-5) 전역 알림 폭풍 방지 — 트레일링 윈도우 내 발송 한도 확인."""
        if self.max_alerts_per_window is None:
            return False
        now = time.time()
        with self._counter_lock:
            cutoff = now - self.window_seconds
            self._dispatch_timestamps = [t for t in self._dispatch_timestamps if t >= cutoff]
            if len(self._dispatch_timestamps) >= self.max_alerts_per_window:
                self._suppressed_count += 1
                return True
            self._dispatch_timestamps.append(now)
            return False

    def _dispatch(self, rule: AlertRule, event: AlertEvent) -> None:
        """(SPEC-015 REQ-1/2) 재시도-백오프로 발송하고 최종 실패 시 카운터를 증가시킨다."""
        succeeded = _send_with_retry(rule.handler, event)
        if not succeeded:
            with self._counter_lock:
                self._failed_send_count += 1

    def evaluate(self, evaluator: Any) -> list[AlertEvent]:
        """모든 규칙을 평가하고 트리거된 알림을 반환.

        Args:
            evaluator: ``StreamingEvaluator`` 인스턴스 또는 ``get_stats(window)`` /
                ``get_stats(window)`` 인터페이스를 갖춘 duck-typed 객체.
                ``None`` 전달 시 빈 리스트 반환 (graceful degradation).
        """
        if evaluator is None:
            return []
        fired: list[AlertEvent] = []
        with self._lock:
            rules = list(self._rules)

        for rule in rules:
            if rule.is_on_cooldown():
                continue
            try:
                triggered = rule.condition(evaluator)
            except Exception:
                continue
            if not triggered:
                continue

            stats = evaluator.get_stats("5m")
            if rule.message_fn:
                try:
                    message = rule.message_fn(evaluator)
                except Exception:
                    message = f"규칙 [{rule.name}] 조건 충족"
            else:
                message = (
                    f"[{rule.severity.upper()}] {rule.name}\n"
                    f"5분 TCR: {stats.get('tcr', 0)}% | "
                    f"P95 지연: {stats.get('p95_latency', 0)}s | "
                    f"오류율: {stats.get('error_rate', 0)}%\n"
                    f"발화 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')}"
                )
            event = AlertEvent(
                rule_name=rule.name,
                severity=rule.severity,
                message=message,
                value=stats,
            )
            rule.mark_fired()
            self.history.record(event)

            # SPEC-015 REQ-5: 전역 알림 폭풍 방지 — 히스토리에는 남기되 발송만 억제.
            if not self._should_suppress_for_storm():
                if self.async_dispatch:
                    threading.Thread(
                        target=self._dispatch, args=(rule, event), daemon=True,
                    ).start()
                else:
                    self._dispatch(rule, event)

            fired.append(event)
        return fired

    def _get_or_create_anomaly_rule(
        self, anomaly_type: str, handler: Any, cooldown: int,
    ) -> AlertRule:
        """SPEC-026 REQ-3: ``AnomalyEvent.type``별 ``AlertRule``을 캐시한다 — 최초
        등장 시 생성하고, 이후 같은 타입은 그 규칙을 그대로 재사용해 쿨다운 상태
        (``_last_fired``)가 호출 간에 이어지게 한다. ``self._rules``(evaluate()가
        순회)와는 별개인 ``self._anomaly_rules``에만 저장된다."""
        rule_name = f"anomaly:{anomaly_type}"
        with self._lock:
            rule = self._anomaly_rules.get(rule_name)
            if rule is None:
                # condition은 이 경로에서 호출되지 않는다(이미 트리거된 이벤트를
                # 넘겨받으므로) — AlertRule 생성에 필요한 자리만 채우는 더미.
                rule = AlertRule(
                    name=rule_name, condition=lambda _ev: True, handler=handler, cooldown=cooldown,
                )
                self._anomaly_rules[rule_name] = rule
            return rule

    def dispatch_anomaly_events(
        self,
        events: list[AnomalyEvent],
        handler: Any,
        cooldown: int = 300,
    ) -> list[AlertEvent]:
        """SPEC-026 REQ-3: ``AnomalyDetector.scan()``이 반환한 ``AnomalyEvent`` 목록을
        기존 쿨다운/재시도-백오프/알림폭풍 방지 인프라를 통해 발송한다.

        새 쿨다운·재시도 로직을 만들지 않고, ``event.type``별로 캐시된 ``AlertRule``
        (:meth:`_get_or_create_anomaly_rule`)의 ``is_on_cooldown()``/``mark_fired()``와
        기존 :meth:`_dispatch`(SPEC-015 재시도-백오프)·:meth:`_should_suppress_for_storm`
        (SPEC-015 전역 알림폭풍 방지)를 그대로 재사용한다 — :meth:`evaluate`와 동일한
        발송 경로를 탄다.

        Args:
            events: ``AnomalyDetector.scan()``의 반환값.
            handler: 알림 발송 핸들러(SlackHandler 등) — 이 호출의 모든 이벤트가
                공유한다.
            cooldown: 이 호출에서 신규로 캐시할 규칙의 쿨다운(초). 이미 캐시된
                규칙(같은 ``event.type``)의 쿨다운은 최초 생성 시점 값을 유지한다
                (재호출마다 바뀌지 않음).

        Returns:
            실제로 발송된(쿨다운을 통과한) ``AlertEvent`` 목록 — :meth:`evaluate`와
            동일한 반환 형태.
        """
        fired: list[AlertEvent] = []
        for anomaly in events:
            rule = self._get_or_create_anomaly_rule(anomaly.type, handler, cooldown)
            if rule.is_on_cooldown():
                continue

            event = AlertEvent(
                rule_name=f"anomaly:{anomaly.type}",
                severity=anomaly.severity,
                message=anomaly.detail,
                value=anomaly.value,
            )
            rule.mark_fired()
            self.history.record(event)

            if not self._should_suppress_for_storm():
                if self.async_dispatch:
                    threading.Thread(
                        target=self._dispatch, args=(rule, event), daemon=True,
                    ).start()
                else:
                    self._dispatch(rule, event)

            fired.append(event)
        return fired
