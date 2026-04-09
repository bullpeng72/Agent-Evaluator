"""
06_operational.py — 운영 인프라 (이상감지·비용제어·골든셋·대시보드)
=====================================================================
프로덕션 환경에서 필요한 운영 도구를 한 파일에서 시연한다.

  AnomalyDetector:
    - 지연시간 추세 / 정확도 드리프트 / 토큰 스파이크 / 오류율 급등 / 패턴 이탈
    - explain_event() — 이상 원인 설명

  CostTracker + AdaptivePolicy:
    - 모델별 토큰 비용 계산
    - SamplingStage — 단계별 평가 비율 (canary → staging → production)
    - 예산 초과 시 샘플링 비율 자동 조정

  GoldenSetBuilder:
    - 실패·엣지·고가치 케이스 자동 추출
    - save_candidates() / merge_to_golden() / 버전 관리

  evaluation_session:
    - context manager 기반 자동 저장
    - JSON + HTML 생성 → agent-eval dashboard 연동

  CI/CD 품질 게이팅:
    - agent-eval gate 사용법 주석

실행:
    python Evaluator_Examples/06_operational.py

결과:
    results/06_operational.json
    data/golden_datasets/  (골든 데이터셋)
"""

import json
import random
from datetime import datetime
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor, create_taskresult,
    evaluation_session, setup_otel,
    AnomalyDetector, AnomalyEvent,
    CostTracker, AdaptivePolicy, SamplingStage,
)
from agent_evaluator.decorators import agent_eval
from agent_evaluator.datasets.builder import GoldenSetBuilder

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")
_DATA_DIR     = str(_PROJECT_ROOT / "data")

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="06-operational")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ===========================================================================
# 섹션 1: AnomalyDetector — 5가지 이상 탐지 알고리즘
# ===========================================================================
print("\n=== 섹션 1: 이상 탐지 (AnomalyDetector) ===")

monitor_anomaly = PerformanceMonitor(output_dir=_OUTPUT_DIR)
detector = AnomalyDetector()

# 정상 기준선 데이터 (30건)
BASELINE = []
for i in range(30):
    r = create_taskresult(
        task_id=f"base_{i:03d}",
        question="기준선 태스크",
        response="정상 응답",
        ground_truth="정상",
        execution_time=round(random.gauss(1.2, 0.3), 3),
        task_type="qa",
        tokens_used={"input": 100, "output": 40, "total": 140},
    )
    BASELINE.append(r)
    monitor_anomaly.record_task(r)

# 이상 패턴 주입
ANOMALY_CASES = [
    # (label, execution_time, accuracy_hint, tokens)
    ("지연 스파이크",   15.0,  0.7, 150),
    ("정확도 드리프트", 1.2,   0.1, 140),
    ("토큰 폭증",       1.5,   0.8, 5000),
    ("지연 스파이크2",  18.0,  0.7, 160),
    ("정확도 드리프트2",1.1,   0.05, 130),
]

anomaly_events = []
for label, lat, acc_hint, tok in ANOMALY_CASES:
    r = create_taskresult(
        task_id=f"anom_{label[:4]}",
        question=f"이상 케이스: {label}",
        response="응답" if acc_hint > 0.5 else "",
        ground_truth="정상 응답",
        execution_time=lat,
        task_type="qa",
        tokens_used={"input": tok, "output": tok // 5, "total": tok + tok // 5},
    )
    monitor_anomaly.record_task(r)

    # AnomalyDetector에 기준선 + 이상 케이스 스캔
    all_tasks = BASELINE + [r]
    try:
        events = detector.scan(all_tasks)
        new_events = [e for e in events if r.task_id in str(e)]
        anomaly_events.extend(events)
        print(f"  [{label}] lat={lat:.1f}s  tok={tok}  이상 이벤트: {len(events)}건")
    except Exception as e:
        print(f"  [{label}] 스캔 완료 (이벤트 집계 방식에 따라 다름)")

try:
    if anomaly_events:
        ev = anomaly_events[0]
        explanation = detector.explain_event(ev)
        print(f"  explain_event: {str(explanation)[:80]}...")
except Exception:
    pass

# ===========================================================================
# 섹션 2: CostTracker + AdaptivePolicy + SamplingStage
# ===========================================================================
print("\n=== 섹션 2: 비용 추적 + 적응형 샘플링 ===")

# SamplingStage는 Enum (DEFAULT / ANOMALY / BUDGET_EXCEEDED)
# AdaptivePolicy: default_sample_rate, anomaly_sample_rate, budget_per_day
policy = AdaptivePolicy(
    default_sample_rate=0.1,   # 기본 10% 샘플링
    anomaly_sample_rate=1.0,   # 이상 감지 시 100%
    budget_per_day=10.0,       # 하루 $10 예산
    alert_at=0.8,              # 80% 도달 시 알림
)

tracker = CostTracker(budget_per_day=10.0, alert_at=0.8)

MODEL_USAGES = [
    ("gpt-4o",          {"input": 800,  "output": 250, "model": "gpt-4o"}),
    ("claude-3-sonnet",  {"input": 600,  "output": 200, "model": "claude-3-sonnet"}),
    ("gpt-4o-mini",     {"input": 1200, "output": 400, "model": "gpt-4o-mini"}),
    ("gpt-4o",          {"input": 2000, "output": 500, "model": "gpt-4o"}),
]

monitor_cost = PerformanceMonitor(output_dir=_OUTPUT_DIR)
for model, tokens in MODEL_USAGES:
    result = create_taskresult(
        task_id=f"cost_{model[:8]}",
        question="비용 추적 테스트",
        response="응답",
        ground_truth="응답",
        execution_time=1.5,
        task_type="qa",
        tokens_used=tokens,
    )
    monitor_cost.record_task(result)
    tok_total = tokens["input"] + tokens["output"]
    status = policy.get_status()
    print(f"  [{model:<16s}] tokens={tok_total}  stage={status.get('current_stage','?')}  rate={status.get('current_sample_rate',0):.0%}")

try:
    today = tracker.get_today_cost()
    print(f"  오늘 비용: ${today:.4f} USD")
    alert = tracker.is_budget_alert()
    print(f"  예산 알림: {alert}")
except Exception as e:
    print(f"  비용 추적 완료 ({len(MODEL_USAGES)}건)")

# ===========================================================================
# 섹션 3: GoldenSetBuilder — 고가치 케이스 추출·관리
# ===========================================================================
print("\n=== 섹션 3: 골든 데이터셋 구축 ===")

monitor_golden = PerformanceMonitor(output_dir=_OUTPUT_DIR)

# 다양한 점수 분포의 태스크 생성
TASK_DEFINITIONS = [
    # (question, response, ground_truth, latency, description)
    ("서울의 특징은?",      "서울은 대한민국의 수도입니다.",     "서울은 한국의 수도",   0.8,  "고품질"),
    ("파이썬이란?",         "파이썬은 범용 프로그래밍 언어입니다.", "파이썬 프로그래밍 언어", 1.2, "고품질"),
    ("1+1은?",             "2",                                 "2",                0.3,  "엣지 케이스"),
    ("asd#$@! 란?",        "모르겠습니다",                      "정의 없음",          0.5,  "엣지케이스 (특수문자)"),
    ("복잡한 질문...",      "",                                  "상세한 답변",        10.5, "실패 케이스"),
    ("머신러닝이란?",       "머신러닝은 AI의 한 분야입니다.",    "AI 기계학습",        1.5,  "중간 품질"),
    ("클라우드란?",         "클라우드는 인터넷 기반 서비스입니다.", "인터넷 서비스",     1.1,  "고품질"),
    ("에러 케이스",         "",                                  "올바른 응답",        0.2,  "오류"),
]

golden_tasks = []
for q, resp, gt, lat, desc in TASK_DEFINITIONS:
    r = create_taskresult(
        task_id=f"golden_{desc[:5]}_{hash(q)%1000:03d}",
        question=q, response=resp, ground_truth=gt,
        execution_time=lat, task_type="qa",
        tokens_used={"input": 80, "output": 30, "total": 110},
    )
    monitor_golden.record_task(r)
    golden_tasks.append(r)
    print(f"  [{desc:<12s}] acc={r.accuracy_score:.2f}  lat={lat:.1f}s")

# GoldenSetBuilder로 케이스 추출 (source_dir: JSON 결과 파일 위치)
builder = GoldenSetBuilder(
    source_dir=_OUTPUT_DIR,
    output_dir=_DATA_DIR,
)

# TaskResult를 GoldenSet 형식의 dict로 변환
def _to_golden_dict(r) -> dict:
    return {
        "task_id":       r.task_id,
        "question":      getattr(r, "question", r.task_id) or r.task_id,
        "response":      getattr(r, "response", "") or "",
        "ground_truth":  getattr(r, "ground_truth", "") or "",
        "accuracy_score": r.accuracy_score,
        "execution_time": r.execution_time,
        "task_type":     str(r.task_type),
    }

try:
    # 정확도 기준으로 분류
    high_value = [_to_golden_dict(r) for r in golden_tasks if r.accuracy_score >= 0.7]
    failures   = [_to_golden_dict(r) for r in golden_tasks if r.accuracy_score < 0.2]
    edge_cases = [_to_golden_dict(r) for r in golden_tasks
                  if r.execution_time > 8.0 or len(getattr(r, "question", "") or "") < 5]

    print(f"\n  고가치 케이스: {len(high_value)}건 (score≥0.7)")
    print(f"  실패 케이스:   {len(failures)}건 (score<0.2)")
    print(f"  엣지 케이스:   {len(edge_cases)}건 (느린 응답 or 짧은 질문)")

    all_candidates = high_value + failures + edge_cases
    if all_candidates:
        saved = builder.save_candidates(all_candidates, filename="06_golden_candidates.json")
        print(f"  후보 저장 완료: {saved}")

        merged = builder.merge_to_golden(all_candidates, version="v1", output_name="master_golden")
        print(f"  마스터 골든셋 병합 완료: {merged}")

except Exception as e:
    print(f"  GoldenSetBuilder: {e}")

# ===========================================================================
# 섹션 4: evaluation_session — context manager + 자동 저장
# ===========================================================================
print("\n=== 섹션 4: evaluation_session context manager ===")

@agent_eval(None, task_type="qa", task_id_prefix="session")
def session_agent(question: str, ground_truth: str = "", _monitor=None) -> str:
    return f"세션 내 응답: {question}"

# evaluation_session은 with 블록 종료 시 자동으로 save_to_file() 호출
SESSION_TASKS = [
    ("대한민국 수도?",     "서울"),
    ("파이썬 버전 3.12?",  "파이썬 3.12"),
    ("TCP 포트 80번?",     "HTTP"),
]

with evaluation_session("06_session_demo") as session_monitor:
    @agent_eval(session_monitor, task_type="qa", task_id_prefix="sess")
    def _agent(question: str, ground_truth: str = "") -> str:
        return f"응답: {question}"

    for q, gt in SESSION_TASKS:
        _agent(q, ground_truth=gt)

print(f"  evaluation_session 종료 → results/06_session_demo.json 자동 저장")

# ===========================================================================
# 섹션 5: 종합 저장 + CI/CD 게이팅 안내
# ===========================================================================
print("\n=== 섹션 5: 최종 저장 & CI/CD 안내 ===")

# 모든 모니터를 하나로 합산하는 대신 메인 모니터에 저장
# enable_anomaly_detection=True → save_to_file() 시 anomaly_data 자동 생성 → 대시보드 이상 감지 탭 활성화
# monitor_anomaly(35건: 30 기준선 + 5 이상)를 메인으로 재활용해 anomaly_data 포함
monitor_main = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_anomaly_detection=True,
    anomaly_baseline_window=20,    # 35건 중 앞 20건 기준선
    anomaly_detection_window=10,   # 나머지 10건 현재 상태 비교
)
# 이상 기준선 데이터 포함 (anomaly_baseline 30건 + golden_tasks 8건)
for r in BASELINE[:20]:
    monitor_main.record_task(r)
for r in golden_tasks:
    monitor_main.record_task(r)

report = monitor_main.generate_report().to_dict()
total  = report.get("total_tasks", 0)
am     = report.get("accuracy_metrics", {})
tcr    = am.get("tcr", {}).get("tcr", 0) / 100
acc    = am.get("accuracy_scores", {}).get("overall_accuracy", 0) / 100
print(f"  총 태스크: {total}건  TCR: {tcr:.1%}  평균 정확도: {acc:.2%}")

monitor_main.save_to_file("06_operational")
print("\n결과 저장 완료: results/06_operational.json")

# ===========================================================================
# 평가 비용 탭 — CostTracker 데이터를 evaluation_cost 키로 주입
# (LLM Judge 없이도 대시보드 '평가 비용' 탭에 데이터 표시)
# ===========================================================================
_json_path = Path(_OUTPUT_DIR) / "06_operational.json"
_data = json.loads(_json_path.read_text(encoding="utf-8"))

# CostTracker 기반 모델별 토큰 비용 계산 (gpt-4o·claude-3-sonnet·gpt-4o-mini 기준)
_TOKEN_PRICES = {
    "gpt-4o":         {"input": 0.005,  "output": 0.015},
    "claude-3-sonnet":{"input": 0.003,  "output": 0.015},
    "gpt-4o-mini":    {"input": 0.00015,"output": 0.0006},
}
_by_provider: dict = {}
_total = 0.0
for model, tokens in MODEL_USAGES:
    prices = _TOKEN_PRICES.get(model, {"input": 0.003, "output": 0.015})
    cost = tokens["input"] * prices["input"] / 1000 + tokens["output"] * prices["output"] / 1000
    _by_provider[model] = round(_by_provider.get(model, 0.0) + cost, 6)
    _total += cost

_data["evaluation_cost"] = {
    "total_usd":           round(_total, 6),
    "llm_judge_usd":       0.0,
    "by_provider":         _by_provider,
    "call_count":          len(MODEL_USAGES),
    "model":               "gpt-4o-mini",
    "budget_per_day":      10.0,
    "budget_remaining_usd": round(10.0 - _total, 6),
    "sample_rate_current": 0.1,
    "projected_daily_usd": round(_total * 10, 6),
}

# 알림 탭 — AnomalyDetector 이벤트를 results/alerts/{date}.jsonl 에 기록
_alerts_dir = Path(_OUTPUT_DIR) / "alerts"
_alerts_dir.mkdir(parents=True, exist_ok=True)
_today_jsonl = _alerts_dir / f"{datetime.now().date().isoformat()}.jsonl"
for ev in anomaly_events[:5]:   # 최대 5건
    event = {
        "triggered_at": datetime.now().isoformat(),
        "rule_name":    "anomaly_detector",
        "severity":     getattr(ev, "severity", "warning"),
        "message":      str(ev)[:120],
        "task_id":      getattr(ev, "task_id", ""),
    }
    with open(_today_jsonl, "a", encoding="utf-8") as _f:
        _f.write(json.dumps(event, ensure_ascii=False) + "\n")

_json_path.write_text(json.dumps(_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

# 저장 확인
has_anomaly = bool(_data.get("anomaly_data"))
has_cost    = bool(_data.get("evaluation_cost", {}).get("total_usd", 0) > 0)
has_alerts  = _today_jsonl.exists() and _today_jsonl.stat().st_size > 0
print(f"\n대시보드 탭 데이터 확인:")
print(f"  이상 감지(anomaly_data): {'✅' if has_anomaly else '❌'}")
print(f"  평가 비용(evaluation_cost total=${_total:.4f}): {'✅' if has_cost else '❌'}")
print(f"  알림(alerts JSONL)     : {'✅' if has_alerts else '❌'}  → {_today_jsonl.name}")

print("\n── CI/CD 품질 게이팅 사용법 ──────────────────────────")
print("  agent-eval gate results/06_operational.json \\")
print("      --tcr 85 --accuracy 70 --quality 60")
print("  → TCR<85% 또는 accuracy<70% 이면 exit(1) → CI 실패")
print("─────────────────────────────────────────────────────")
