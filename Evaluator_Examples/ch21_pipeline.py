"""
ch21_pipeline.py — 종합 실무 파이프라인 (개발 → CI → 운영 → 개선 사이클)
====================================================================
Book Chapter 21 — 지속 평가·자기개선 파이프라인

개발·CI·프로덕션·주간 리뷰 4단계를 단일 파일에서 시연한다.
각 단계는 독립적으로 실행 가능하며, 전체를 순서대로 실행하면
완전한 Harness Engineering 파이프라인을 경험할 수 있다.

  1단계 — 개발: QuickEval + Layer 1 기초 검증 (ch01/ch02 대응)
  2단계 — CI: Harness Gate 판정 + 추세 분석 (ch03/ch18 대응)
  3단계 — 프로덕션: 데코레이터 + 알림 + 이상 탐지 (ch12/ch16/ch10 대응)
  4단계 — 개선: 골든셋 추출 + 회귀 방지 (ch11/ch17 대응)

실행:
  python Evaluator_Examples/ch21_pipeline.py
  agent-eval dashboard results/
"""

from __future__ import annotations

import json
import os
import random
import socket
import subprocess
import sys
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    QuickEval,
    HarnessEvaluationGate,
    create_taskresult,
    evaluation_session,
    AnomalyDetector,
    CostTracker,
    SimpleTaskAlertRule,
    InstructionConfig,
    ScopeConfig,
    SLAConfig,
    ComplianceConfig,
    ExplainabilityConfig,
    FaultToleranceConfig,
    ThreatSeverityConfig,
    # 단일 커버리지 Config — 종합 파이프라인에 통합
    SubtaskConfig,
    ThreatResponseConfig,
    ErrorDiagnosisConfig,
    ConflictResolutionConfig,
)
from agent_evaluator import agent_eval, EvalMetadata
from agent_evaluator.datasets.builder import GoldenSetBuilder
from agent_evaluator.config import load_env

load_env()

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")
Path(_OUTPUT_DIR).mkdir(exist_ok=True)

_PIPELINE_RESULTS: dict = {}  # 단계별 결과 집계

# ════════════════════════════════════════════════════════════
# 1단계 — 개발: QuickEval + Layer 1 기초 검증
# ════════════════════════════════════════════════════════════
print("=" * 60)
print("1단계 — 개발: QuickEval + Layer 1 기초 검증")
print("=" * 60)

DEV_CASES = [
    ("한국의 수도는?",            "서울"),
    ("Python GIL이란?",          "전역 인터프리터 잠금"),
    ("REST vs GraphQL 차이?",    "REST는 엔드포인트 기반, GraphQL은 단일 엔드포인트"),
    ("CI/CD란?",                 "지속적 통합·배포 파이프라인"),
    ("Docker 컨테이너란?",        "격리된 실행 환경 단위"),
    ("마이크로서비스 장점?",       "독립 배포·확장 가능성"),
    ("RAG란?",                   "검색 증강 생성"),
    ("LLM Judge란?",             "LLM을 활용한 자동 품질 채점"),
]

eval_dev = QuickEval(_OUTPUT_DIR, auto_save=False)

@eval_dev.qa
def dev_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    answers = {
        "수도": "서울입니다",
        "GIL": "Python의 전역 인터프리터 잠금(GIL)은 하나의 스레드만 Python 코드를 실행하게 합니다",
        "GraphQL": "REST는 여러 엔드포인트를 사용하고, GraphQL은 단일 엔드포인트로 유연한 쿼리를 제공합니다",
        "CI/CD": "CI는 지속적 통합, CD는 지속적 배포를 의미하는 소프트웨어 개발 방법론입니다",
        "Docker": "Docker 컨테이너는 애플리케이션과 의존성을 격리된 환경에 패키징합니다",
        "마이크로서비스": "마이크로서비스는 서비스별 독립 배포와 확장이 가능한 아키텍처입니다",
        "RAG": "RAG(Retrieval-Augmented Generation)는 검색으로 컨텍스트를 보강하는 생성 방식입니다",
        "Judge": "LLM Judge는 LLM이 다른 LLM의 응답 품질을 자동으로 채점하는 방식입니다",
    }
    for key, ans in answers.items():
        if key in question:
            return ans
    return f"답변: {question}"

for q, gt in DEV_CASES:
    dev_agent(q, ground_truth=gt)

dev_summary = eval_dev.summary()
eval_dev.save("ch21_pipeline_dev")
_PIPELINE_RESULTS["dev"] = dev_summary

print(f"  TCR:      {dev_summary['tcr']:.1f}%")
print(f"  정확도:    {dev_summary['accuracy']:.1f}%")
print(f"  p95 지연:  {dev_summary['p95_latency']:.3f}s")
print(f"  → results/ch21_pipeline_dev.json 저장")

# ════════════════════════════════════════════════════════════
# 2단계 — CI: Harness Gate 판정 + 배포 검증
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("2단계 — CI: Harness Gate 판정")
print("=" * 60)

monitor_ci = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_security_metrics=True,
    use_korean_tokenizer=True,
)

@agent_eval(
    monitor_ci,
    task_type="qa",
    task_id_prefix="ci_gate",
    instructions=InstructionConfig(
        required_keywords=["답변", "출처"],
        fail_on_violation=False,
    ),
    scope=ScopeConfig(
        allowed_tools=["search", "analyze"],
        forbidden_tools=["delete", "admin"],
    ),
    sla=SLAConfig(p95_ms=3000),
    fault_tolerance=FaultToleranceConfig(check_fallback_attempts=True, partial_success_threshold=0.5),
    compliance=ComplianceConfig(pii_categories=["email", "phone"]),
    explainability=ExplainabilityConfig(
        require_reasoning=True,
        min_reasoning_length=15,
        reasoning_markers=["왜냐하면", "따라서"],
    ),
    # 단일 커버리지 Config 통합 — 파이프라인 전체 Gate A/E/F/G 커버리지 확대
    subtask_tracking=SubtaskConfig(
        expected_subtasks=["답변", "출처"],
        completion_markers=["완료", "처리", "답변"],
        min_completion_rate=0.5,
    ),
    threat_response=ThreatResponseConfig(
        isolation_markers=["차단", "거부", "blocked"],
        score_clean_tasks=True,
    ),
    error_diagnosis=ErrorDiagnosisConfig(
        only_on_failure=True,
        root_cause_markers=["왜냐하면", "때문에", "원인"],
        suggestion_markers=["제안", "시도", "대신"],
    ),
    conflict_resolution=ConflictResolutionConfig(
        check_resolution_quality=True,
        resolution_markers=["합의", "결정", "resolved"],
    ),
)
def ci_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"답변: {question}에 대한 결과입니다 | 출처: 내부 DB | 왜냐하면 검증된 데이터를 참조했습니다"

for q, gt in DEV_CASES:
    ci_agent(q, ground_truth=gt)

monitor_ci.save_to_file("ch21_pipeline_ci")
report_ci = monitor_ci.generate_report()

try:
    gate = HarnessEvaluationGate(report_ci, min_group_score=0.6, fail_on_warn=False)
    gate.enforce()
    print("  ✅ Harness Gate PASS — 배포 승인")
    _PIPELINE_RESULTS["ci_gate"] = "PASS"
except SystemExit:
    print("  ❌ Harness Gate FAIL — 배포 차단 (예제용 — 실제 배포라면 여기서 중단)")
    _PIPELINE_RESULTS["ci_gate"] = "FAIL"

# CLI agent-eval gate 연동 (결과 파일 있으면 검증)
ci_json = Path(_OUTPUT_DIR) / "ch21_pipeline_ci.json"
if ci_json.exists():
    cli_result = subprocess.run(
        ["agent-eval", "gate", str(ci_json), "--tcr", "40", "--accuracy", "50"],
        capture_output=True, text=True,
    )
    print(f"  agent-eval gate: {'통과' if cli_result.returncode == 0 else '실패'} (exit {cli_result.returncode})")

# ════════════════════════════════════════════════════════════
# 3단계 — 프로덕션: 데코레이터 + 알림 + 이상 탐지
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("3단계 — 프로덕션: 알림 + 이상 탐지")
print("=" * 60)

monitor_prod = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_security_metrics=True,
    auto_save=True,
    auto_save_interval=10,
    use_korean_tokenizer=True,
)

anomaly_detector = AnomalyDetector(baseline_window=20, detection_window=5)
cost_tracker = CostTracker(budget_per_day=10.0)

alert_log: list[str] = []

slow_alert = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 3.0,
    handler=lambda msg, tr: alert_log.append(f"SLOW:{tr.task_id}:{tr.execution_time:.2f}s"),
    severity="warning",
    cooldown=0,
)
accuracy_alert = SimpleTaskAlertRule(
    name="low_accuracy",
    condition=lambda tr: tr.accuracy_score < 0.4,
    handler=lambda msg, tr: alert_log.append(f"LOW_ACC:{tr.task_id}:{tr.accuracy_score:.2f}"),
    severity="warning",
    cooldown=0,
)

@agent_eval(
    monitor_prod,
    task_type="information_retrieval",
    task_id_prefix="prod",
    alert_rules=[slow_alert, accuracy_alert],
    instructions=InstructionConfig(required_keywords=["답변"], fail_on_violation=False),
    sla=SLAConfig(p95_ms=3000),
)
def production_agent(question: str, ground_truth: str = "") -> tuple:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    response = f"답변: {question} | 출처: 프로덕션 DB"
    return response, EvalMetadata(
        tool_calls=[
            {"tool_name": "retriever", "success": True, "duration": 0.3},
            {"tool_name": "llm",       "success": True, "duration": 0.5},
        ],
        expected_tools=["retriever", "llm"],
    )

PROD_CASES = DEV_CASES + [
    ("시스템 가용성은?",      "99.9%"),
    ("오늘 트래픽은?",        "10만 req/s"),
    ("에러율은?",             "0.1%"),
    ("p95 응답시간은?",       "1.2s"),
    ("배포 이력은?",          "3월 15일 v2.1.0"),
    ("비용 현황은?",          "$120/월"),
]

random.seed(7)
for i, (q, gt) in enumerate(PROD_CASES):
    production_agent(q, ground_truth=gt)

    # 데코레이터 외 추가 태스크 직접 기록 — 이상 탐지 + 비용 추적
    result = create_taskresult(
        task_id=f"prod_anomaly_{i:03d}",
        question=q,
        response=f"답변: {q}",
        ground_truth=gt,
        execution_time=round(random.gauss(0.8, 0.2) if i < 12 else random.gauss(4.0, 0.5), 3),
        task_type="qa",
        tokens_used={"input": 80, "output": 20, "total": 100},
    
        use_korean_tokenizer=True,
    )
    monitor_prod.record_task(result)
    cost_tracker.record(
        provider="openai", model="gpt-5-nano",
        cost_usd=result.tokens_used.get("total", 100) * 0.000001,
        input_tokens=result.tokens_used.get("input", 80),
        output_tokens=result.tokens_used.get("output", 20),
    )

monitor_prod.save_to_file("ch21_pipeline_prod")

# 루프 종료 후 monitor 전체에 대해 이상 탐지 실행
anomaly_events = anomaly_detector.scan(monitor_prod)
for event in anomaly_events:
    print(f"  ⚠️  이상 탐지: [{event.severity}] {event.type} — {event.detail[:60]}")

_today_cost = cost_tracker.get_today_cost()
_PIPELINE_RESULTS["prod_alerts"] = len(alert_log)
_PIPELINE_RESULTS["prod_cost"] = round(_today_cost, 4)

print(f"  발화 알림: {len(alert_log)}건 | {alert_log[:3]}")
print(f"  이상 탐지: {len(anomaly_events)}건")
print(f"  오늘 누적 비용: ${_today_cost:.4f} / $10.00 예산")
print(f"  → results/ch21_pipeline_prod.json 저장")

# ════════════════════════════════════════════════════════════
# 4단계 — 개선: 골든셋 추출 + 추세 분석 + 회귀 방지
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("4단계 — 개선: 골든셋 추출 + 추세 분석")
print("=" * 60)

# 골든 데이터셋 자동 추출
golden_dir = _PROJECT_ROOT / "data" / "golden_datasets"
builder = GoldenSetBuilder(source_dir=_OUTPUT_DIR, output_dir=str(golden_dir))

try:
    golden_result = builder.extract(strategies=["high_value", "failure_cases"], max_cases=20)
    if golden_result:
        # 추출 결과가 있을 때만 필요 시 디렉토리 생성 (실제 저장 로직이 추가될 경우 대비)
        # 현재는 개수만 출력하므로 실제 mkdir은 생략 가능하나, 일관성을 위해 유지하거나 정리
        print(f"  골든셋 추출: {len(golden_result)}개 케이스")
        _PIPELINE_RESULTS["golden_cases"] = len(golden_result)
    else:
        print("  골든셋: 임계점 미달 케이스 없음")
        _PIPELINE_RESULTS["golden_cases"] = 0
except Exception as e:
    print(f"  골든셋 추출 오류 (예제용): {e}")
    _PIPELINE_RESULTS["golden_cases"] = 0

# CLI 추세 분석 (결과 파일 2개 이상 있을 때)
json_files = sorted(Path(_OUTPUT_DIR).glob("ch21_pipeline_*.json"))
if len(json_files) >= 2:
    trend_result = subprocess.run(
        ["agent-eval", "trend", _OUTPUT_DIR, "--window", "5", "--output-json",
         f"{_OUTPUT_DIR}ch21_trend.json"],
        capture_output=True, text=True,
    )
    if trend_result.returncode == 0:
        print("  ✅ 추세 분석 완료 → results/ch21_trend.json")
        trend_json = Path(_OUTPUT_DIR) / "ch21_trend.json"
        if trend_json.exists():
            trend_data = json.loads(trend_json.read_text())
            tcr_trend = trend_data.get("trends", {}).get("tcr", {}).get("direction", "N/A")
            print(f"  TCR 추세: {tcr_trend}")
    else:
        print(f"  추세 분석: {trend_result.stderr[:80]}")
else:
    print(f"  추세 분석: 결과 파일 {len(json_files)}개 — 2개 이상 필요")

# 자기 개선 루프 요약
print("\n" + "=" * 60)
print("파이프라인 종합 결과")
print("=" * 60)

print(f"""
  1단계(개발)  TCR={_PIPELINE_RESULTS['dev']['tcr']:.1f}%  \
정확도={_PIPELINE_RESULTS['dev']['accuracy']:.1f}%
  2단계(CI)    Gate={_PIPELINE_RESULTS['ci_gate']}
  3단계(운영)  알림={_PIPELINE_RESULTS['prod_alerts']}건  \
비용=${_PIPELINE_RESULTS['prod_cost']:.4f}
  4단계(개선)  골든셋={_PIPELINE_RESULTS['golden_cases']}건

  생성된 결과 파일:""")

for f in sorted(Path(_OUTPUT_DIR).glob("ch21_pipeline_*.json")):
    print(f"  ✅ {f}")

print("""
  대시보드 기동:
    agent-eval dashboard results/
    http://localhost:8765
""")
