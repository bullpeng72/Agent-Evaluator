"""
성능 지표 검증 예제 — Agent Evaluator
======================================

커버 지표 (성능 카테고리):
  Layer 1  │ Task Completion Rate  (TCR · full/partial/failure 분류 · 벤치마크 비교)
           │ Latency Tracking      (p50 · p95 · p99 · 병목 탐지 · SLA 준수)
           │ Token Economy         (입출력 토큰 비율 · 비용 추정 · 월간 예측)

실행:
    python 02_performance_eval.py
"""

import dataclasses
import os
import sys
import random
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from agent_evaluator import PerformanceMonitor, TaskResult, create_taskresult
from agent_evaluator.decorators import agent_eval, EvalMetadata
from agent_evaluator.reporting import generate_comprehensive_html_report

_sc_02: dict = {}  # 루프별 시나리오 공유 컨텍스트


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

_try_setup_otel("02-performance-eval")

# ────────────────────────────────────────────────────────────────────────────────
# 태스크 시나리오 정의
# ────────────────────────────────────────────────────────────────────────────────

# (task_type, completion_profile, latency_profile, token_profile)
# completion_profile: "high"(>0.9 success), "medium"(~0.7), "low"(<0.5)
# latency_profile: "fast"(<1s), "normal"(1-3s), "slow"(5-15s), "timeout"(>15s)
# token_profile: "small"(<500), "medium"(500-2000), "large"(>2000)

TASK_SCENARIOS = [
    # ─── 빠른 QA 태스크 ─────────────────────────────────────────────────────
    ("qa",              "high",   "fast",   "small"),
    ("qa",              "high",   "fast",   "small"),
    ("qa",              "high",   "normal", "small"),
    ("qa",              "medium", "normal", "small"),
    ("qa",              "high",   "fast",   "small"),
    ("qa",              "high",   "fast",   "medium"),
    ("qa",              "high",   "normal", "small"),
    ("qa",              "medium", "slow",   "medium"),
    # ─── 데이터 분석 태스크 ──────────────────────────────────────────────────
    ("data_analysis",   "high",   "normal", "medium"),
    ("data_analysis",   "high",   "slow",   "large"),
    ("data_analysis",   "medium", "slow",   "large"),
    ("data_analysis",   "high",   "normal", "medium"),
    ("data_analysis",   "low",    "slow",   "medium"),
    ("data_analysis",   "high",   "normal", "large"),
    # ─── 코드 생성 태스크 ────────────────────────────────────────────────────
    ("code_generation", "high",   "slow",   "large"),
    ("code_generation", "high",   "normal", "medium"),
    ("code_generation", "medium", "slow",   "large"),
    ("code_generation", "high",   "slow",   "large"),
    ("code_generation", "high",   "normal", "medium"),
    ("code_generation", "low",    "slow",   "medium"),
    ("code_generation", "high",   "slow",   "large"),
    # ─── 추론 태스크 ─────────────────────────────────────────────────────────
    ("reasoning",       "high",   "normal", "medium"),
    ("reasoning",       "high",   "slow",   "large"),
    ("reasoning",       "medium", "normal", "medium"),
    ("reasoning",       "high",   "slow",   "large"),
    ("reasoning",       "low",    "slow",   "large"),
    ("reasoning",       "high",   "normal", "medium"),
    # ─── 문서 생성 태스크 ────────────────────────────────────────────────────
    ("document_creation", "high",  "slow",   "large"),
    ("document_creation", "high",  "normal", "large"),
    ("document_creation", "medium","slow",   "large"),
    ("document_creation", "high",  "slow",   "large"),
    # ─── 정보 검색 태스크 ────────────────────────────────────────────────────
    ("information_retrieval", "high",   "fast",   "small"),
    ("information_retrieval", "high",   "fast",   "medium"),
    ("information_retrieval", "medium", "normal", "medium"),
    ("information_retrieval", "high",   "fast",   "small"),
    # ─── 계획 수립 태스크 ────────────────────────────────────────────────────
    ("planning",        "high",   "slow",   "large"),
    ("planning",        "medium", "slow",   "medium"),
    ("planning",        "high",   "slow",   "large"),
    ("planning",        "high",   "normal", "medium"),
    # ─── 도구 사용 태스크 ────────────────────────────────────────────────────
    ("tool_use",        "high",   "normal", "medium"),
    ("tool_use",        "medium", "slow",   "medium"),
    ("tool_use",        "high",   "normal", "small"),
    ("tool_use",        "low",    "timeout","large"),
    ("tool_use",        "high",   "normal", "medium"),
    # ─── 크리에이티브 태스크 ─────────────────────────────────────────────────
    ("creative",        "high",   "slow",   "large"),
    ("creative",        "medium", "slow",   "large"),
    ("creative",        "high",   "normal", "medium"),
]


def _gen_latency(profile: str, rng: random.Random) -> float:
    if profile == "fast":
        return round(rng.uniform(0.15, 0.80), 3)
    elif profile == "normal":
        return round(rng.uniform(1.0, 3.5), 3)
    elif profile == "slow":
        return round(rng.uniform(4.5, 12.0), 3)
    else:  # timeout
        return round(rng.uniform(15.0, 30.0), 3)


def _gen_tokens(profile: str, rng: random.Random) -> dict:
    if profile == "small":
        inp = rng.randint(50, 250)
        out = rng.randint(30, 150)
    elif profile == "medium":
        inp = rng.randint(250, 1000)
        out = rng.randint(150, 800)
    else:  # large
        inp = rng.randint(1000, 4000)
        out = rng.randint(600, 2500)
    return {"input": inp, "output": out, "total": inp + out}


def _gen_completion(profile: str, rng: random.Random) -> tuple:
    """Returns (success, completion_score, accuracy_score, partial)"""
    if profile == "high":
        score = round(rng.uniform(0.85, 1.0), 3)
        acc = round(rng.uniform(0.78, 0.97), 3)
        return True, score, acc, False
    elif profile == "medium":
        score = round(rng.uniform(0.55, 0.80), 3)
        acc = round(rng.uniform(0.50, 0.78), 3)
        partial = rng.random() < 0.6
        return partial, score, acc, partial
    else:  # low
        score = round(rng.uniform(0.10, 0.50), 3)
        acc = round(rng.uniform(0.10, 0.45), 3)
        return False, score, acc, False


# ── 태스크 타입별 대표 콘텐츠 ─────────────────────────────────────────────────────
# (request, response_ok, response_fail, ground_truth, expected_elements)
_TASK_CONTENT = {
    "qa": (
        "Python GIL(Global Interpreter Lock)이란 무엇이며 멀티스레딩에 어떤 영향을 주나요?",
        "GIL은 CPython에서 한 번에 하나의 스레드만 Python 바이트코드를 실행하도록 제한하는 뮤텍스입니다. CPU 바운드 작업에서는 멀티스레딩 병렬 효과가 제한되지만, I/O 바운드 작업에서는 GIL이 해제되어 유효합니다. CPU 병렬 처리가 필요하면 multiprocessing 모듈을 사용하세요.",
        "GIL에 대한 정보를 찾지 못했습니다.",
        "CPython 스레드 동시 실행 제한 뮤텍스, CPU 바운드 제약·I/O 바운드는 유효, multiprocessing 권장",
        ["GIL", "CPython", "스레드", "CPU 바운드"],
    ),
    "data_analysis": (
        "2024년 분기별 매출 데이터를 분석하고 성장 추세를 파악하세요.",
        "Q1 1.2억(기준), Q2 1.5억(+25%), Q3 1.8억(+20%), Q4 2.1억(+17%). 전체 CAGR 75%. 성장세는 지속되나 증가율은 점차 둔화 중입니다. Q4 집중 마케팅 전략 검토 권고.",
        "데이터 분석을 완료하지 못했습니다.",
        "분기별 성장률 계산, CAGR 75%, 증가율 둔화 추세 주목",
        ["CAGR", "성장률", "분기", "추세"],
    ),
    "code_generation": (
        "Python으로 이진 탐색(Binary Search) 함수를 구현하세요.",
        "def binary_search(arr: list, target: int) -> int:\n    left, right = 0, len(arr) - 1\n    while left <= right:\n        mid = (left + right) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1",
        "def search(arr, target): return -1",
        "이진 탐색 O(log n), left/right 포인터, 타입 힌트 포함",
        ["binary_search", "left", "right", "mid"],
    ),
    "reasoning": (
        "마이크로서비스 아키텍처 도입 시 주요 트레이드오프를 분석하세요.",
        "장점: 독립 배포, 기술 다양성, 장애 격리, 팀 자율성. 단점: 네트워크 오버헤드, 분산 트랜잭션 복잡도, 서비스 디스커버리 필요, 운영 복잡도 증가. 트래픽이 충분하고 팀이 성숙한 경우에 유리합니다.",
        "마이크로서비스는 복잡합니다.",
        "독립 배포·장애 격리 장점 vs 운영 복잡도·네트워크 오버헤드 단점 트레이드오프",
        ["독립 배포", "장애 격리", "운영 복잡도", "네트워크"],
    ),
    "document_creation": (
        "AI 에이전트 평가 시스템 도입 제안서를 작성하세요.",
        "## AI 에이전트 평가 시스템 도입 제안서\n\n**배경**: 운영 중인 LLM 서비스 품질·안전성 모니터링 체계 부재\n\n**제안**: 25개 지표 기반 Agent Evaluator SDK 도입\n- Layer 1: 정확도·완료율·응답 품질 자동 측정\n- Layer 2: 도구 사용·워크플로우·보안 추적\n\n**기대 효과**: 품질 지표 30% 개선, 이슈 탐지 시간 60% 단축",
        "AI 평가 시스템이 필요합니다.",
        "배경·제안 내용·기대 효과 포함, Layer 1·2 설명, 정량 목표 명시",
        ["Layer 1", "Layer 2", "품질 지표", "도입"],
    ),
    "information_retrieval": (
        "Agent Evaluator에서 지원하는 보안 메트릭 5종을 설명하세요.",
        "Layer 2 보안 메트릭 5종: ① InputSanitizationTracker — SQL·XSS·프롬프트 인젝션 탐지 ② OutputLeakageDetector — API키·PII·내부경로 유출 탐지 ③ ToolAuthorizationTracker — 비인가 도구 사용 탐지 ④ PrivilegeEscalationDetector — 권한 상승 체인 탐지 ⑤ ToolChainAttackDetector — APT·횡적 이동 패턴 탐지.",
        "보안 메트릭 정보를 찾지 못했습니다.",
        "InputSanitization, OutputLeakage, ToolAuthorization, PrivilegeEscalation, ToolChainAttack",
        ["InputSanitization", "OutputLeakage", "ToolAuthorization", "PrivilegeEscalation"],
    ),
    "planning": (
        "신규 AI 챗봇 서비스 출시를 위한 3개월 개발 계획을 수립하세요.",
        "1개월차: 요구사항 정의·아키텍처 설계·LLM 선정 / 2개월차: 핵심 기능 개발·RAG 파이프라인 구축·내부 테스트 / 3개월차: 베타 테스트·성능 최적화·모니터링 체계 구축·정식 출시. 단계별 품질 게이트와 KPI 정의 필수.",
        "계획을 수립하지 못했습니다.",
        "3개월 로드맵: 설계→개발→베타→출시, 단계별 품질 게이트",
        ["1개월차", "2개월차", "3개월차", "품질 게이트"],
    ),
    "tool_use": (
        "web_search 도구로 최신 AI 에이전트 프레임워크 동향을 조사하세요.",
        "web_search('AI agent framework 2024') 실행 완료. 주요 동향: LangGraph(멀티에이전트 DAG), CrewAI(역할 기반 협업), AutoGen(대화형 에이전트). 공통 트렌드: RAG 통합, 툴 자동화, 평가 파이프라인 내재화.",
        "검색을 완료하지 못했습니다.",
        "LangGraph·CrewAI·AutoGen 동향, RAG·툴 자동화·평가 트렌드",
        ["LangGraph", "CrewAI", "AutoGen", "RAG"],
    ),
    "creative": (
        "AI 시대의 개발자 역할 변화에 대한 짧은 에세이를 작성하세요.",
        "AI가 코드를 생성하는 시대에 개발자는 '코드 타이피스트'에서 '시스템 설계자'로 진화합니다. 요구사항을 정확히 이해하고 AI 결과물을 검증하며 복잡한 문제를 분해하는 능력이 핵심 역량이 됩니다. 코딩 실력보다 사고력·맥락 파악 능력이 더 중요해지는 전환점입니다.",
        "개발자는 변화가 필요합니다.",
        "AI 시대 개발자 역할: 코드 타이피스트→시스템 설계자, 검증·분해 능력 중요",
        ["시스템 설계자", "검증", "사고력", "맥락"],
    ),
}


def run_performance_evaluation():
    print("\n" + "=" * 70)
    print("  성능 지표 평가 — Agent Evaluator")
    print("  Coverage: Task Completion · Latency · Token Economy")
    print("=" * 70)

    rng = random.Random(1234)

    # for_rag_evaluation(): hallucination_detection 기본 활성 (성능 + 품질 동시 측정)
    monitor = PerformanceMonitor.for_rag_evaluation(
        output_dir=str(project_root / "results"),  # Phoenix Top-models / Cost 차트 그룹핑용
        pricing={"input": 0.00015, "output": 0.0006},  # GPT-4o-mini 수준 per 1K tokens
        enable_transparency=True,
    )

    base_time = datetime.now() - timedelta(hours=4)

    @agent_eval(
        monitor,
        task_type="qa",
        task_id_fn=lambda args, kw: _sc_02.get("task_id", "perf_qa_000"),
        flush_every=26,
        flush_filename="02_performance_eval",
    )
    def _perf_agent(question: str, ground_truth: str = "") -> tuple:
        sc = _sc_02
        response_text = sc["resp_ok"] if sc["success"] else sc["resp_fail"]
        if not sc["success"] and not sc["partial"]:
            raise RuntimeError(sc.get("error_msg", "execution_failed"))
        return response_text, EvalMetadata(
            accuracy_score=sc["accuracy"],
            completion_score=sc["completion"],
            tokens_used=sc["tokens"],
            attempts=sc["attempts"],
            framework="native",
        )

    type_counts: dict = {}
    for idx, (task_type, comp_prof, lat_prof, tok_prof) in enumerate(TASK_SCENARIOS):
        n = type_counts.get(task_type, 0) + 1
        type_counts[task_type] = n
        task_id = f"perf_{task_type[:4]}_{n:03d}"

        success, completion, accuracy, partial = _gen_completion(comp_prof, rng)
        exec_time = _gen_latency(lat_prof, rng)
        tokens = _gen_tokens(tok_prof, rng)

        error_msg = None
        if not success and not partial:
            error_msg = f"{task_type}_execution_failed"
        elif lat_prof == "timeout":
            error_msg = "timeout_exceeded"

        attempts = 1
        if comp_prof in ("low", "medium") and rng.random() < 0.4:
            attempts = rng.randint(2, 3)

        req, resp_ok, resp_fail, ground_truth_text, expected_elems = _TASK_CONTENT.get(
            task_type, _TASK_CONTENT["qa"]
        )
        request_text  = req
        response_text = resp_ok if success else resp_fail

        _sc_02.update({
            "task_id": task_id,
            "success": success,
            "partial": partial,
            "completion": completion,
            "accuracy": accuracy,
            "tokens": tokens,
            "attempts": attempts,
            "error_msg": error_msg,
            "resp_ok": resp_ok,
            "resp_fail": resp_fail,
        })

        try:
            _perf_agent(question=request_text, ground_truth=ground_truth_text)
        except RuntimeError:
            pass

        # Response Quality — 성공 시 expected_elements 기반 5차원 품질 평가
        monitor.quality_evaluator.evaluate_response(
            task_id=task_id,
            response=response_text,
            request=request_text,
            expected_elements=expected_elems if success else [],
            ground_truth=ground_truth_text,
        )

        # Accuracy — ground_truth 대비 실제 응답 정확도 명시적 평가
        monitor.accuracy_evaluator.add_evaluation(
            task_id=task_id,
            ground_truth=ground_truth_text,
            prediction=response_text,
            task_type=task_type,
        )

        if task_type in ("qa", "information_retrieval"):
            monitor.record_rag_metrics(
                faithfulness=round(min(accuracy * rng.uniform(0.85, 1.05), 1.0), 3),
                answer_relevancy=round(min(accuracy * rng.uniform(0.90, 1.10), 1.0), 3),
                context_precision=round(min(completion * rng.uniform(0.80, 1.00), 1.0), 3),
                context_recall=round(min(completion * rng.uniform(0.75, 1.05), 1.0), 3),
            )

    # ─── SLA 임계값 검사 ─────────────────────────────────────────────────────
    sla_targets = {
        "p50": 3.0,   # 3초
        "p95": 10.0,  # 10초
        "p99": 20.0,  # 20초
        "mean": 5.0,  # 5초
    }

    # ─── 직접 트래커 API 호출 — 풍부한 데이터로 각 트래커 기능 검증 ──────────────
    # ① LatencyTracker: 단계별 breakdown 포함 직접 기록
    detailed_latency_cases = [
        # (task_id, task_type, total_time, breakdown)
        ("lat_direct_001", "qa",              0.42, {"preprocessing": 0.02, "model_call": 0.35, "postprocessing": 0.05}),
        ("lat_direct_002", "code_generation", 5.80, {"preprocessing": 0.10, "model_call": 5.20, "postprocessing": 0.50}),
        ("lat_direct_003", "data_analysis",   8.30, {"preprocessing": 0.20, "model_call": 7.50, "postprocessing": 0.60}),
        ("lat_direct_004", "reasoning",       3.10, {"preprocessing": 0.05, "model_call": 2.80, "postprocessing": 0.25}),
        ("lat_direct_005", "qa",              0.28, {"preprocessing": 0.01, "model_call": 0.22, "postprocessing": 0.05}),
        ("lat_direct_006", "document_creation", 12.5, {"preprocessing": 0.30, "model_call": 11.50, "postprocessing": 0.70}),
        ("lat_direct_007", "information_retrieval", 0.65, {"preprocessing": 0.03, "model_call": 0.55, "postprocessing": 0.07}),
        ("lat_direct_008", "planning",        9.20, {"preprocessing": 0.15, "model_call": 8.60, "postprocessing": 0.45}),
    ]
    for tid, ttype, total, breakdown in detailed_latency_cases:
        monitor.latency_tracker.record_latency(tid, ttype, total, breakdown)

    # ② TokenEconomyTracker: 모델별 비용 비교를 위한 직접 기록
    # 동일 태스크를 두 모델로 처리했을 때 비용 차이 비교
    model_comparison_cases = [
        # (task_id, input_tokens, output_tokens, task_type, model)
        ("tok_claude_001", 850,  420, "reasoning",       "claude-3-5-sonnet"),
        ("tok_claude_002", 1200, 680, "code_generation", "claude-3-5-sonnet"),
        ("tok_claude_003", 320,  180, "qa",              "claude-3-5-sonnet"),
        ("tok_gpt4o_001",  850,  410, "reasoning",       os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
        ("tok_gpt4o_002",  1190, 670, "code_generation", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
        ("tok_mini_001",   820,  390, "reasoning",       "gpt-4o-mini"),
        ("tok_mini_002",   1150, 650, "code_generation", "gpt-4o-mini"),
        ("tok_mini_003",   3800, 1800, "data_analysis",  "gpt-4o-mini"),
        ("tok_haiku_001",  310,  175, "qa",              "claude-3-haiku"),
        ("tok_haiku_002",  2500, 1200, "document_creation", "claude-3-haiku"),
    ]
    for tid, inp, out, ttype, model in model_comparison_cases:
        monitor.token_tracker.track_usage(tid, inp, out, ttype, model=model)

    # ③ RetryCorrectionTracker: 다양한 재시도 패턴 직접 기록
    # record_task는 attempts 수만 전달 (성공/실패 구분 없는 단순 로그)
    # 직접 호출로 실제 시도별 성공/실패·소요 시간을 정밀하게 기록
    named_retry_patterns = [
        # (task_id, attempts_log, task_type)
        # 첫 시도 실패 후 즉시 성공 — 응답 형식 오류 교정
        ("retry_pat_001_immediate_fix", [
            {"success": False, "retry_reason": "ValueError: response format mismatch (expected JSON)", "duration": 1.2},
            {"success": True,  "retry_reason": "", "duration": 0.8},
        ], "qa"),
        # 3회 재시도 후 성공 — API 불안정
        ("retry_pat_002_triple_fail", [
            {"success": False, "retry_reason": "TimeoutError: LLM API response exceeded 10s", "duration": 2.5},
            {"success": False, "retry_reason": "TimeoutError: LLM API response exceeded 10s", "duration": 2.1},
            {"success": False, "retry_reason": "RateLimitError: 429 Too Many Requests", "duration": 1.8},
            {"success": True,  "retry_reason": "", "duration": 1.0},
        ], "reasoning"),
        # 첫 시도 성공 (재시도 없음)
        ("retry_pat_003_first_success", [
            {"success": True, "retry_reason": "", "duration": 0.5},
        ], "qa"),
        # 2회 실패 → 성공 — 도구 오류 후 재시도
        ("retry_pat_004_two_fails", [
            {"success": False, "retry_reason": "ToolError: web_search connection reset", "duration": 3.0},
            {"success": False, "retry_reason": "ToolError: web_search timeout (5s)", "duration": 2.8},
            {"success": True,  "retry_reason": "", "duration": 1.5},
        ], "information_retrieval"),
        # 첫 시도 성공 (고속)
        ("retry_pat_005_fast_success", [
            {"success": True, "retry_reason": "", "duration": 0.2},
        ], "qa"),
        # 전체 실패 (eventual_success=False) — 외부 서비스 장애
        ("retry_pat_006_all_fail", [
            {"success": False, "retry_reason": "ServiceUnavailableError: database connection failed", "duration": 5.0},
            {"success": False, "retry_reason": "ServiceUnavailableError: database connection failed", "duration": 4.5},
            {"success": False, "retry_reason": "ServiceUnavailableError: database connection refused", "duration": 4.0},
        ], "data_analysis"),
        # 첫 시도 실패 → 성공 (느린 재시도) — 컨텍스트 초과 후 요약 재시도
        ("retry_pat_007_slow_retry", [
            {"success": False, "retry_reason": "ContextLengthError: input exceeds 128k token limit", "duration": 8.0},
            {"success": True,  "retry_reason": "", "duration": 5.0},
        ], "document_creation"),
        # 단번 성공 (중간 속도)
        ("retry_pat_008_normal", [
            {"success": True, "retry_reason": "", "duration": 1.5},
        ], "reasoning"),
    ]
    for tid, log, ttype in named_retry_patterns:
        monitor.retry_tracker.track_attempts(tid, log, task_type=ttype)

    # Phase 2-C: 암묵적 사용자 피드백 시뮬레이션 — 대시보드 '사용자 반응' 탭 데이터 생성
    _fb_rng = random.Random(42)
    _fb_map = {
        "high":   {"thumbs_up": 0.45, "copy": 0.25, "share": 0.10, "follow_up_depth": 0.10, "regenerate": 0.05, "thumbs_down": 0.03, "abandon": 0.02},
        "medium": {"thumbs_up": 0.20, "copy": 0.15, "share": 0.05, "follow_up_depth": 0.05, "regenerate": 0.25, "thumbs_down": 0.15, "abandon": 0.10, "correction": 0.05},
        "low":    {"thumbs_up": 0.05, "regenerate": 0.40, "thumbs_down": 0.25, "abandon": 0.20, "correction": 0.10},
    }
    for idx, (task_type, comp_prof, *_) in enumerate(TASK_SCENARIOS):
        task_id = f"perf_{task_type[:4]}_{idx+1:03d}"
        dist = _fb_map.get(comp_prof, _fb_map["medium"])
        for fb_type, prob in dist.items():
            if _fb_rng.random() < prob:
                monitor.record_implicit_feedback(
                    task_id=task_id,
                    feedback_type=fb_type,
                    metadata={"task_type": task_type, "profile": comp_prof},
                )

    # 리포트 저장
    report = monitor.generate_report()
    filename = f"[P]_performance_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    saved_path = monitor.save_to_file(filename)
    html_path = Path(saved_path).with_suffix('.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(generate_comprehensive_html_report(monitor))
    print(f"📄 HTML 리포트 저장: {html_path}")

    # ─── 결과 출력 ────────────────────────────────────────────────────────────
    tcr_data    = report.accuracy_metrics.get("tcr", {})
    latency_data = report.efficiency_metrics.get("latency", {})
    token_data  = report.efficiency_metrics.get("tokens", {})
    retry_data  = report.efficiency_metrics.get("retries", {})

    print(f"\n{'─'*70}")
    print(f"  총 평가 태스크: {report.total_tasks}개")
    print(f"  저장 위치: {saved_path}")

    total_tasks = report.total_tasks

    print(f"\n  [Task Completion Rate]")
    if tcr_data:
        tcr_val = tcr_data.get("tcr", 0)
        full    = tcr_data.get("full_success", 0)
        partial = tcr_data.get("partial_success", 0)
        fail    = tcr_data.get("failures", 0)
        bench   = monitor.tcr_tracker.get_benchmark_status(tcr_val)
        print(f"    TCR (전체):    {tcr_val:.1f}%")
        print(f"    완전 성공:     {full}/{total_tasks}건")
        print(f"    부분 성공:     {partial}/{total_tasks}건")
        print(f"    실패:          {fail}/{total_tasks}건")
        print(f"    벤치마크:      {bench}")

    print(f"\n  [Latency (초)]")
    if latency_data:
        # latency_data: {'all': {...}, 'qa': {...}, ...} 또는 flat dict
        lat = latency_data.get("all", latency_data)
        if not isinstance(lat, dict) or "p50" not in lat:
            # try first value that has p50
            for v in latency_data.values():
                if isinstance(v, dict) and "p50" in v:
                    lat = v
                    break
        print(f"    p50:  {lat.get('p50', 0):.2f}s")
        print(f"    p95:  {lat.get('p95', 0):.2f}s")
        print(f"    p99:  {lat.get('p99', 0):.2f}s")
        print(f"    평균: {lat.get('mean', 0):.2f}s")
        bottleneck = lat.get("slowest_type", lat.get("bottleneck", ""))
        if bottleneck:
            print(f"    최고 지연 타입: {bottleneck}")

    sla_check = monitor.latency_tracker.check_sla_compliance(sla_targets)
    if sla_check:
        violations = [k for k, v in sla_check.items()
                      if isinstance(v, dict) and not v.get("compliant", True)]
        print(f"    SLA 위반: {violations if violations else '없음'}")

    print(f"\n  [Token Economy]")
    if token_data:
        dist = token_data.get("token_distribution", {})
        in_ratio  = dist.get("input_ratio", 0)
        out_ratio = dist.get("output_ratio", 0)
        print(f"    총 토큰:        {token_data.get('total_tokens', 0):,}")
        print(f"    총 비용:        ${token_data.get('total_cost', 0):.4f}")
        print(f"    태스크당 비용:  ${token_data.get('avg_cost_per_task', 0):.5f}")
        print(f"    월간 예상 비용: ${token_data.get('estimated_monthly_cost', 0):.2f}")
        print(f"    입출력 비율:    입력 {in_ratio*100:.0f}% / 출력 {out_ratio*100:.0f}%")

    print(f"\n  [Retry & Correction]")
    if retry_data:
        print(f"    재시도율:       {retry_data.get('retry_rate', 0):.1f}%")
        print(f"    첫시도 성공률:  {retry_data.get('first_attempt_success_rate', 0):.1f}%")
        print(f"    최종 성공률:    {retry_data.get('eventual_success_rate', 0):.1f}%")

    if report.alerts:
        print(f"\n  [Alerts — {len(report.alerts)}건]")
        for a in report.alerts[:4]:
            print(f"    [{a['severity'].upper()}] {a['metric']}")

    if report.recommendations:
        print(f"\n  [Recommendations — {len(report.recommendations)}건]")
        for r in report.recommendations[:3]:
            print(f"    → [{r.get('priority','').upper()}] {r.get('title', r.get('area', ''))}")

    # ─── 검증 테이블 ─────────────────────────────────────────────────────────
    tcr_val     = tcr_data.get("tcr", 0) if tcr_data else 0
    lat         = latency_data.get("all", latency_data) if latency_data else {}
    if not isinstance(lat, dict) or "p95" not in lat:
        for v in (latency_data or {}).values():
            if isinstance(v, dict) and "p95" in v:
                lat = v; break
    p95_val     = lat.get("p95", 0)
    total_cost  = token_data.get("total_cost", 0) if token_data else 0
    retry_rate  = retry_data.get("retry_rate", 0) if retry_data else 0
    first_suc   = retry_data.get("first_attempt_success_rate", 0) if retry_data else 0

    # 모델별 비용 비교 — track_usage() 직접 호출 결과 검증
    # usage_log에서 model 필드 집계 (get_usage_stats는 per-model 분리 미지원)
    unique_models = {e["model"] for e in monitor.token_tracker.usage_log
                     if e.get("model") and e["model"] != "default"}
    multi_model = len(unique_models) >= 2  # 2가지 이상 모델 명시 기록 확인

    # 재시도 직접 등록 — first_attempt_success_rate 분리 확인
    retry_stats = monitor.retry_tracker.get_retry_metrics()
    first_suc_r = retry_stats.get("first_attempt_success_rate", 0)

    # Latency breakdown — 직접 등록한 케이스가 트래커에 반영됐는지 확인
    lat_stats_qa = monitor.latency_tracker.get_latency_stats(task_type="qa")
    lat_qa_p50   = lat_stats_qa.get("p50", 0)

    checks = [
        #  항목                           기준            실제값                  통과 여부
        ("TCR (전체 완료율)",              "> 60.0%",   f"{tcr_val:.1f}%",       tcr_val > 60.0),
        ("p95 지연 시간",                  "< 25.0s",   f"{p95_val:.2f}s",       p95_val < 25.0),
        ("전체 추정 비용",                 "< $1.00",   f"${total_cost:.4f}",    total_cost < 1.00),
        ("재시도율 (retry_rate)",          "> 0%",      f"{retry_rate:.1f}%",    retry_rate > 0),
        ("첫시도 성공률 (retry 직접 등록)","≥ 10%",     f"{first_suc_r:.1f}%",   first_suc_r >= 10.0),
        ("모델별 비용 분리 (≥2종)",        "True",      str(multi_model),        multi_model),
        ("QA p50 직접 기록 반영",          "> 0s",      f"{lat_qa_p50:.3f}s",    lat_qa_p50 > 0),
    ]

    print(f"\n  {'═'*66}")
    print(f"  {'검증 항목':<30} {'기준':<12} {'실측값':<14} {'결과'}")
    print(f"  {'─'*66}")
    pass_cnt = 0
    for name, threshold, actual, ok in checks:
        mark = "PASS ✅" if ok else "FAIL ❌"
        if ok: pass_cnt += 1
        print(f"  {name:<30} {threshold:<12} {actual:<14} {mark}")
    print(f"  {'═'*66}")
    print(f"  합계: {pass_cnt}/{len(checks)} 통과\n")

    print(f"{'─'*70}\n")
    return saved_path


if __name__ == "__main__":
    run_performance_evaluation()
