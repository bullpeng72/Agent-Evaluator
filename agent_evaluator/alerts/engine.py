"""
AlertEngine — Phase 2-B 알림 시스템

품질 임계값 위반 시 즉시 알림을 발송한다.
규칙 기반 평가: AlertRule(name, condition, handler, cooldown, severity)
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agent_evaluator.streaming.evaluator import StreamingEvaluator


@dataclass
class AlertEvent:
    """발화된 알림 이벤트."""
    rule_name: str
    severity: str
    message: str
    value: Any
    triggered_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
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
    condition: Callable[["StreamingEvaluator"], bool]
    handler: Any
    cooldown: int = 300
    severity: str = "warning"
    message_fn: Optional[Callable[["StreamingEvaluator"], str]] = None
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity,
            "cooldown": self.cooldown,
            "last_fired": datetime.fromtimestamp(self._last_fired).isoformat() if self._last_fired > 0 else None,
            "on_cooldown": self.is_on_cooldown(),
        }


class AlertHistory:
    """알림 히스토리 — results/alerts/YYYY-MM-DD.jsonl 파일에 저장."""

    def __init__(self, history_dir: Optional[str] = None) -> None:
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

    def get_today(self) -> List[Dict[str, Any]]:
        today = date.today().isoformat()
        return self._read_file(self.history_dir / f"{today}.jsonl")

    def get_recent(self, days: int = 7) -> List[Dict[str, Any]]:
        results = []
        for i in range(days):
            d = (datetime.now() - timedelta(days=i)).date().isoformat()
            results.extend(self._read_file(self.history_dir / f"{d}.jsonl"))
        return results

    def _read_file(self, path: Path) -> List[Dict[str, Any]]:
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

    def __init__(self, history_dir: Optional[str] = None) -> None:
        self.history = AlertHistory(history_dir)
        self._rules: List[AlertRule] = []
        self._lock = threading.Lock()

    def add_rule(self, rule: AlertRule) -> "AlertEngine":
        with self._lock:
            self._rules.append(rule)
        return self

    def remove_rule(self, name: str) -> None:
        with self._lock:
            self._rules = [r for r in self._rules if r.name != name]

    def get_rules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._rules]

    def evaluate(self, evaluator: Any) -> List[AlertEvent]:
        """모든 규칙을 평가하고 트리거된 알림을 반환.

        Args:
            evaluator: ``StreamingEvaluator`` 인스턴스 또는 ``get_stats(window)`` /
                ``get_stats(window)`` 인터페이스를 갖춘 duck-typed 객체.
                ``None`` 전달 시 빈 리스트 반환 (graceful degradation).
        """
        if evaluator is None:
            return []
        fired: List[AlertEvent] = []
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
            try:
                rule.handler.send(event)
            except Exception as _e:
                logger.debug("Alert handler send failed (ignored): %s", _e)
            fired.append(event)
        return fired
