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

import os
from agent_evaluator import (
    PerformanceMonitor,
    setup_otel,
    LLMJudgeConfig,
    create_taskresult,
    load_env,
    agent_eval,
    EvalMetadata,
    RetryConfig,
    # Gate C — Reliability
    FaultToleranceConfig,
    GracefulDegradationConfig,
    ReproducibilityConfig,
    RetryConsistencyConfig,
    IdempotencyConfig,
)

load_env()

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
    enable_hallucination_detection=True,   # Gate C: HallucinationDetector 활성화
    enable_security_metrics=False,
    enable_transparency=True,
    use_korean_tokenizer=True,
)

# ===========================================================================
# 섹션 1: HallucinationDetector 활성화 패턴 (RAG 모드)
# ===========================================================================
print("\n=== 섹션 1: HallucinationDetector + RAG 모드 ===")

@agent_eval(monitor, task_type="qa", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    # TODO(현업 적용): 이 mock을 실제 에이전트 구현으로 교체하세요.
    # HallucinationDetector는 NLP 기반으로 동작하므로 LLM 호출 불필요.
    if context:
        return f"주어진 문맥을 바탕으로 답변드립니다. {question} — 문맥: {context[:40]}"
    return "문맥 정보가 없어 답변하기 어렵습니다."


rag_agent(
    "아인슈타인이 태어난 해는?",
    context="알베르트 아인슈타인(1879-1955)은 독일의 물리학자이다.",
    ground_truth="1879년",
)
rag_agent(
    "퀴리 부인의 국적은?",
    context="마리 퀴리(1867-1934)는 폴란드 출신의 프랑스 물리학자·화학자이다.",
    ground_truth="폴란드/프랑스",
)

_r1 = monitor.generate_report().to_dict()
_hall = (_r1.get("accuracy_metrics") or {}).get("hallucination", {})
print(f"  환각률: {_hall.get('overall_rate', 0):.1f}%")
print(f"  섹션 1 완료: RAG 2건 기록")

# ===========================================================================
# 섹션 2: RAG Faithfulness + LLMJudge 결합 패턴
# ===========================================================================
print("\n=== 섹션 2: RAG Faithfulness + LLMJudge ===")

_has_llm_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))

if not _has_llm_key:
    print("  API 키 없음 — LLMJudge 섹션 skip (OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 필요)")
else:
    @agent_eval(
        monitor,
        task_type="information_retrieval",
        rag_mode=True,
        llm_judge=LLMJudgeConfig(
            model=None,       # None → API 키 기반 자동 결정
            sample_rate=1.0,  # 예제: 100% 채점 (프로덕션은 0.2 권장)
        ),
    )
    def rag_faithfulness_agent(question: str, context: str = "", ground_truth: str = "") -> str:
        # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
        #   예) return client.chat.completions.create(model="gpt-5-nano",
        #        messages=[{"role":"user","content":question}]).choices[0].message.content
        # 에이전트 응답은 mock — LLMJudge가 이 응답의 faithfulness를 LLM으로 채점
        if context:
            return f"주어진 문맥을 바탕으로 답변드립니다. {question} — 문맥: {context[:40]}"
        return "문맥 정보가 없어 답변하기 어렵습니다."

    rag_faithfulness_agent(
        "아인슈타인이 태어난 해는?",
        context="알베르트 아인슈타인(1879-1955)은 독일의 물리학자이다.",
        ground_truth="1879년",
    )

    _last = monitor.tasks[-1] if monitor.tasks else None
    if _last:
        _judge = _last.llm_judge or {}
        _faith = (_judge.get("scores") or {}).get("faithfulness")
        if _faith is not None:
            print(f"  RAG Faithfulness: {_faith}/5 (5=모든 주장이 컨텍스트에 근거)")
        elif _judge.get("skipped"):
            print("  LLMJudge: sample_rate에 의해 skip됨")
        elif _judge.get("error"):
            print(f"  LLMJudge 오류: {_judge['error']}")
    print("  섹션 2 완료: RAG Faithfulness + LLMJudge 1건 기록")

# ===========================================================================
# 섹션 2-b: RetryCorrectionTracker — attempts/errors 직접 기록 패턴
# ===========================================================================
print("\n=== 섹션 2-b: RetryCorrectionTracker ===")

_retry_cases = [
    ("복잡한 계산 태스크",  "최종 답변: 42",  "42",  3, ["timeout", "invalid_format"]),
    ("단순 조회 태스크",    "조회 결과: OK",  "OK",  1, []),
    ("네트워크 호출 태스크", "응답: 200",     "200", 2, ["connection_reset"]),
]
for _q, _resp, _gt, _att, _errs in _retry_cases:
    monitor.record_task(create_taskresult(
        task_id=f"retry_{_att}",
        question=_q,
        response=_resp,
        ground_truth=_gt,
        execution_time=float(_att),
        task_type="reasoning",
        attempts=_att,
        errors=_errs,
    ))

_r2b = monitor.generate_report().to_dict()
_retries = (_r2b.get("efficiency_metrics") or {}).get("retries", {})
print(f"  재시도율: {_retries.get('retry_rate', 0):.1f}%")
print(f"  최종 성공률: {_retries.get('eventual_success_rate', 0):.1f}%")
print(f"  재시도 후 성공 건수: {_retries.get('retry_success_count', 0)}")
print(f"  태스크당 평균 시도: {_retries.get('avg_attempts_per_task', 0):.1f}회")
print(f"  섹션 2-b 완료: {len(_retry_cases)}건 기록")

# ===========================================================================
# 섹션 3: Gate C — Reliability
# ===========================================================================
print("\n=== 섹션 3: Gate C — Reliability ===")


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
def fault_tolerant_agent(question: str, ground_truth: str = "") -> tuple:
    """장애 내성 + 우아한 저하 에이전트 (실무 패턴)

    에러 발생 시 무조건 raise하여 중단하는 것이 아니라,
    try-except로 감싸 사용자에게 '부분적인 결과'라도 제공하는 패턴을 보여줍니다.
    """
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    _fault_call_count["n"] += 1

    try:
        if _fault_call_count["n"] % 3 == 1:
            # 의도적 장애 발생 시뮬레이션
            raise RuntimeError("외부 API 타임아웃 발생")

        return f"정상 처리 완료: {question}", EvalMetadata()

    except RuntimeError as e:
        # [실무 팁] 에러를 잡아서 '우아한 저하' 응답으로 변환
        # EvalMetadata로 내부 catch 에러와 tool_calls를 데코레이터에 전달해야
        # graceful_degradation(has_error=True)과 fault_tolerance(grade="good")가 올바르게 채점됨
        print(f"  [시스템 로그] 장애 감지: {e} → 폴백 모드 전환")
        response = f"부분 완료(폴백): 외부 도구 일시 오류({e})로 인해 캐시 데이터로 응답합니다. {question}"
        tool_calls = [
            {"name": "main_tool",  "success": False, "error": str(e)},
            {"name": "cache_tool", "success": True},
        ]
        return response, EvalMetadata(errors=[f"RuntimeError: {e}"], tool_calls=tool_calls)


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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
def retry_consistent_agent(question: str, ground_truth: str = "") -> tuple:
    """재시도 일관성 에이전트 (mock)."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    # EvalMetadata(attempts=2): 1회 실패 후 재시도 성공 시나리오 시뮬레이션
    # RetryConfig on=(ValueError,)가 실제 발동 시 decorator가 attempts를 자동 기록함
    return f"일관된 재시도 응답: {question}", EvalMetadata(attempts=2)


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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"읽기 전용 조회 완료: {question}에 대한 데이터를 검색했습니다."


# 섹션 3 실행
RELIABILITY_CASES = [
    ("서버 상태를 확인해줘", "정상"),
    ("데이터를 읽어줘", "데이터 조회"),
    ("현재 설정을 보여줘", "설정 조회"),
]

print("  Reliability 패턴 실행 (장애 복구 시뮬레이션)...")
for q, gt in RELIABILITY_CASES:
    # 에이전트 내부에서 에러를 처리하므로 호출부의 try-except는 '완전 실패' 대비용
    try:
        resp = fault_tolerant_agent(q, ground_truth=gt)
        status = "⚠️ 폴백" if "부분" in resp else "✅ 정상"
        print(f"    {status} 응답: {resp[:50]}...")
    except Exception as e:
        print(f"    ❌ 완전 실패: {e}")

    reproducible_agent(q, ground_truth=gt)
    retry_consistent_agent(q, ground_truth=gt)
    idempotent_agent(q, ground_truth=gt)

print(f"  섹션 3 완료: ~{len(RELIABILITY_CASES) * 4}건 기록")

# ── 역케이스: Gate C FAIL 유도 (IdempotencyConfig) ───────────────────────────
_monitor_c_fail = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

@agent_eval(
    _monitor_c_fail, task_type="tool_use", task_id_prefix="c_fail_idempotency",
    idempotency=IdempotencyConfig(
        non_idempotent_patterns=["create", "insert", "생성", "등록", "delete"],
        non_idempotent_penalty=0.4,
    ),
)
def _c_fail_agent(question: str, ground_truth: str = "") -> tuple:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
print("확인: agent-eval dashboard results/")
