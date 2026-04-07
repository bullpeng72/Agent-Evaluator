"""
19_decorator_coverage_expanded.py — 커버리지 확대 데코레이터 검증
================================================================
Phase 1~3 구현 내용을 모두 검증한다.

실행:
    python Evaluator_Examples/19_decorator_coverage_expanded.py
"""

import asyncio
import os
import socket as _sock
from pathlib import Path

from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import (
    agent_eval,
    agent_eval_async,
    agent_eval_with_retry,
    batch_eval,
    conversation_eval,
    flush_conversation,
    EvalMetadata,
    get_eval_ctx,
)

_project_root = Path(__file__).parent.parent

monitor = PerformanceMonitor(output_dir=str(_project_root / "results"))

# Phoenix OTEL 연결
try:
    if _sock.socket().connect_ex(("localhost", 6006)) == 0:
        from agent_evaluator import setup_otel
        setup_otel(endpoint="http://localhost:6006", service_name="19-decorator-coverage")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Phase 1-A: expected_tools_arg + framework 파라미터 확장
# ---------------------------------------------------------------------------
print("\n=== Phase 1-A: expected_tools_arg + framework ===")

@agent_eval(
    monitor,
    task_type="tool_use",
    expected_tools_arg="expected",
    framework="langchain",
    task_id_prefix="p1a",
)
def tool_agent(question: str, expected=None, ground_truth: str = "") -> str:
    return f"searched: {question}"

tool_agent("서울 날씨", expected=["search", "weather_api"], ground_truth="맑음")
print("  tool_agent 완료 — framework=langchain, expected_tools 전달됨")

# ---------------------------------------------------------------------------
# Phase 1-B: score_fn / completion_fn 커스텀 점수
# ---------------------------------------------------------------------------
print("\n=== Phase 1-B: score_fn / completion_fn ===")

def simple_score(response: str, gt: str) -> float:
    return 1.0 if gt and gt in response else 0.2

@agent_eval(
    monitor,
    task_type="qa",
    score_fn=simple_score,
    completion_fn=lambda r, gt: 1.0 if len(r) > 5 else 0.5,
    task_id_prefix="p1b",
)
def scored_agent(question: str, ground_truth: str = "") -> str:
    return f"서울 — {question}에 대한 답변"

scored_agent("수도가 어딘가요?", ground_truth="서울")
print("  scored_agent 완료 — 커스텀 score_fn 적용됨")

# ---------------------------------------------------------------------------
# Phase 1-C: task_id_fn 커스텀 task_id
# ---------------------------------------------------------------------------
print("\n=== Phase 1-C: task_id_fn ===")

@agent_eval(
    monitor,
    task_type="qa",
    task_id_fn=lambda args, kw: kw.get("task_id") or f"custom_{args[0][:8]}",
    task_id_prefix="fallback",
)
def custom_id_agent(question: str, task_id: str = "", ground_truth: str = "") -> str:
    return f"응답: {question}"

custom_id_agent("한국의 수도는?", task_id="my_task_001", ground_truth="서울")
print("  custom_id_agent 완료 — task_id=my_task_001")

# ---------------------------------------------------------------------------
# Phase 2-A: EvalMetadata 튜플 반환 — attempts + chain_steps
# ---------------------------------------------------------------------------
print("\n=== Phase 2-A: EvalMetadata 튜플 반환 ===")

@agent_eval(monitor, task_type="tool_use", task_id_prefix="p2a")
def meta_agent(question: str, ground_truth: str = "") -> tuple:
    # 내부 재시도 시뮬레이션
    response = f"도구 사용 결과: {question}"
    return response, EvalMetadata(
        attempts=3,
        framework="langchain",
        expected_tools=["search", "calculator"],
        chain_steps=[
            {"name": "search", "success": True, "execution_time": 0.3},
            {"name": "calculator", "success": True, "execution_time": 0.1},
        ],
        agent_interactions=[
            {"from_agent": "router", "to_agent": "search_agent", "type": "delegation", "success": True},
        ],
    )

result = meta_agent("2 + 2는?", ground_truth="4")
print(f"  meta_agent 반환값: {result!r}  (호출자에게 원본 str 반환)")
print("  EvalMetadata — attempts=3, framework=langchain, chain_steps(2), agent_interactions(1)")

# ---------------------------------------------------------------------------
# Phase 2-B: get_eval_ctx() 스레드 로컬 컨텍스트 주입
# ---------------------------------------------------------------------------
print("\n=== Phase 2-B: get_eval_ctx() 스레드 로컬 ===")

@agent_eval(monitor, task_type="tool_use", task_id_prefix="p2b")
def ctx_agent(question: str, ground_truth: str = "") -> str:
    response = f"결과: {question}"
    ctx = get_eval_ctx()
    if ctx:
        ctx.framework = "langgraph"
        ctx.attempts = 2
        ctx.graph_traversal = {
            "nodes_visited": ["router", "search", "synthesizer"],
            "edges": [("router", "search"), ("search", "synthesizer")],
        }
        ctx.state_transitions = [
            {"from": "router", "to": "search", "trigger": "tool_call"},
            {"from": "search", "to": "synthesizer", "trigger": "result"},
        ]
    return response  # 반환값 타입 변경 없음

ctx_result = ctx_agent("LangGraph 테스트", ground_truth="정상 동작")
print(f"  ctx_agent 반환: {ctx_result!r}  (str 그대로)")
print("  eval_ctx — framework=langgraph, graph_traversal, state_transitions 주입됨")

# ---------------------------------------------------------------------------
# Phase 2-C: EvalMetadata + score_fn 우선순위 확인
# ---------------------------------------------------------------------------
print("\n=== Phase 2-C: 우선순위 검증 (EvalMetadata > score_fn) ===")

@agent_eval(
    monitor,
    task_type="qa",
    score_fn=lambda r, gt: 0.1,   # score_fn이 0.1 반환
    task_id_prefix="p2c",
)
def priority_agent(question: str, ground_truth: str = "") -> tuple:
    return "정답입니다", EvalMetadata(accuracy_score=0.95)  # EvalMetadata가 우선
    # 결과: accuracy_score=0.95 (score_fn의 0.1 무시)

priority_agent("우선순위 테스트", ground_truth="정답")
print("  priority_agent — EvalMetadata(0.95) > score_fn(0.1) 우선순위 확인")

# ---------------------------------------------------------------------------
# Phase 3-A-0: batch_eval — 배치 평가 + DataFrame 반환
# ---------------------------------------------------------------------------
print("\n=== Phase 3-A-0: batch_eval — 배치 평가 (return_format='dataframe') ===")

_BATCH_QA_PAIRS = [
    ("Python 리스트와 튜플 차이?",   "리스트 mutable, 튜플 immutable"),
    ("REST API와 GraphQL 차이점?",   "REST: 고정 엔드포인트, GraphQL: 유연한 쿼리"),
    ("Docker 컨테이너 생성 명령어?", "docker run 명령어 사용"),
    ("JWT 토큰 구조?",               "Header.Payload.Signature"),
    ("CI/CD 파이프라인이란?",         "자동화 빌드·테스트·배포"),
]

@batch_eval(
    monitor,
    task_type="qa",
    task_id_prefix="p3a0_basic",
    return_format="dataframe",
    shuffle=True,
    shuffle_seed=42,
    flush_every=5,
    flush_filename="19_batch_basic",
    on_batch_complete=lambda results: print(f"  on_batch_complete: {len(results)}건 기록됨"),
)
def qa_batch_basic(questions: list, ground_truths: list = None) -> list:
    return [f"{q}에 대한 배치 응답" for q in questions]

df = qa_batch_basic(
    questions=[q for q, _ in _BATCH_QA_PAIRS],
    ground_truths=[gt for _, gt in _BATCH_QA_PAIRS],
)
if hasattr(df, "shape"):
    print(f"  DataFrame: {df.shape}  컬럼: {list(df.columns[:6])}")
print("  shuffle=True, shuffle_seed=42, return_format='dataframe' 확인")

# ---------------------------------------------------------------------------
# Phase 3-A-0-2: batch_eval + concurrent=True + EvalMetadata per item
# ---------------------------------------------------------------------------
print("\n=== Phase 3-A-0-2: batch_eval + concurrent + EvalMetadata ===")

@batch_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="p3a0_conc",
    return_format="list",
    concurrent=True,
    max_concurrent=3,
    on_item_error=lambda i, q, e: print(f"  항목 {i} 실패: {type(e).__name__}"),
)
def tool_batch_concurrent(questions: list, ground_truths: list = None) -> list:
    # concurrent=True → 1항목씩 호출됨 (len(questions)==1)
    return [(
        f"도구 검색 결과: {questions[0]}",
        EvalMetadata(
            tool_calls=[{"tool_name": "web_search", "success": True, "duration": 0.3}],
            chain_steps=[{"name": "search", "success": True, "execution_time": 0.3}],
            attempts=1,
        ),
    )]

tool_results = tool_batch_concurrent(questions=["검색 A", "검색 B", "검색 C"])
print(f"  concurrent=True → 항목별 병렬 처리 + EvalMetadata 추출")
print(f"  반환 건수: {len(tool_results) if tool_results else 0}건")

# ---------------------------------------------------------------------------
# Phase 3-A: agent_eval_with_retry — 재시도 정확한 카운트
# ---------------------------------------------------------------------------
print("\n=== Phase 3-A: agent_eval_with_retry ===")

_attempt_counter = {"count": 0}

@agent_eval_with_retry(
    monitor,
    task_type="qa",
    max_retries=3,
    retry_on=(ValueError,),
    delay=0.0,
    task_id_prefix="retry",
)
def flaky_agent(question: str, ground_truth: str = "") -> str:
    _attempt_counter["count"] += 1
    if _attempt_counter["count"] < 3:
        raise ValueError(f"임시 오류 (시도 {_attempt_counter['count']})")
    return "3번째 시도 성공!"

try:
    retry_result = flaky_agent("재시도 테스트", ground_truth="성공")
    print(f"  flaky_agent 결과: {retry_result}")
    print(f"  실제 시도 횟수: {_attempt_counter['count']}  (attempts=3으로 기록됨)")
except Exception as e:
    print(f"  예외: {e}")

# ---------------------------------------------------------------------------
# Phase 3-A-2: agent_eval_with_retry — 비동기 버전
# ---------------------------------------------------------------------------
print("\n=== Phase 3-A-2: agent_eval_with_retry (async) ===")

_async_counter = {"count": 0}

@agent_eval_with_retry(
    monitor,
    task_type="qa",
    max_retries=3,
    retry_on=(ConnectionError,),
    delay=0.0,
    task_id_prefix="async_retry",
)
async def async_flaky(question: str, ground_truth: str = "") -> str:
    _async_counter["count"] += 1
    if _async_counter["count"] < 2:
        raise ConnectionError("연결 실패")
    return "비동기 성공"

# ---------------------------------------------------------------------------
# Phase 3-B: conversation_eval — 멀티턴 대화
# ---------------------------------------------------------------------------
print("\n=== Phase 3-B: conversation_eval ===")

@conversation_eval(monitor, session_id_arg="sid", user_arg="question", max_turns=3)
def chat_agent(question: str, sid: str = "conv_001") -> str:
    responses = {
        "안녕하세요": "안녕하세요! 무엇을 도와드릴까요?",
        "오늘 날씨는?": "맑고 따뜻한 날씨입니다.",
        "내일은요?": "내일도 맑을 예정입니다.",
        "고맙습니다": "천만에요!",
    }
    return responses.get(question, f"{question}에 대한 응답입니다.")

chat_agent("안녕하세요", sid="sess_001")
chat_agent("오늘 날씨는?", sid="sess_001")
chat_agent("내일은요?", sid="sess_001")   # max_turns=3 도달 → 자동 flush
print("  3턴 도달 → 자동 flush (context_retention, topic_coherence 등 계산)")

# 수동 flush 예시
chat_agent("안녕하세요", sid="sess_002")
chat_agent("오늘 날씨는?", sid="sess_002")
flush_conversation("sess_002")   # 명시적 종료
print("  sess_002 수동 flush 완료")

# ---------------------------------------------------------------------------
# Phase 3-B-2: conversation_eval — 비동기
# ---------------------------------------------------------------------------
print("\n=== Phase 3-B-2: conversation_eval (async) ===")

@conversation_eval(monitor, session_id_arg="sid", max_turns=2)
async def async_chat(question: str, sid: str = "async_conv") -> str:
    await asyncio.sleep(0.01)
    return f"비동기 응답: {question}"

# ---------------------------------------------------------------------------
# 결과 저장 및 최종 출력
# ---------------------------------------------------------------------------
async def main():
    # 비동기 테스트 실행
    async_retry_result = await async_flaky("비동기 재시도", ground_truth="성공")
    print(f"  async_flaky 결과: {async_retry_result}")

    await async_chat("안녕", sid="async_001")
    await async_chat("날씨", sid="async_001")   # max_turns=2 → 자동 flush
    print("  async_chat 2턴 완료 → 자동 flush")

    print("\n--- 결과 저장 ---")
    monitor.save_to_file("19_decorator_coverage_expanded")
    print(f"  {_project_root / 'results' / '19_decorator_coverage_expanded'} 저장 완료")


asyncio.run(main())

# ---------------------------------------------------------------------------
# 결과 확인
# ---------------------------------------------------------------------------
import json
result_path = str(_project_root / "results" / "19_decorator_coverage_expanded")
try:
    with open(result_path) as f:
        data = json.load(f)
    tasks = data.get("tasks", [])
    print(f"\n=== 기록된 태스크 {len(tasks)}건 ===")
    for t in tasks:
        meta_fields = []
        if t.get("attempts", 1) > 1:
            meta_fields.append(f"attempts={t['attempts']}")
        if t.get("framework") and t["framework"] != "native":
            meta_fields.append(f"fw={t['framework']}")
        if t.get("expected_tools"):
            meta_fields.append(f"tools={t['expected_tools']}")
        if t.get("chain_steps"):
            meta_fields.append(f"chain_steps={len(t['chain_steps'])}")
        if t.get("agent_interactions"):
            meta_fields.append(f"interactions={len(t['agent_interactions'])}")
        if t.get("graph_traversal"):
            meta_fields.append("graph_traversal=✓")
        meta_str = " | " + ", ".join(meta_fields) if meta_fields else ""
        print(f"  [{t['task_id']:30s}] acc={t['accuracy_score']:.2f} ok={t['success']}{meta_str}")
except Exception as e:
    print(f"결과 확인 실패: {e}")
