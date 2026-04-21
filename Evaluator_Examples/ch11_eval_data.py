"""
ch11_eval_data.py — 평가데이터 설계 (GoldenSetBuilder)
=======================================================
Book Chapter 11 — 평가데이터 설계

GoldenSetBuilder로 QA·RAG·Tool Selection 골든 데이터셋을 구축하고,
evaluation_session context manager로 자동 저장을 시연한다.

  GoldenSetBuilder:
    - QA 고가치·실패·엣지 케이스 자동 분류
    - RAG context 유무 기반 coverage_gap 탐지
    - Tool Selection expected_tools F1 기반 고가치·실패 분류
    - save_candidates() / merge_to_golden() — 대시보드 케이스 검토 탭 연동

  evaluation_session:
    - context manager 기반 자동 저장
    - JSON + HTML 생성 → agent-eval dashboard 연동

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch11_eval_data.py

결과:
    results/ch11_eval_data.json  (+ .html)
    data/golden_datasets/  (골든 데이터셋)
    → 전체 운영 인프라 예제: Evaluator_Examples/.deprecated/06_operational.py
"""

import socket
from datetime import datetime
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    create_taskresult,
    evaluation_session,
    setup_otel,
    AnomalyDetector,
    CostTracker,
    AdaptivePolicy,
    SamplingStage,
)
from agent_evaluator.decorators import agent_eval
from agent_evaluator.datasets.builder import GoldenSetBuilder

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")
_DATA_DIR     = str(_PROJECT_ROOT / "data")

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch11-eval-data")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ===========================================================================
# 섹션 1: create_taskresult() — TaskResult 기본 생성
# ===========================================================================
# create_taskresult() 헬퍼는 accuracy_score·completion_score를 자동 계산한다.
# TaskResult 직접 생성보다 권장되는 방식이다.
# ===========================================================================
print("\n=== 섹션 1: create_taskresult() 기본 사용 ===")

# 기본 QA TaskResult — 자동 점수 계산
r_qa = create_taskresult(
    task_id="qa_demo_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=0.85,
    task_type="qa",
    tokens_used={"input": 20, "output": 10, "total": 30},
)
print(f"  [QA]      accuracy={r_qa.accuracy_score:.3f}  completion={r_qa.completion_score:.3f}")

# 코드 생성 — AST 비교로 정확도 계산
r_code = create_taskresult(
    task_id="code_demo_001",
    question="리스트를 정렬하는 파이썬 코드",
    response="sorted_list = sorted(my_list)",
    ground_truth="sorted_list = sorted(my_list)",
    execution_time=1.2,
    task_type="code_generation",
)
print(f"  [Code]    accuracy={r_code.accuracy_score:.3f}  completion={r_code.completion_score:.3f}")

# 도구 호출 — tool_calls 없으면 completion_score=0.6 (부분 완료)
r_tool_no_calls = create_taskresult(
    task_id="tool_demo_001",
    question="날씨 검색해줘",
    response="날씨를 알려드리기 어렵습니다.",
    ground_truth="오늘 서울 날씨는 맑음입니다.",
    execution_time=0.5,
    task_type="tool_use",
)
r_tool_with_calls = create_taskresult(
    task_id="tool_demo_002",
    question="날씨 검색해줘",
    response="오늘 서울 날씨는 맑음 15도입니다.",
    ground_truth="오늘 서울 날씨는 맑음입니다.",
    execution_time=1.8,
    task_type="tool_use",
    tool_calls=[{"tool_name": "weather_api", "success": True}],
)
print(f"  [Tool/no] completion={r_tool_no_calls.completion_score:.3f}  (도구 미사용 → 부분 완료)")
print(f"  [Tool/ok] completion={r_tool_with_calls.completion_score:.3f}  (도구 사용 → 더 높은 완료)")

# 직렬화 / 역직렬화
d = r_qa.to_dict()
from agent_evaluator import TaskResult
r_restored = TaskResult.from_dict(d)
print(f"  직렬화 → 복원: task_id={r_restored.task_id}  accuracy={r_restored.accuracy_score:.3f}")

# ===========================================================================
# 섹션 2: task_type별 데이터 설계 패턴
# ===========================================================================
# 태스크 유형마다 accuracy·completion_score 계산 방식이 다르다.
# 평가 데이터를 설계할 때 task_type을 올바르게 지정해야 한다.
# ===========================================================================
print("\n=== 섹션 2: task_type별 데이터 설계 패턴 ===")

monitor_types = PerformanceMonitor(output_dir=_OUTPUT_DIR)

TYPE_CASES = [
    # (task_type, question, response, ground_truth, tool_calls)
    ("qa",                     "한국 수도?",    "서울",           "서울",         None),
    ("information_retrieval",  "판다스란?",     "데이터 처리 라이브러리", "데이터분석", None),
    ("reasoning",              "2+3×4는?",      "14입니다.",      "14",           None),
    ("planning",               "여행 계획 짜줘","1일차: 서울 도착…","계획서",       None),
    ("creative",               "시 한 편",      "봄이 왔네요…",   "봄 관련 시",   None),
    ("data_analysis",          "매출 분석",     "3월 매출 급증",  "매출 분석",    None),
    ("tool_use",               "파일 읽기",     "파일 내용: abc", "파일 내용",
     [{"tool_name": "file_reader", "success": True}]),
    ("code_generation",        "피보나치 함수", "def fib(n): return n if n<=1 else fib(n-1)+fib(n-2)",
     "def fib(n):", None),
]

for task_type, q, resp, gt, tool_calls in TYPE_CASES:
    kwargs = {
        "task_id": f"type_{task_type[:6]}_{hash(q)%100:03d}",
        "question": q, "response": resp, "ground_truth": gt,
        "execution_time": 1.0, "task_type": task_type,
    }
    if tool_calls:
        kwargs["tool_calls"] = tool_calls
    r = create_taskresult(**kwargs)
    monitor_types.record_task(r)
    print(f"  [{task_type:<22}] acc={r.accuracy_score:.3f}  comp={r.completion_score:.3f}")

print(f"\n  ▶ code_generation은 AST 비교로 구조가 같으면 높은 정확도")
print(f"  ▶ tool_use는 tool_calls 포함 여부와 accuracy에 따라 completion_score가 결정됨")

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
    ("데이터 分析 + 차트 생성",   ["data_analysis", "chart_generator", "web_search"],
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
        p = builder.save_candidates(qa_all,   filename="11_qa_candidates.json")
        print(f"\n  저장: {p}")
    if rag_all:
        p = builder.save_candidates(rag_all,  filename="11_rag_candidates.json")
        print(f"  저장: {p}")
    if tool_all:
        p = builder.save_candidates(tool_all, filename="11_tool_candidates.json")
        print(f"  저장: {p}")

    print("\n  agent-eval dashboard → 케이스 검토 탭에서 승인/거부/병합 가능")

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

# evaluation_session은 with 블록 종료 시 자동으로 save_to_file() 호출
SESSION_TASKS = [
    ("대한민국 수도?",     "서울"),
    ("파이썬 버전 3.12?",  "파이썬 3.12"),
    ("TCP 포트 80번?",     "HTTP"),
]

with evaluation_session("11_session_demo", enable_transparency=True) as session_monitor:
    @agent_eval(session_monitor, task_type="qa", task_id_prefix="sess")
    def _agent(question: str, ground_truth: str = "") -> str:
        return f"응답: {question}"

    for q, gt in SESSION_TASKS:
        _agent(q, ground_truth=gt)

print(f"  evaluation_session 종료 → results/11_session_demo.json 자동 저장")

# ===========================================================================
# 최종 저장
# ===========================================================================
monitor_golden.save_to_file("ch11_eval_data")
print("\n결과 저장 완료: results/ch11_eval_data.json")
print("확인: agent-eval dashboard --results results/")
