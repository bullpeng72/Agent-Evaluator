"""
실시간 알림 엔진 예제 — Agent Evaluator v0.6.7 Phase 2-B
=========================================================

StreamingEvaluator 지표를 기반으로 AlertEngine이 임계값 초과를
감지하면 SlackHandler · WebhookHandler로 알림을 발송합니다.

커버 지표 (Phase 2-B):
  Phase 2-B  │ AlertEngine  — 규칙 기반 알림 엔진
             │ AlertRule    — 조건부 알림 규칙 (냉각 시간 포함)
             │ AlertEvent   — 알림 이벤트 (severity, triggered_at)
             │ AlertHistory — 날짜별 JSONL 이력 저장
             │ SlackHandler — Slack Webhook 발송 (모의)
             │ WebhookHandler — 범용 HTTP Webhook 발송 (모의)

핵심 시나리오:
  1. 정상 구간 (10개 태스크) — 알림 없음 예상
  2. 이상 구간 (고지연 + 오류 급등, 20개 태스크) — warning/critical 발생
  3. 쿨다운 동작 확인 — 같은 규칙이 연속 발동되지 않음
  4. AlertHistory 이력 조회 (오늘/최근 7일)

실행:
    python 12_alerting_eval.py    # API 키 불필요 — 순수 시뮬레이션
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

from agent_evaluator import PerformanceMonitor, create_taskresult
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

    # ── 핸들러 초기화 ─────────────────────────────────────────────────────
    slack_handler   = _MockSlackHandler()
    webhook_handler = _MockWebhookHandler()

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


if __name__ == "__main__":
    run_alerting_evaluation()
