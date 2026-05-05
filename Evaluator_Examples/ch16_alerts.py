"""
ch16_alerts.py — 실시간 스트리밍 평가 + 알림 엔진
==========================================================
Book Chapter 16 — 알림시스템 운영

StreamingEvaluator의 슬라이딩 윈도우 메트릭과 AlertEngine의
규칙 기반 알림을 함께 시연한다.

  StreamingEvaluator:
    - 슬라이딩 윈도우 (1m / 5m / 1h) 지표
    - get_stats() — TCR, 평균 지연, p95, 오류율, 평균 토큰

  ImplicitFeedbackTracker:
    - 클릭·평점·재시도·저장·공유 신호 기록

  AlertEngine (고급):
    - AlertRule + 임계값 조건
    - SlackHandler / WebhookHandler (URL 미설정 시 Mock)
    - AlertHistory — 발생 이력 조회

  SimpleTaskAlertRule (경량):
    - StreamingEvaluator 없이 TaskResult 기반 즉시 알림
    - @agent_eval / @batch_eval / eval_context 에 alert_rules= 로 연결

  AlertRuleBuilder:
    - when_accuracy_below() / when_latency_above() / when_completion_below()

의존성:
    필수: pip install agent-evaluator          (numpy·pandas·python-dotenv 포함)
    선택: agent-eval monitor                   (Phoenix OTEL 시각화 — 없어도 실행됨)
    선택: SLACK_WEBHOOK_URL 환경변수             (슬랙 알림 — 미설정 시 Mock 핸들러로 대체)

실행:
    python Evaluator_Examples/ch16_alerts.py

결과:
    results/ch16_alerts.json
    → deprecated 전체 예제: Evaluator_Examples/.deprecated/05_streaming_alerts.py
"""

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor, create_taskresult, setup_otel,
    SimpleTaskAlertRule, ImplicitFeedbackTracker,
)
from agent_evaluator.decorators import agent_eval, batch_eval, eval_context
from agent_evaluator.streaming.evaluator import StreamingEvaluator

try:
    from agent_evaluator.alerts.engine import AlertEngine, AlertRule
    from agent_evaluator.alerts.handlers import SlackHandler, WebhookHandler
    _HAS_ALERTS = True
except ImportError:
    _HAS_ALERTS = False

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch16-alerts")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_anomaly_detection=True,     # ← 이상 감지 탭 활성화
    anomaly_baseline_window=30,        # 50건 중 앞 30건을 기준선으로
    anomaly_detection_window=10,       # 나머지 10건을 현재 상태로 비교
    enable_transparency=True,          # 투명성 탭: 메트릭 계산 Traces 자동 생성
)

# ===========================================================================
# 섹션 1: StreamingEvaluator — 슬라이딩 윈도우 평가
# ===========================================================================
print("\n=== 섹션 1: StreamingEvaluator 슬라이딩 윈도우 ===")

# StreamingEvaluator는 monitor를 필수 인자로 받음
streaming = StreamingEvaluator(monitor=monitor)

# 50건 시뮬레이션 (정상 40건 + 느린 응답 8건 + 오류 2건)
PATTERNS = (
    [(0.8, True,  random.uniform(0.5, 2.0), 200)] * 35  +   # 정상 구간 (기준선)
    [(0.6, True,  random.uniform(8.0, 15.0), 150)] * 10 +   # 느린 응답 구간 (이상 감지 대상)
    [(0.0, False, 0.1,                        0)]   * 5      # 오류 구간 (이상 감지 대상)
)
# shuffle 제거 — 정상→느림→오류 순서를 유지해야 이상 감지기가 추세를 탐지할 수 있음
# (AnomalyDetector는 최근 N건과 이전 N건의 통계를 비교하는 방식)

for i, (acc, success, lat, tok) in enumerate(PATTERNS):
    task_id = f"stream_{i:04d}"
    # StreamingEvaluator.record()는 task_id, success, execution_time, ... 개별 파라미터
    streaming.record(
        task_id=task_id,
        success=success,
        execution_time=round(lat, 3),
        tokens_used=tok,
        accuracy_score=acc,
        has_error=not success,
    )
    result = create_taskresult(
        task_id=task_id,
        question=f"스트리밍 태스크 {i:03d}",
        response="응답" if success else "",
        ground_truth="응답",
        execution_time=round(lat, 3),
        task_type="qa",
        tokens_used={"input": tok, "output": tok // 5, "total": tok + tok // 5} if tok else {"input": 0, "output": 0, "total": 0},
    )
    monitor.record_task(result)

for window in ["1m", "5m"]:
    stats = streaming.get_stats(window)
    # tcr, error_rate 는 0-100 스케일 (% 단위)
    print(f"  [{window}] count={stats.get('count', 0)}  "
          f"tcr={stats.get('tcr', 0):.1f}%  "
          f"p95={stats.get('p95_latency', 0):.2f}s  "
          f"err={stats.get('error_rate', 0):.1f}%")

# ===========================================================================
# 섹션 2: ImplicitFeedbackTracker — 사용자 암묵적 피드백
# ===========================================================================
print("\n=== 섹션 2: 암묵적 피드백 트래킹 ===")

# 지원 타입: thumbs_up, thumbs_down, save, share, regenerate, copy, correction, follow_up_depth, abandon
# monitor.record_implicit_feedback() → monitor 내부 feedback_tracker에 연결
# → save_to_file() 시 feedback 키에 집계 포함 → 대시보드 '사용자 반응' 탭 활성화
FEEDBACK_EVENTS = [
    ("stream_0001", "thumbs_up",      {"dwell_time": 8.5}),
    ("stream_0002", "save",           {"format": "pdf"}),
    ("stream_0003", "regenerate",     {"reason": "unsatisfied"}),
    ("stream_0004", "share",          {"channel": "slack"}),
    ("stream_0005", "thumbs_down",    {"reason": "wrong_answer"}),
    ("stream_0006", "copy",           {"section": "code"}),
    ("stream_0007", "abandon",        {"at_position": 0}),
]

for task_id, feedback_type, metadata in FEEDBACK_EVENTS:
    monitor.record_implicit_feedback(task_id=task_id, feedback_type=feedback_type, metadata=metadata)
    print(f"  [{feedback_type:<8s}] task={task_id}")

try:
    fb_stats = monitor.feedback_tracker.get_stats()
    print(f"  피드백 통계: total={fb_stats.get('total',0)}  positive={fb_stats.get('positive_count',0)}  negative={fb_stats.get('negative_count',0)}")
except Exception:
    print(f"  피드백 {len(FEEDBACK_EVENTS)}건 기록 완료")

# ===========================================================================
# 섹션 3: SimpleTaskAlertRule — @agent_eval 통합 경량 알림
# ===========================================================================
print("\n=== 섹션 3: SimpleTaskAlertRule (@agent_eval 통합) ===")

alert_log = []
_ALERTS_DIR = Path(_OUTPUT_DIR) / "alerts"
_ALERTS_DIR.mkdir(parents=True, exist_ok=True)
_TODAY_JSONL = _ALERTS_DIR / f"{datetime.now().date().isoformat()}.jsonl"

def _write_alert_jsonl(rule_name: str, severity: str, msg: str, task_id: str = "") -> None:
    """AlertEngine JSONL 포맷으로 results/alerts/{date}.jsonl 에 기록 → 대시보드 알림 탭 활성화."""
    event = {
        "triggered_at": datetime.now().isoformat(),
        "rule_name":    rule_name,
        "severity":     severity,
        "message":      msg,
        "task_id":      task_id,
    }
    with open(_TODAY_JSONL, "a", encoding="utf-8") as _f:
        _f.write(json.dumps(event, ensure_ascii=False) + "\n")

low_accuracy_rule = SimpleTaskAlertRule(
    name="low_accuracy",
    condition=lambda tr: tr.accuracy_score < 0.5,
    handler=lambda msg, tr: (
        alert_log.append(f"ACCURACY: {tr.task_id}={tr.accuracy_score:.2f}"),
        _write_alert_jsonl("low_accuracy", "warning", msg, tr.task_id),
    ),
    severity="warning",
    cooldown=0,
)

slow_response_rule = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 5.0,
    handler=lambda msg, tr: (
        alert_log.append(f"SLOW: {tr.task_id}={tr.execution_time:.1f}s"),
        _write_alert_jsonl("slow_response", "critical", msg, tr.task_id),
    ),
    severity="critical",
    cooldown=0,
)

@agent_eval(
    monitor, task_type="qa",
    task_id_prefix="alert_test",
    alert_rules=[low_accuracy_rule, slow_response_rule],
)
def monitored_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.messages.create(model="claude-haiku-4-5-20251001",
    #        messages=[{"role":"user","content":question}]).content[0].text
    # 의도적으로 낮은 품질 + 느린 응답 시뮬레이션
    if "느린" in question:
        time.sleep(0.01)  # 실제 환경 대체용 (시뮬레이션이므로 짧게)
    return "모름"  # 낮은 정확도

monitored_agent("정상 질문", ground_truth="정상 답변")
monitored_agent("엉뚱한 질문이라 정확도가 낮게 나올 것", ground_truth="전혀 다른 답변")

for log in alert_log:
    print(f"  알림 발생: {log}")

# dry_run — 핸들러 실행 없이 조건만 검증
from agent_evaluator import create_taskresult as _ctr
test_result = _ctr(
    task_id="dry_run_test", question="테스트", response="낮은 품질",
    ground_truth="전혀 다른 것", execution_time=6.0, task_type="qa", tokens_used=50,
)
triggered = slow_response_rule.dry_run(test_result)
print(f"  dry_run(slow_response, lat=6.0s): triggered={triggered}")

# ===========================================================================
# 섹션 4: AlertRuleBuilder (팩토리 패턴)
# ===========================================================================
print("\n=== 섹션 4: AlertRuleBuilder 팩토리 ===")

try:
    from agent_evaluator.decorators import AlertRuleBuilder

    builder_rules = [
        AlertRuleBuilder.when_accuracy_below(
            threshold=0.6,
            handler=lambda msg, tr: print(f"  [Builder-Accuracy] {msg[:60]}"),
        ),
        AlertRuleBuilder.when_latency_above(
            threshold_seconds=10.0,
            handler=lambda msg, tr: print(f"  [Builder-Latency] {msg[:60]}"),
        ),
        AlertRuleBuilder.when_completion_below(
            threshold=0.8,
            handler=lambda msg, tr: print(f"  [Builder-TCR] {msg[:60]}"),
        ),
    ]
    print(f"  AlertRuleBuilder: {len(builder_rules)}개 규칙 생성")

    @batch_eval(
        monitor, task_type="qa",
        task_id_prefix="builder_test",
        return_format="list",
        alert_rules=builder_rules,
    )
    def builder_batch(questions: list, ground_truths: list = None) -> list:
        return ["잘 모르겠습니다" for _ in questions]   # 의도적 낮은 정확도

    builder_batch(
        questions=["Q1", "Q2", "Q3"],
        ground_truths=["완전히 다른 답 A", "완전히 다른 답 B", "완전히 다른 답 C"],
    )

except (ImportError, AttributeError):
    print("  AlertRuleBuilder 미지원 버전 — 건너뜀")

# ===========================================================================
# 섹션 5: AlertEngine + AlertRule (고급)
# ===========================================================================
print("\n=== 섹션 5: AlertEngine + AlertRule (고급) ===")

if _HAS_ALERTS:
    # 핸들러: URL 없으면 Mock 출력
    SLACK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
    WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")

    if SLACK_URL:
        slack_handler = SlackHandler(webhook_url=SLACK_URL)
    else:
        class MockSlack:
            def handle(self, alert):
                print(f"  [Mock Slack] {alert.get('message', '')[:60]}")
        slack_handler = MockSlack()

    if WEBHOOK_URL:
        webhook_handler = WebhookHandler(webhook_url=WEBHOOK_URL)
    else:
        class MockWebhook:
            def handle(self, alert):
                print(f"  [Mock Webhook] {alert.get('message', '')[:60]}")
        webhook_handler = MockWebhook()

    try:
        engine = AlertEngine()
        # AlertRule.condition: StreamingEvaluator 인스턴스를 인자로 받아 bool 반환
        engine.add_rule(AlertRule(
            name="error_rate_spike",
            condition=lambda ev: ev.get_stats("5m").get("error_rate", 0) > 5.0,
            handler=slack_handler,
            severity="critical",
            cooldown=60,
        ))
        engine.add_rule(AlertRule(
            name="p95_latency_high",
            condition=lambda ev: ev.get_stats("5m").get("p95_latency", 0) > 5.0,
            handler=webhook_handler,
            severity="warning",
            cooldown=30,
        ))

        # AlertEngine.evaluate()는 StreamingEvaluator 인스턴스를 인자로 받음
        engine.evaluate(streaming)

        print(f"  AlertEngine 2개 규칙 평가 완료")
        try:
            history = engine.history.get_history()
            print(f"  AlertHistory: {len(history)}건")
        except Exception:
            pass

    except Exception as e:
        print(f"  AlertEngine 초기화 오류: {e}")
else:
    print("  AlertEngine 미설치 — 건너뜀")

# ===========================================================================
# 섹션 6: eval_context + alert_rules
# ===========================================================================
print("\n=== 섹션 6: eval_context + alert_rules ===")

ctx_alert = SimpleTaskAlertRule(
    name="ctx_low_score",
    condition=lambda tr: tr.accuracy_score < 0.4,
    handler=lambda msg, tr: print(f"  [ctx ALERT] acc={tr.accuracy_score:.2f}"),
    severity="warning", cooldown=0,
)

with eval_context(
    monitor, task_type="qa",
    question="컨텍스트 기반 평가",
    ground_truth="전혀 다른 정답",
    alert_rules=[ctx_alert],
) as ctx:
    ctx.response = "낮은 품질의 응답"

print("  eval_context + alert_rules 완료")

# ===========================================================================
# 최종 리포트 & 저장
# ===========================================================================
print("\n=== 최종 리포트 ===")

report = monitor.generate_report().to_dict()
total  = report.get("total_tasks", 0)
tcr    = report.get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0) / 100
print(f"  PerformanceMonitor 기록: {total}건  TCR: {tcr:.1%}")
print(f"  알림 발생: {len(alert_log)}건")

# streaming_data 스냅샷 → monitor._streaming_snapshot 에 저장 후 save_to_file()에 포함
streaming._flush()   # ← 이 호출이 있어야 대시보드 '실시간' 탭에 데이터 표시됨

monitor.save_to_file("ch16_alerts")
print("\n결과 저장 완료: results/ch16_alerts.json")

# 저장 확인
saved = json.loads(Path(_OUTPUT_DIR, "ch16_alerts.json").read_text())
has_streaming = bool(saved.get("streaming_data"))
has_feedback  = saved.get("feedback", {}).get("total", 0) > 0
has_anomaly   = bool(saved.get("anomaly_data"))
has_alerts    = _TODAY_JSONL.exists() and _TODAY_JSONL.stat().st_size > 0
print(f"\n대시보드 탭 데이터 확인:")
print(f"  실시간(streaming_data) : {'✅' if has_streaming else '❌'}")
print(f"  알림(alerts JSONL)     : {'✅' if has_alerts    else '❌'}  → {_TODAY_JSONL.name}")
print(f"  사용자 반응(feedback)  : {'✅' if has_feedback  else '❌'}  total={saved.get('feedback',{}).get('total',0)}")
print(f"  이상 감지(anomaly_data): {'✅' if has_anomaly   else '❌'}")
