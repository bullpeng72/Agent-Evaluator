"""
04_decorator_quickeval.py — 데코레이터 전체 API + QuickEval Facade
====================================================================
agent_eval / batch_eval / conversation_eval 의 모든 옵션과
QuickEval 원스톱 Facade를 한 파일에서 시연한다.

  @agent_eval 고급:
    - score_fn / completion_fn 커스텀 점수
    - task_id_fn 커스텀 task ID
    - flush_every 주기 저장
    - retry=RetryConfig(max, on, delay, backoff)
    - alert_rules (SimpleTaskAlertRule)
    - EvalMetadata 튜플 반환 (우선순위: EvalMetadata > score_fn)
    - get_eval_ctx() 스레드 로컬 주입

  @batch_eval:
    - concurrency=N (병렬 항목 실행)
    - return_format="dataframe" | "list"
    - on_batch_complete / on_item_error

  @conversation_eval:
    - max_turns 자동 flush
    - flush_conversation 수동 종료
    - async 지원

  QuickEval Facade:
    - @eval.qa / @eval.tool_use / @eval.rag / @eval.code
    - gate() CI/CD 품질 게이팅
    - summary() 집계 결과

의존성:
    필수: pip install agent-evaluator          (numpy·pandas·python-dotenv 포함)
    선택: agent-eval monitor                   (Phoenix OTEL 시각화 — 없어도 실행됨)

실행:
    python Evaluator_Examples/04_decorator_quickeval.py

결과:
    results/04_decorator_quickeval.json
"""

import asyncio
from pathlib import Path

from agent_evaluator import PerformanceMonitor, QuickEval, SimpleTaskAlertRule, setup_otel
from agent_evaluator.decorators import (
    agent_eval, batch_eval, conversation_eval,
    flush_conversation, EvalMetadata, get_eval_ctx, RetryConfig,
)

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="04-decorators-quickeval")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

monitor = PerformanceMonitor(output_dir=_OUTPUT_DIR)

# ===========================================================================
# 섹션 1: @agent_eval 기본 + 파라미터 자동 탐지
# ===========================================================================
print("\n=== 섹션 1: @agent_eval 기본 ===")

@agent_eval(monitor, task_type="qa", task_id_prefix="basic")
def basic_agent(question: str, ground_truth: str = "") -> str:
    """가장 단순한 사용 패턴 — question/ground_truth 자동 탐지."""
    return f"답변: {question}"

# 파라미터 이름이 다를 때 명시적 지정
@agent_eval(monitor, task_type="qa",
            question_arg="query", ground_truth_arg="expected",
            task_id_prefix="param")
def custom_param_agent(query: str, expected: str = "") -> str:
    return f"응답: {query}"

basic_agent("대한민국의 수도는?", ground_truth="서울")
custom_param_agent(query="파이썬의 창시자는?", expected="귀도 반 로섬")
print("  기본 패턴 2건 완료")

# ===========================================================================
# 섹션 2: 커스텀 score_fn / completion_fn
# ===========================================================================
print("\n=== 섹션 2: 커스텀 score_fn / completion_fn ===")

def keyword_score(response: str, ground_truth: str) -> float:
    """응답에 핵심 키워드가 포함되면 가점."""
    keywords = ground_truth.lower().split()
    matches = sum(1 for kw in keywords if kw in response.lower())
    return min(1.0, matches / max(len(keywords), 1))

@agent_eval(
    monitor, task_type="qa",
    score_fn=keyword_score,
    completion_fn=lambda r, gt: 1.0 if len(r) > 10 else 0.5,
    task_id_prefix="score_fn",
)
def scored_agent(question: str, ground_truth: str = "") -> str:
    return f"서울은 대한민국의 수도이자 최대 도시입니다. — {question} 답변"

scored_agent("한국의 수도에 대해 설명해줘", ground_truth="서울 대한민국 수도")
print("  keyword_score 적용 완료")

# ===========================================================================
# 섹션 3: EvalMetadata 튜플 반환 (우선순위: EvalMetadata > score_fn)
# ===========================================================================
print("\n=== 섹션 3: EvalMetadata 튜플 반환 ===")

@agent_eval(
    monitor, task_type="tool_use",
    score_fn=lambda r, gt: 0.1,   # score_fn은 0.1을 반환하지만 EvalMetadata에 의해 무시됨
    task_id_prefix="meta",
)
def meta_agent(question: str, ground_truth: str = "") -> tuple:
    response = f"도구 실행 결과: {question}"
    return response, EvalMetadata(
        accuracy_score=0.92,          # score_fn보다 우선
        attempts=3,
        framework="langchain",
        expected_tools=["search", "calculator"],
        tool_calls=[
            {"tool_name": "search",     "success": True,  "duration": 0.5},
            {"tool_name": "calculator", "success": True,  "duration": 0.1},
        ],
        chain_steps=[
            {"name": "retrieve",   "success": True, "execution_time": 0.5},
            {"name": "synthesize", "success": True, "execution_time": 0.3},
        ],
        agent_interactions=[
            {"from_agent": "router", "to_agent": "search_agent", "type": "delegation", "success": True},
        ],
    )

raw = meta_agent("검색 후 계산해줘", ground_truth="계산 완료")
print(f"  EvalMetadata(0.92) > score_fn(0.1) 우선순위 확인  반환값 타입: {type(raw).__name__}")

# ===========================================================================
# 섹션 4: get_eval_ctx() 스레드 로컬 주입
# ===========================================================================
print("\n=== 섹션 4: get_eval_ctx() 스레드 로컬 ===")

@agent_eval(monitor, task_type="planning", task_id_prefix="ctx")
def ctx_agent(question: str, ground_truth: str = "") -> str:
    response = f"그래프 실행 완료: {question}"
    ctx = get_eval_ctx()
    if ctx:
        ctx.framework = "langgraph"
        ctx.attempts  = 2
        ctx.graph_traversal = {
            "nodes_visited": ["router", "search", "synthesizer"],
            "edges": [("router", "search"), ("search", "synthesizer")],
        }
        ctx.state_transitions = [
            {"from": "router", "to": "search",      "trigger": "tool_call"},
            {"from": "search", "to": "synthesizer", "trigger": "result"},
        ]
    return response   # 반환 타입 변경 없음

ctx_agent("LangGraph 워크플로우 테스트", ground_truth="성공")
print("  get_eval_ctx()로 graph_traversal·state_transitions 주입 완료")

# ===========================================================================
# 섹션 5: retry=RetryConfig + flush_every + alert_rules
# ===========================================================================
print("\n=== 섹션 5: retry=RetryConfig + flush_every + alert_rules ===")

slow_alert = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 3.0,
    handler=lambda msg, tr: print(f"  [ALERT] {msg}"),
    severity="warning",
    cooldown=0,
)

_retry_count = {"n": 0}

@agent_eval(
    monitor, task_type="qa",
    retry=RetryConfig(max=3, on=(ValueError,), delay=0.0),
    flush_every=5,
    alert_rules=[slow_alert],
    task_id_prefix="retry",
)
def flaky_agent(question: str, ground_truth: str = "") -> str:
    _retry_count["n"] += 1
    if _retry_count["n"] < 3:
        raise ValueError(f"임시 오류 (시도 {_retry_count['n']})")
    return "3번째 성공!"

result = flaky_agent("재시도 테스트", ground_truth="성공")
print(f"  결과: {result}  (attempts={_retry_count['n']})")

# ===========================================================================
# 섹션 6: @batch_eval (concurrency + DataFrame)
# ===========================================================================
print("\n=== 섹션 6: @batch_eval 고급 ===")

BATCH_DATA = [
    ("TCP와 UDP의 차이점은?",   "TCP: 연결 지향, UDP: 비연결"),
    ("REST API란?",             "HTTP 기반 아키텍처 스타일"),
    ("Git rebase란?",           "커밋 히스토리 재작성"),
    ("Docker와 VM의 차이?",     "Docker: 컨테이너, VM: 가상화"),
    ("CI/CD란?",               "지속적 통합/배포 자동화"),
]

@batch_eval(
    monitor, task_type="qa",
    task_id_prefix="batch_basic",
    return_format="dataframe",
    flush_every=5,
    on_batch_complete=lambda r: print(f"  on_batch_complete: {len(r)}건"),
)
def qa_batch(questions: list, ground_truths: list = None) -> list:
    return [f"{q}에 대한 배치 응답" for q in questions]

df = qa_batch(
    questions=[q for q, _ in BATCH_DATA],
    ground_truths=[gt for _, gt in BATCH_DATA],
)
if hasattr(df, "shape"):
    print(f"  DataFrame: {df.shape}  컬럼: {list(df.columns[:5])}")

# 병렬 배치 (concurrency=3)
@batch_eval(
    monitor, task_type="tool_use",
    task_id_prefix="batch_concurrent",
    return_format="list",
    concurrency=3,
    on_item_error=lambda i, q, e: print(f"  항목 {i} 오류: {type(e).__name__}"),
)
def tool_batch(questions: list, ground_truths: list = None) -> list:
    return [(f"도구 실행: {questions[0]}", EvalMetadata(
        tool_calls=[{"tool_name": "web_search", "success": True, "duration": 0.3}],
    ))]

concurrent_results = tool_batch(questions=["검색 A", "검색 B", "검색 C"])
print(f"  concurrent 배치: {len(concurrent_results)}건 완료")

# ===========================================================================
# 섹션 7: @conversation_eval + async
# ===========================================================================
print("\n=== 섹션 7: @conversation_eval ===")

@conversation_eval(monitor, session_id_arg="sid", user_arg="question", max_turns=3)
def chat(question: str, sid: str = "default") -> str:
    scripts = {
        "안녕":       "안녕하세요!",
        "이름이 뭐야": "저는 AI 어시스턴트입니다.",
        "잘 있어":    "네, 안녕히 계세요!",
    }
    return scripts.get(question, f"{question}에 대한 응답")

chat("안녕",       sid="conv_001")
chat("이름이 뭐야", sid="conv_001")
chat("잘 있어",    sid="conv_001")   # 3턴 → 자동 flush
print("  conv_001: 3턴 → 자동 flush")

@conversation_eval(monitor, session_id_arg="sid", max_turns=10)
async def async_chat(question: str, sid: str = "async") -> str:
    await asyncio.sleep(0.01)
    return f"비동기: {question}"

async def _conv_async():
    await async_chat("비동기 질문 1", sid="conv_async")
    await async_chat("비동기 질문 2", sid="conv_async")
    flush_conversation("conv_async")
    print("  conv_async: 2턴 후 수동 flush")

asyncio.run(_conv_async())

# ===========================================================================
# 섹션 8: QuickEval Facade — 원스톱 간편 시작
# ===========================================================================
print("\n=== 섹션 8: QuickEval Facade ===")

eval_qe = QuickEval(
    output_dir=_OUTPUT_DIR,
    auto_save=True,
    auto_save_interval=5,
    auto_save_filename="04_quickeval_auto",
)

@eval_qe.qa
def qe_qa_agent(question: str, ground_truth: str = "") -> str:
    return f"QE 답변: {question}"

@eval_qe.tool_use
def qe_tool_agent(question: str, ground_truth: str = "") -> str:
    return f"QE 도구 실행: {question}"

@eval_qe.rag
def qe_rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return context[:80] if context else "컨텍스트 없음"

@eval_qe.code
def qe_code_agent(question: str, ground_truth: str = "") -> str:
    return "def solution(): pass"

QE_CASES = [
    ("한국의 국화는?",    "무궁화"),
    ("OS란 무엇인가?",   "운영체제"),
    ("TCP 포트란?",      "포트 번호"),
]

for q, gt in QE_CASES:
    qe_qa_agent(q, ground_truth=gt)
    qe_tool_agent(q, ground_truth=gt)

qe_rag_agent(
    "한국의 수도는?",
    context="서울은 대한민국의 수도입니다. 인구는 약 950만 명입니다.",
    ground_truth="서울",
)
qe_code_agent("빈 함수를 작성해줘", ground_truth="def solution(): pass")

print(f"  QuickEval: {repr(eval_qe)}")

# gate() — 임계값 미충족 시 경고 (sys.exit 방지를 위해 try/except)
try:
    eval_qe.gate(tcr=50, accuracy=30)
    print("  gate() 통과")
except SystemExit as e:
    print(f"  gate() 실패 (코드 {e.code}) — 임계값 미충족")

# summary()
try:
    sm = eval_qe.summary()
    # summary() 값은 0-100 스케일 (% 단위)
    print(f"  summary(): tcr={sm.get('tcr', 0):.1f}%  accuracy={sm.get('accuracy', 0):.1f}%")
except Exception:
    pass

eval_qe.save()
print("  QuickEval.save() 완료 (quickeval.json + .html)")

# ===========================================================================
# 최종 리포트 & 저장
# ===========================================================================
print("\n=== 최종 리포트 ===")

report = monitor.generate_report().to_dict()
total  = report.get("total_tasks", 0)
tcr    = report.get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0) / 100
print(f"  PerformanceMonitor 기록: {total}건  TCR: {tcr:.1%}")

monitor.save_to_file("04_decorator_quickeval")
print("\n결과 저장 완료: results/04_decorator_quickeval.json")
