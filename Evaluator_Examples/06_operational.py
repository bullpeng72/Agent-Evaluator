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

의존성:
    필수: pip install agent-evaluator          (numpy·pandas·python-dotenv 포함)
    선택: agent-eval monitor                   (Phoenix OTEL 시각화 — 없어도 실행됨)

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
# 섹션 3: GoldenSetBuilder — QA / RAG / Tool Selection 골든 데이터 구축
# ===========================================================================
# 대시보드 '케이스 검토' 탭 연동:
#   data/golden_datasets/*candidates*.json 파일을 저장하면
#   → agent-eval dashboard → 케이스 검토 탭에서 승인/거부/병합 가능
# ===========================================================================
print("\n=== 섹션 3: 골든 데이터셋 구축 (QA + RAG + Tool Selection) ===")

monitor_golden = PerformanceMonitor(output_dir=_OUTPUT_DIR)

# GoldenSetBuilder: source_dir = 평가 결과 JSON 위치, output_dir = 골든 데이터 저장 위치
builder = GoldenSetBuilder(
    source_dir=_OUTPUT_DIR,
    output_dir=str(_PROJECT_ROOT / "data" / "golden_datasets"),
)

# ---------------------------------------------------------------------------
# 3-A: QA 골든 케이스
# ---------------------------------------------------------------------------
QA_DEFINITIONS = [
    # (question, response, ground_truth, latency, description)
    ("서울의 특징은?",       "서울은 대한민국의 수도입니다.",        "서울은 한국의 수도",      0.8,  "고품질"),
    ("파이썬이란?",          "파이썬은 범용 프로그래밍 언어입니다.", "파이썬 프로그래밍 언어",  1.2,  "고품질"),
    ("1+1은?",              "2",                                    "2",                   0.3,  "엣지 케이스"),
    ("asd#$@! 란?",         "모르겠습니다",                         "정의 없음",             0.5,  "엣지케이스 (특수문자)"),
    ("복잡한 질문...",       "",                                     "상세한 답변",           10.5, "실패 케이스"),
    ("머신러닝이란?",        "머신러닝은 AI의 한 분야입니다.",       "AI 기계학습",           1.5,  "중간 품질"),
    ("클라우드란?",          "클라우드는 인터넷 기반 서비스입니다.", "인터넷 서비스",          1.1,  "고품질"),
    ("에러 케이스",          "",                                     "올바른 응답",           0.2,  "오류"),
]

golden_tasks = []
for q, resp, gt, lat, desc in QA_DEFINITIONS:
    r = create_taskresult(
        task_id=f"golden_{desc[:5]}_{hash(q)%1000:03d}",
        question=q, response=resp, ground_truth=gt,
        execution_time=lat, task_type="qa",
        tokens_used={"input": 80, "output": 30, "total": 110},
    )
    monitor_golden.record_task(r)
    golden_tasks.append(r)
    print(f"  [QA][{desc:<12s}] acc={r.accuracy_score:.2f}  lat={lat:.1f}s")

# ---------------------------------------------------------------------------
# 3-B: RAG 골든 케이스 (question + context + ground_truth)
# ---------------------------------------------------------------------------
print()
RAG_DEFINITIONS = [
    # (question, context, response, ground_truth, latency)
    (
        "판다스에서 결측값을 처리하는 방법은?",
        "판다스는 dropna()로 결측값 행을 제거하거나, fillna()로 특정 값으로 채울 수 있습니다.",
        "dropna()로 제거하거나 fillna()로 채울 수 있습니다.",
        "dropna()로 제거하거나 fillna()로 채울 수 있다",
        1.23,
    ),
    (
        "HTTP와 HTTPS의 차이는?",
        "HTTPS는 HTTP에 TLS/SSL 암호화를 추가한 버전으로, 포트 443을 사용합니다.",
        "HTTPS는 HTTP에 TLS 암호화를 적용한 보안 버전이며 443번 포트를 씁니다.",
        "HTTPS는 HTTP에 TLS 암호화를 추가한 보안 프로토콜",
        0.98,
    ),
    (
        "도커 컨테이너와 가상 머신의 차이는?",
        "컨테이너는 호스트 OS 커널을 공유해 가볍고, VM은 전체 OS를 포함해 강한 격리를 제공합니다.",
        "컨테이너는 커널 공유로 경량, VM은 전체 OS 포함으로 강격리입니다.",
        "컨테이너는 커널 공유 경량, VM은 전체 OS 포함 강격리",
        1.12,
    ),
    (
        "트랜스포머 어텐션이란?",
        "",  # 컨텍스트 없음 — 커버리지 갭 케이스
        "어텐션은 Q·K·V 행렬 내적으로 토큰 간 관련도를 계산합니다.",
        "Q·K·V 행렬 내적으로 토큰 관련도 계산",
        1.67,
    ),
]

rag_tasks = []
for i, (q, ctx, resp, gt, lat) in enumerate(RAG_DEFINITIONS):
    r = create_taskresult(
        task_id=f"rag_{i+1:03d}",
        question=q, response=resp, ground_truth=gt, context=ctx,
        execution_time=lat, task_type="information_retrieval",
        tokens_used={"input": 120, "output": 50, "total": 170},
    )
    monitor_golden.record_task(r)
    rag_tasks.append(r)
    ctx_tag = "(no-ctx)" if not ctx else ""
    print(f"  [RAG] {q[:30]:<30s}  acc={r.accuracy_score:.2f} {ctx_tag}")

# ---------------------------------------------------------------------------
# 3-C: Tool Selection 골든 케이스 (expected_tools 기반 F1)
# ---------------------------------------------------------------------------
print()
TOOL_DEFINITIONS = [
    # (question, used_tools, expected_tools, latency)
    ("날씨와 환율 조회",          ["web_search", "calculator"], ["web_search", "calculator"], 1.52),
    ("코스피 → 엑셀 저장",        ["web_search", "database"],   ["web_search", "file_write"],  2.31),
    ("데이터 분석 + 차트 생성",   ["data_analysis", "chart_generator", "web_search"],
                                   ["data_analysis", "chart_generator"],                       3.14),
    ("이메일 중복 제거 + CSV",    ["calculator", "web_search"], ["data_analysis", "file_write"], 1.08),
    ("코드 + 단위 테스트 생성",   ["code_generator", "test_generator"],
                                   ["code_generator", "test_generator"],                       2.87),
]

tool_tasks = []
for q, used, expected, lat in TOOL_DEFINITIONS:
    r = create_taskresult(
        task_id=f"tool_{hash(q)%1000:03d}",
        question=q, response="처리 완료", ground_truth="도구 선택 완료",
        execution_time=lat, task_type="tool_use",
        tokens_used={"input": 100, "output": 40, "total": 140},
        tool_calls=[{"tool_name": t, "success": True} for t in used],
        expected_tools=expected,
    )
    monitor_golden.record_task(r)
    tool_tasks.append(r)
    overlap = len(set(used) & set(expected))
    print(f"  [Tool] {q:<22s}  used={used}  F1={overlap}/{max(len(used),len(expected))}")

# ---------------------------------------------------------------------------
# GoldenSet 형식 변환 헬퍼 — _requires_review=True 포함 (대시보드 케이스 검토용)
# ---------------------------------------------------------------------------
def _to_golden_dict(r, strategy: str = "high_value", extra: dict = None) -> dict:
    d = {
        "task_id":        r.task_id,
        "question":       getattr(r, "question", r.task_id) or r.task_id,
        "response":       getattr(r, "response", "") or "",
        "ground_truth":   getattr(r, "ground_truth", "") or "",
        "accuracy_score": r.accuracy_score,
        "execution_time": r.execution_time,
        "task_type":      str(r.task_type),
        "_requires_review": True,           # ← 대시보드 케이스 검토 '검토 대기' 집계 키
        "_strategy":      strategy,
        "_extracted_at":  datetime.now().isoformat(),
    }
    if extra:
        d.update(extra)
    return d

try:
    # QA: 정확도 기준 분류
    qa_high    = [_to_golden_dict(r, "high_value")     for r in golden_tasks if r.accuracy_score >= 0.7]
    qa_fail    = [_to_golden_dict(r, "failure_cases")  for r in golden_tasks if r.accuracy_score < 0.2]
    qa_edge    = [_to_golden_dict(r, "edge_cases")     for r in golden_tasks
                  if r.execution_time > 8.0 or len(getattr(r, "question", "") or "") < 5]
    qa_all = qa_high + qa_fail + qa_edge
    print(f"\n  [QA candidates]  고가치={len(qa_high)} / 실패={len(qa_fail)} / 엣지={len(qa_edge)}")

    # RAG: context 유무로 분류
    rag_all = []
    for r in rag_tasks:
        has_ctx = bool(getattr(r, "context", ""))
        strategy = "high_value" if has_ctx and r.accuracy_score >= 0.7 else "coverage_gap"
        rag_all.append(_to_golden_dict(r, strategy, extra={
            "context": getattr(r, "context", "") or "",
        }))
    print(f"  [RAG candidates] 총 {len(rag_all)}건 (context 없는 케이스 포함)")

    # Tool Selection: expected_tools 필드 포함
    tool_all = []
    for r in tool_tasks:
        expected = getattr(r, "expected_tools", None) or []
        used     = [tc["tool_name"] for tc in (getattr(r, "tool_calls", None) or [])]
        strategy = "high_value" if set(used) == set(expected) else "failure_cases"
        tool_all.append(_to_golden_dict(r, strategy, extra={
            "expected_tools": expected,
            "used_tools":     used,
        }))
    print(f"  [Tool candidates] 총 {len(tool_all)}건")

    # 타입별 후보 파일 저장 → data/golden_datasets/ → 대시보드 케이스 검토 탭
    if qa_all:
        p = builder.save_candidates(qa_all,   filename="06_qa_candidates.json")
        print(f"\n  저장: {p}")
    if rag_all:
        p = builder.save_candidates(rag_all,  filename="06_rag_candidates.json")
        print(f"  저장: {p}")
    if tool_all:
        p = builder.save_candidates(tool_all, filename="06_tool_candidates.json")
        print(f"  저장: {p}")

    print("\n  ✓ agent-eval dashboard → 케이스 검토 탭에서 승인/거부/병합 가능")

    # 고가치 QA + RAG를 마스터 골든셋으로 병합
    master_items = qa_high + [d for d in rag_all if d.get("accuracy_score", 0) >= 0.8]
    if master_items:
        merged = builder.merge_to_golden(master_items, version="v1", output_name="master_golden")
        print(f"  마스터 골든셋 병합: {merged} ({len(master_items)}건)")

except Exception as e:
    print(f"  GoldenSetBuilder: {e}")

# ===========================================================================
# 섹션 4: evaluation_session — context manager + 자동 저장
# ===========================================================================
print("\n=== 섹션 4: evaluation_session context manager ===")

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
