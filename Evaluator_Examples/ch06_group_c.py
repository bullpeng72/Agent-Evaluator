"""
ch06_group_c.py — Gate C: Reliability
======================================
Book Chapter 06 — Gate C: Reliability

FaultToleranceConfig, GracefulDegradationConfig, ReproducibilityConfig,
RetryConsistencyConfig, IdempotencyConfig — 5개 Config 전체 시연.

역케이스(_monitor_c_fail)로 Gate C FAIL 유도 비교도 포함한다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch06_group_c.py

결과:
    results/ch06_group_c.json  (+ .html)
    → 전체 33개 Config 통합 예제: Evaluator_Examples/.deprecated/08_harness_eval.py
"""

import socket
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    setup_otel,
    # Group C — Reliability
    FaultToleranceConfig,
    GracefulDegradationConfig,
    ReproducibilityConfig,
    RetryConsistencyConfig,
    IdempotencyConfig,
)
from agent_evaluator.decorators import agent_eval, RetryConfig, EvalMetadata

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch06-group-c")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Gate C 전용 monitor
# ---------------------------------------------------------------------------
monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_hallucination_detection=False,
    enable_security_metrics=False,
    enable_transparency=True,
)

# ===========================================================================
# 섹션 3: Group C — Reliability
# ===========================================================================
print("\n=== 섹션 3: Group C — Reliability ===")


_fault_call_count = {"n": 0}


@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="c_fault",
    fault_tolerance=FaultToleranceConfig(
        check_fallback_attempts=True,
        partial_success_threshold=0.5,
    ),
    graceful_degradation=GracefulDegradationConfig(
        quality_floor=0.4,
        partial_result_markers=["부분", "폴백", "fallback", "partial"],
        check_error_acknowledgment=True,
    ),
    retry=RetryConfig(max=2, on=(RuntimeError,), delay=0.0),
)
def fault_tolerant_agent(question: str, ground_truth: str = "") -> str:
    """장애 내성 + 우아한 저하 에이전트 (mock) — 실패 시 부분 완료 응답."""
    _fault_call_count["n"] += 1
    if _fault_call_count["n"] % 3 == 1:
        # 우아한 저하: 완전 실패 대신 부분 결과 + 오류 인정 반환
        return f"부분 완료(폴백): 외부 도구 일시 오류로 인해 캐시 데이터로 응답합니다. {question}"
    return f"폴백 처리 완료: {question}"


@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="c_repro",
    reproducibility=ReproducibilityConfig(
        runs=3,
        similarity_measure="token_f1",
        reproducibility_threshold=0.8,
    ),
)
def reproducible_agent(question: str, ground_truth: str = "") -> str:
    """재현성 에이전트 (mock) — 동일 입력에 동일 응답."""
    # 결정론적 응답 (재현성 ↑)
    return f"재현 가능한 답변: {question}에 대해 정해진 응답을 반환합니다."


@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="c_retry_consistency",
    retry_consistency=RetryConsistencyConfig(
        min_retry_count=2,
        improvement_threshold=0.1,
    ),
    retry=RetryConfig(max=3, on=(ValueError,), delay=0.0),
)
def retry_consistent_agent(question: str, ground_truth: str = "") -> str:
    """재시도 일관성 에이전트 (mock)."""
    return f"일관된 재시도 응답: {question}"


@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="c_idempotency",
    idempotency=IdempotencyConfig(
        non_idempotent_patterns=["create", "delete", "insert", "생성", "삭제"],
        non_idempotent_penalty=0.2,
    ),
)
def idempotent_agent(question: str, ground_truth: str = "") -> str:
    """멱등성 에이전트 (mock) — 읽기 전용 작업 우선."""
    return f"읽기 전용 조회 완료: {question}에 대한 데이터를 검색했습니다."


# 섹션 3 실행
RELIABILITY_CASES = [
    ("서버 상태를 확인해줘", "정상"),
    ("데이터를 읽어줘", "데이터 조회"),
    ("현재 설정을 보여줘", "설정 조회"),
    ("로그를 분析해줘", "로그 분析"),
]

for q, gt in RELIABILITY_CASES:
    try:
        fault_tolerant_agent(q, ground_truth=gt)
    except Exception:
        pass  # 재시도 소진 케이스는 무시
    reproducible_agent(q, ground_truth=gt)
    retry_consistent_agent(q, ground_truth=gt)
    idempotent_agent(q, ground_truth=gt)

print(f"  섹션 3 완료: ~{len(RELIABILITY_CASES) * 4}건 기록")

# ── 역케이스: Gate C FAIL 유도 (IdempotencyConfig) ───────────────────────────
_monitor_c_fail = PerformanceMonitor(output_dir=_OUTPUT_DIR)

@agent_eval(
    _monitor_c_fail, task_type="tool_use", task_id_prefix="c_fail_idempotency",
    idempotency=IdempotencyConfig(
        non_idempotent_patterns=["create", "insert", "생성", "등록", "delete"],
        non_idempotent_penalty=0.4,
    ),
)
def _c_fail_agent(question: str, ground_truth: str = "") -> tuple:
    return f"레코드 생성 및 등록: {question}", EvalMetadata(
        tool_calls=[
            {"name": "create_record", "args": {"data": question}},
            {"name": "insert_db",     "args": {"row": question}},
            {"name": "delete_old",    "args": {"id": "prev"}},
        ],
    )

for _q in ["신규 주문을 등록해줘", "회원을 생성해줘", "레코드를 추가해줘"]:
    _c_fail_agent(_q)

_r = _monitor_c_fail.generate_report().to_dict()
_s = (_r.get("extra_metrics") or {}).get("harness_groups", {}).get("C", {})
_pct = f"{_s['score']*100:.1f}%" if _s.get("score") is not None else "n/a"
print(f"  ▶ 역케이스 Gate C: {_pct}  {'FAIL 확인 ✓' if (_s.get('gate','').upper()=='FAIL') else '예상과 다름'}")

# Gate C 점수 출력
_report = monitor.generate_report().to_dict()
_harness = (_report.get("extra_metrics") or {}).get("harness_groups", {})
_gd = _harness.get("C", {})
_score = _gd.get("score")
_status = _gd.get("status", "n/a")
if _score is not None:
    _bar = "█" * int(_score * 10) + "░" * (10 - int(_score * 10))
    print(f"\n  Gate C [Reliability            ] {_bar} {_score:.3f} ({_status})")

monitor.save_to_file("ch06_group_c")
print("\n결과 저장 완료: results/ch06_group_c.json")
print("확인: agent-eval dashboard --results results/")
