"""
12_alerting_eval.py — 실시간 알림 엔진 예제
=============================================

두 가지 알림 패턴을 시연합니다:

패턴 A — StreamingEvaluator + AlertEngine (시간 윈도우 기반 통계 알림):
  AlertEngine · AlertRule · AlertEvent · AlertHistory
  SlackHandler · WebhookHandler

패턴 B — @agent_eval + SimpleTaskAlertRule (TaskResult 기반 경량 알림):
  StreamingEvaluator 없이 개별 TaskResult 조건으로 즉시 알림
  alert_rules=[SimpleTaskAlertRule(...)] 파라미터로 통합

핵심 시나리오:
  [A] 1. 정상 구간 (10개 태스크) — 알림 없음 예상
  [A] 2. 이상 구간 (고지연 + 오류 급등, 20개 태스크) — warning/critical 발생
  [A] 3. 쿨다운 동작 확인 — 같은 규칙이 연속 발동되지 않음
  [A] 4. AlertHistory 이력 조회
  [B] 5. @agent_eval(alert_rules=[...]) 패턴 시연

실행:
    python Evaluator_Examples/12_alerting_eval.py    # API 키 불필요 — 순수 시뮬레이션
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import time

from agent_evaluator import PerformanceMonitor, create_taskresult, SimpleTaskAlertRule
from agent_evaluator.decorators import agent_eval
from agent_evaluator.streaming.evaluator import StreamingEvaluator
from agent_evaluator.alerts.engine import AlertEngine, AlertRule, AlertEvent
from agent_evaluator.alerts.handlers import SlackHandler, WebhookHandler


def _try_setup_otel(service_name: str) -> None:
    """Phoenix가 실행 중이면 OTEL 활성화 (선택적). 미실행 시 무시."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
        _s.settimeout(1)
        if _s.connect_ex(("localhost", 6006)) != 0:
            return
    try:
        from agent_evaluator import setup_otel
        setup_otel(endpoint="http://localhost:6006", service_name=service_name)
        print(f"  📡  Phoenix 모니터링 활성화 — http://localhost:6006  (service: {service_name})")
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).debug("setup_otel 실패: %s", _e)

_try_setup_otel("12-alerting-eval")

import os as _os


def _build_slack_handler() -> "SlackHandler":
    """SLACK_WEBHOOK_URL 설정 시 실제 SlackHandler, 아닌 경우 Mock 반환."""
    url = _os.getenv("SLACK_WEBHOOK_URL", "")
    if url:
        channel = _os.getenv("SLACK_CHANNEL", "#agent-alerts")
        print(f"  📨  Slack 실제 발송 활성화 — channel: {channel}")
        return SlackHandler(webhook_url=url, channel=channel)
    return _MockSlackHandler()


def _build_webhook_handler() -> "WebhookHandler":
    """ALERT_WEBHOOK_URL 설정 시 실제 WebhookHandler, 아닌 경우 Mock 반환."""
    url = _os.getenv("ALERT_WEBHOOK_URL", "")
    if url:
        print(f"  📨  Webhook 실제 발송 활성화 — {url}")
        return WebhookHandler(url=url)
    return _MockWebhookHandler()


# ─── 모의(Mock) 핸들러 — 실제 HTTP 호출 없이 동작 기록 ───────────────────────
class _MockSlackHandler(SlackHandler):
    """테스트용 Slack 핸들러 — 실제 발송 없이 수신 기록."""

    def __init__(self):
        self.webhook_url = "https://hooks.slack.com/mock/test"
        self.channel = "#agent-alerts"
        self.username = "Agent Evaluator (Mock)"
        self.sent: list[dict] = []

    def send(self, event: "AlertEvent") -> None:
        record = {
            "rule": event.rule_name,
            "severity": event.severity,
            "message": event.message,
            "value": event.value,
            "triggered_at": event.triggered_at,
        }
        self.sent.append(record)
        sev_icon = "🔴" if event.severity == "critical" else "🟡"
        print(f"    {sev_icon} [Slack] {event.rule_name}: {event.message[:60]}")


class _MockWebhookHandler(WebhookHandler):
    """테스트용 Webhook 핸들러 — 실제 HTTP 호출 없이 수신 기록."""

    def __init__(self):
        self.url = "https://ops.example.com/mock/alerts"
        self.headers = {"Content-Type": "application/json"}
        self.method = "POST"
        self.sent: list[dict] = []

    def send(self, event: "AlertEvent") -> None:
        payload = event.to_dict()
        self.sent.append(payload)
        sev_icon = "🔴" if event.severity == "critical" else "🟡"
        print(f"    {sev_icon} [Webhook] {event.rule_name} (severity={event.severity})")


def run_alerting_evaluation():
    print("\n" + "=" * 70)
    print("  실시간 알림 엔진 평가 — Agent Evaluator v0.6.7")
    print("  Phase 2-B: AlertEngine · AlertRule · SlackHandler · WebhookHandler")
    print("=" * 70)

    rng = random.Random(20250402)
    results_dir = project_root / "results"
    results_dir.mkdir(exist_ok=True)

    # ── 핸들러 초기화 (SLACK_WEBHOOK_URL / ALERT_WEBHOOK_URL 설정 시 실제 발송) ──
    slack_handler   = _build_slack_handler()
    webhook_handler = _build_webhook_handler()

    # ── AlertEngine 구성 ─────────────────────────────────────────────────
    alert_engine = AlertEngine(history_dir=str(results_dir / "alerts"))

    # 규칙 1: P95 지연 급등 (5m 윈도우 p95_latency > 1.5초)
    alert_engine.add_rule(AlertRule(
        name="high_p95_latency",
        condition=lambda ev: ev.get_stats("5m").get("p95_latency", 0) > 1.5,
        handler=slack_handler,
        cooldown=60,
        severity="warning",
        message_fn=lambda ev: (
            f"P95 지연 {ev.get_stats('5m').get('p95_latency', 0)*1000:.0f}ms "
            f"(임계값 1500ms 초과)"
        ),
    ))

    # 규칙 2: 오류율 급등 — critical (1m 윈도우, error_rate는 이미 % 단위 → > 20.0)
    alert_engine.add_rule(AlertRule(
        name="error_surge",
        condition=lambda ev: ev.get_stats("1m").get("error_rate", 0) > 20.0,
        handler=webhook_handler,
        cooldown=60,
        severity="critical",
        message_fn=lambda ev: (
            f"오류율 {ev.get_stats('1m').get('error_rate', 0):.1f}% "
            f"(임계값 20% 초과)"
        ),
    ))

    # 규칙 3: TCR 급락 (1h 윈도우, tcr는 이미 % 단위 → < 60.0)
    alert_engine.add_rule(AlertRule(
        name="low_tcr",
        condition=lambda ev: (
            ev.get_stats("1h").get("count", 0) > 0
            and ev.get_stats("1h").get("tcr", 100.0) < 60.0
        ),
        handler=slack_handler,
        cooldown=60,
        severity="warning",
        message_fn=lambda ev: (
            f"TCR {ev.get_stats('1h').get('tcr', 0):.1f}% "
            f"(임계값 60% 미만)"
        ),
    ))

    print(f"\n  등록된 알림 규칙: {len(alert_engine.get_rules())}개")
    for r in alert_engine.get_rules():
        print(f"    - {r['name']}  severity={r['severity']}  cooldown={r['cooldown']}s")

    # ── PerformanceMonitor + StreamingEvaluator 설정 ────────────────────
    monitor = PerformanceMonitor(output_dir=str(results_dir))
    streamer = StreamingEvaluator(monitor=monitor, flush_interval=30)
    streamer.start()

    all_events: list[AlertEvent] = []

    # ─────────────────────────────────────────────────────────────────────
    # 시나리오 1: 정상 구간 (10개 태스크 — 알림 없음)
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  {'─'*70}")
    print(f"  [시나리오 1] 정상 구간 — 10개 태스크 (알림 없음 예상)")
    print(f"  {'─'*70}")
    events_phase1: list[AlertEvent] = []
    for i in range(10):
        task_id = f"normal_{i+1:03d}"
        exec_t = rng.uniform(0.2, 0.6)
        task = create_taskresult(
            task_id=task_id, question="정상 질문", response="정상 응답",
            ground_truth="정상", execution_time=exec_t, task_type="qa",
        )
        monitor.record_task(task)
        streamer.record(task_id=task_id, success=True,
                        execution_time=exec_t, tokens_used=rng.randint(100, 300),
                        accuracy_score=rng.uniform(0.80, 0.96), has_error=False)
        fired = alert_engine.evaluate(streamer)
        events_phase1.extend(fired)

    all_events.extend(events_phase1)
    phase1_stats = streamer.get_stats("5m")
    print(f"  정상 구간 통계: TCR={phase1_stats.get('tcr', 0):.1f}%  "
          f"P95={phase1_stats.get('p95_latency', 0)*1000:.0f}ms  "
          f"오류율={phase1_stats.get('error_rate', 0):.1f}%")
    print(f"  발생 알림: {len(events_phase1)}건")

    # ─────────────────────────────────────────────────────────────────────
    # 시나리오 2: 고지연 + 오류 급등 (20개 태스크 — 알림 발생 예상)
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  {'─'*70}")
    print(f"  [시나리오 2] 이상 구간 — 20개 태스크 (고지연 + 70% 오류)")
    print(f"  {'─'*70}")
    events_phase2: list[AlertEvent] = []
    for i in range(20):
        task_id = f"anomaly_{i+1:03d}"
        success = rng.random() > 0.70   # 70% 오류
        exec_t = rng.uniform(2.0, 4.5) if not success else rng.uniform(0.3, 0.8)
        task = create_taskresult(
            task_id=task_id, question="이상 질문", response="이상 응답" if success else "실패",
            ground_truth="정답", execution_time=exec_t, task_type="reasoning",
            has_error=not success,
        )
        monitor.record_task(task)
        streamer.record(task_id=task_id, success=success,
                        execution_time=exec_t, tokens_used=rng.randint(50, 200),
                        accuracy_score=0.0 if not success else 0.65, has_error=not success)
        fired = alert_engine.evaluate(streamer)
        if fired:
            events_phase2.extend(fired)
            for ev in fired:
                icon = "🔴" if ev.severity == "critical" else "🟡"
                print(f"  {icon} 알림 발생: [{ev.rule_name}] {ev.severity}")

    all_events.extend(events_phase2)
    phase2_stats = streamer.get_stats("5m")
    print(f"\n  이상 구간 통계: TCR={phase2_stats.get('tcr', 0):.1f}%  "
          f"P95={phase2_stats.get('p95_latency', 0)*1000:.0f}ms  "
          f"오류율={phase2_stats.get('error_rate', 0):.1f}%")
    print(f"  발생 알림: {len(events_phase2)}건")

    # ─────────────────────────────────────────────────────────────────────
    # 시나리오 3: 쿨다운 테스트 — 같은 알림이 즉시 재발동 안 됨
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  {'─'*70}")
    print(f"  [시나리오 3] 쿨다운 테스트 — 이상 조건 지속 중 재발동 여부")
    print(f"  {'─'*70}")
    events_cooldown: list[AlertEvent] = []
    # 이상 조건 유지 (고지연 추가 5개)
    for i in range(5):
        task_id = f"cooldown_{i+1:03d}"
        exec_t = rng.uniform(3.0, 5.0)
        task = create_taskresult(
            task_id=task_id, question="쿨다운 테스트", response="실패",
            ground_truth="정답", execution_time=exec_t, task_type="qa",
            has_error=True,
        )
        monitor.record_task(task)
        streamer.record(task_id=task_id, success=False,
                        execution_time=exec_t, tokens_used=50, accuracy_score=0.0, has_error=True)
        fired = alert_engine.evaluate(streamer)
        events_cooldown.extend(fired)

    all_events.extend(events_cooldown)
    print(f"  쿨다운 구간 재발동: {len(events_cooldown)}건 (쿨다운이 올바르면 0건)")

    streamer.stop()

    # ── AlertRule API 시연 ────────────────────────────────────────────────
    print(f"\n  {'─'*70}")
    print(f"  [AlertRule API] 규칙 직렬화 · 쿨다운 상태")
    print(f"  {'─'*70}")
    for r_dict in alert_engine.get_rules():
        cd_on = r_dict.get("on_cooldown", False)
        print(f"  - {r_dict['name']:<22}  severity={r_dict['severity']}  "
              f"on_cooldown={cd_on}  last_fired={r_dict.get('last_fired', 'never')}")

    # ── AlertEvent API 시연 ───────────────────────────────────────────────
    if all_events:
        print(f"\n  [AlertEvent] 첫 번째 이벤트 구조")
        ev_dict = all_events[0].to_dict()
        for k, v in ev_dict.items():
            if k != "value":  # value는 stats dict로 길어서 생략
                print(f"    {k}: {str(v)[:60]}")

    # ── AlertHistory 조회 ────────────────────────────────────────────────
    print(f"\n  {'─'*70}")
    print(f"  [AlertHistory] 오늘 발생 알림 이력")
    print(f"  {'─'*70}")
    today_alerts = alert_engine.history.get_today()
    print(f"  오늘 총 알림: {len(today_alerts)}건")
    for a in today_alerts:
        sev_icon = "🔴" if a.get("severity") == "critical" else "🟡"
        print(f"  {sev_icon} [{a.get('rule_name', '?')}] {a.get('message', '')[:55]}  "
              f"({a.get('triggered_at', '')[:19]})")

    # ── 핸들러 발송 통계 ─────────────────────────────────────────────────
    print(f"\n  {'─'*70}")
    print(f"  [핸들러 발송 통계]")
    print(f"  {'─'*70}")
    print(f"  SlackHandler   발송: {len(slack_handler.sent)}건")
    for s in slack_handler.sent:
        print(f"    → {s['rule']} ({s['severity']})  {s['message'][:50]}")
    print(f"  WebhookHandler 발송: {len(webhook_handler.sent)}건")
    for w in webhook_handler.sent:
        print(f"    → {w.get('rule_name', '?')} ({w.get('severity', '?')})")

    # ── 전체 알림 요약 ────────────────────────────────────────────────────
    total_fired     = len(all_events)
    has_warning     = any(e.severity == "warning"  for e in all_events)
    has_critical    = any(e.severity == "critical" for e in all_events)
    total_handler   = len(slack_handler.sent) + len(webhook_handler.sent)

    print(f"\n  전체 발생 알림: {total_fired}건  "
          f"(warning={sum(1 for e in all_events if e.severity=='warning')}건, "
          f"critical={sum(1 for e in all_events if e.severity=='critical')}건)")

    # ── 검증 테이블 ───────────────────────────────────────────────────────
    checks = [
        ("정상 구간 알림 없음",          f"{len(events_phase1)}건",    len(events_phase1) == 0),
        ("이상 구간 알림 발생",          f"{len(events_phase2)}건",    len(events_phase2) > 0),
        ("핸들러 발송 확인",            f"{total_handler}건",          total_handler > 0),
        ("AlertHistory 기록",           f"{len(today_alerts)}건",     len(today_alerts) > 0),
        ("warning 이벤트 존재",         str(has_warning),             has_warning),
        ("critical 이벤트 존재",        str(has_critical),            has_critical),
        ("쿨다운 재발동 차단",           f"{len(events_cooldown)}건",  len(events_cooldown) == 0),
        ("AlertRule.to_dict() 동작",    "성공",                       True),
    ]

    print(f"\n  {'═'*62}")
    print(f"  {'검증 항목':<30} {'실측값':<14} 결과")
    print(f"  {'─'*62}")
    pass_cnt = 0
    for chk, actual, ok in checks:
        mark = "PASS ✅" if ok else "FAIL ❌"
        if ok:
            pass_cnt += 1
        print(f"  {chk:<30} {actual:<14} {mark}")
    print(f"  {'═'*62}")
    print(f"  합계: {pass_cnt}/{len(checks)} 통과\n")

    # Phoenix Annotation API 전송 (accuracy / completion / success 점수)
    saved = monitor.save_to_file("12_alerting_eval")
    print(f"  결과 저장: {saved}")


# ═══════════════════════════════════════════════════════════════════════════
# 패턴 B — @agent_eval + SimpleTaskAlertRule (TaskResult 기반 경량 알림)
# ═══════════════════════════════════════════════════════════════════════════

def run_simple_task_alerting():
    """@agent_eval(alert_rules=[...]) 패턴 — StreamingEvaluator 불필요.

    SimpleTaskAlertRule은 개별 TaskResult를 평가해 조건 충족 시 즉시 handler를
    호출합니다. 시간 윈도우 통계가 아닌 개별 태스크 수준의 경량 알림입니다.

    사용 예:
        from agent_evaluator import SimpleTaskAlertRule, AlertRuleBuilder

        rule = SimpleTaskAlertRule(
            name="slow_response",
            condition=lambda tr: tr.execution_time > 3.0,
            handler=lambda msg, tr: print(f"[ALERT] {msg}"),
            severity="warning",
            cooldown=10,
        )

        # 또는 AlertRuleBuilder 팩토리 사용
        rule = AlertRuleBuilder.when_latency_above(
            threshold=3.0,
            handler=lambda msg, tr: print(msg),
            severity="warning",
        )
    """
    print("\n" + "=" * 70)
    print("  패턴 B — @agent_eval + SimpleTaskAlertRule")
    print("  TaskResult 조건 기반 경량 알림 (StreamingEvaluator 불필요)")
    print("=" * 70)

    fired_alerts: list[str] = []

    def _on_slow(msg: str, tr):
        fired_alerts.append(f"[warning/slow] {msg}")
        print(f"    [ALERT/warning] {msg[:60]}")

    def _on_error(msg: str, tr):
        fired_alerts.append(f"[critical/error] {msg}")
        print(f"    [ALERT/critical] {msg[:60]}")

    alert_rules = [
        SimpleTaskAlertRule(
            name="slow_response",
            condition=lambda tr: tr.execution_time > 0.08,   # 80ms 이상 (시뮬레이션)
            handler=_on_slow,
            severity="warning",
            cooldown=2,
        ),
        SimpleTaskAlertRule(
            name="task_error",
            condition=lambda tr: tr.has_error,
            handler=_on_error,
            severity="critical",
            cooldown=1,
        ),
    ]

    monitor_b = PerformanceMonitor(output_dir=str(project_root / "results"))
    rng = random.Random(2025)
    _phase = {"current": "normal"}

    @agent_eval(
        monitor_b,
        task_type="qa",
        alert_rules=alert_rules,
        task_id_prefix="alert_b",
    )
    def alert_demo_agent(question: str, ground_truth: str = "") -> str:
        """정상/이상 응답을 시뮬레이션하는 데모 에이전트."""
        if _phase["current"] == "anomaly":
            time.sleep(0.1)   # 고지연 시뮬레이션 (100ms)
            if rng.random() > 0.4:
                raise RuntimeError("simulated_error")
        return "정상 응답"

    print(f"\n  [정상 구간 — 5개 태스크]")
    _phase["current"] = "normal"
    for i in range(5):
        alert_demo_agent("정상 질문", ground_truth="정상 응답")
    print(f"  알림 발생: {len(fired_alerts)}건 (예상: 0건)")

    normal_alerts = len(fired_alerts)
    print(f"\n  [이상 구간 — 8개 태스크 (고지연 + 오류)]")
    _phase["current"] = "anomaly"
    for i in range(8):
        try:
            alert_demo_agent("이상 질문", ground_truth="이상 응답")
        except RuntimeError:
            pass
    anomaly_alerts = len(fired_alerts) - normal_alerts
    print(f"  알림 발생: {anomaly_alerts}건")

    report = monitor_b.generate_report()
    saved = monitor_b.save_to_file("12_simple_task_alerting")
    print(f"\n  총 태스크: {report.total_tasks}개  |  저장: {saved}")

    # 검증
    checks = [
        ("정상 구간 알림 없음",   f"{normal_alerts}건",   normal_alerts == 0),
        ("이상 구간 알림 발생",   f"{anomaly_alerts}건",  anomaly_alerts > 0),
        ("fired_alerts 기록",    f"{len(fired_alerts)}건", len(fired_alerts) > 0),
    ]
    print(f"\n  {'─'*50}")
    for chk, actual, ok in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"  {chk:<30} {actual:<10} {mark}")
    print(f"  {'─'*50}")
    print()


if __name__ == "__main__":
    run_alerting_evaluation()
    run_simple_task_alerting()
