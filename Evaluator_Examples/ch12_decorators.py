"""
ch12_decorators.py — 데코레이터 전체 API + QuickEval Facade
====================================================================
Book Chapter 12 — 데코레이터 완전정복

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
    python Evaluator_Examples/ch12_decorators.py

결과:
    results/ch12_decorators.json
    results/ch12_version_v1_baseline.json / ch12_version_v2_detailed.json
        (동일 task_id 3건 공유 — agent-eval dashboard의 File Compare →
         Group by: prompt_version / ⚖️ Pairwise Judge 탭 데모용)
    → deprecated 전체 예제: Evaluator_Examples/.deprecated/04_decorator_quickeval.py
"""

import asyncio
from pathlib import Path

# 💡 import 간략화 팁: `import agent_evaluator as ae` 한 줄로
#    PerformanceMonitor · QuickEval · agent_eval · batch_eval · RetryConfig 등
#    모든 Public API를 ae.XXX 형태로 접근 가능.
#
#   import agent_evaluator as ae
#   from agent_evaluator import conversation_eval, flush_conversation, EvalMetadata, get_eval_ctx
#   # 이후: ae.PerformanceMonitor(, use_korean_tokenizer=True)  ae.agent_eval(...)  ae.RetryConfig(...)
from agent_evaluator import (
    PerformanceMonitor, QuickEval, SimpleTaskAlertRule, LLMJudge, setup_otel,
    GoalAlignmentConfig, PlanConfig,
    ConversationSession, ConversationMetrics,
    agent_eval, batch_eval, conversation_eval,
    flush_conversation, EvalMetadata, get_eval_ctx, RetryConfig, LLMJudgeConfig,
    create_taskresult,
)

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch12-decorators")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_transparency=True,           # 투명성 탭: 메트릭 계산 Traces 자동 생성
    use_korean_tokenizer=True,
)

# ===========================================================================
# 섹션 1: @agent_eval 기본 + 파라미터 자동 탐지
# ===========================================================================
print("\n=== 섹션 1: @agent_eval 기본 ===")

@agent_eval(monitor, task_type="qa", task_id_prefix="basic")
def basic_agent(question: str, ground_truth: str = "") -> str:
    """가장 단순한 사용 패턴 — question/ground_truth 자동 탐지."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"답변: {question}"

# 파라미터 이름이 다를 때 명시적 지정
@agent_eval(monitor, task_type="qa",
            question_arg="query", ground_truth_arg="expected",
            task_id_prefix="param")
def custom_param_agent(query: str, expected: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
    auto_save_filename="ch12_quickeval_auto",
)

@eval_qe.qa
def qe_qa_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"QE 답변: {question}"

@eval_qe.tool_use
def qe_tool_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"QE 도구 실행: {question}"

@eval_qe.rag
def qe_rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return context[:80] if context else "컨텍스트 없음"

@eval_qe.code
def qe_code_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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

monitor.save_to_file("ch12_decorators")
print("\n결과 저장 완료: results/ch12_decorators.json")


# ===========================================================================
# 섹션 추가: LLMJudge 직접 사용
# ===========================================================================
# LLMJudge는 ground_truth 없이 completeness·relevance·factual_consistency·
# toxicity·bias 5차원 + RAG faithfulness + G-Eval 커스텀 기준을 LLM으로 채점.
# API 키가 없으면 gracefully skip.
print("\n=== LLMJudge 직접 사용 ===")

try:
    import os
    _has_key = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))
    if not _has_key:
        print("  API 키 없음 — LLMJudge 섹션 skip (ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 필요)")
    else:
        # ── API 키 유효성 사전 확인 (401/403 방지) ─────────────────────────
        judge = LLMJudge(
            model=None,          # None → API 키 기반 자동 결정
            sample_rate=1.0,     # 100% 채점 (프로덕션에서는 0.1 권장)
        )
        _ping = judge.judge("ping", question="test", response="test")
        if _ping.get("error"):
            _err_msg = str(_ping["error"])
            print("  API 키 인증 실패 — LLMJudge 섹션 skip")
            print(f"  오류: {_err_msg[:120]}")
            print("  해결: .env 파일에 유효한 ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 설정")
        else:
            # ── 기본 5차원 채점 ────────────────────────────────────────────
            result = judge.judge(
                task_id="llm_judge_001",
                question="한국의 수도는 어디인가요?",
                response="서울입니다. 서울은 약 950만 명이 거주하는 대한민국의 수도입니다.",
            )
            scores = result.get("scores") or {}
            if result.get("error"):
                print(f"  기본 채점 오류: {result['error']}")
            else:
                print(f"  기본 채점 — overall: {scores.get('overall', 0):.2f}")
                print(f"    completeness={scores.get('completeness',0)}  "
                      f"relevance={scores.get('relevance',0)}  "
                      f"factual_consistency={scores.get('factual_consistency',0)}")
                safety = scores.get("safety_score")
                if safety is not None:
                    print(f"    safety_score={safety:.2f}  (1.0=완전 안전)")

            # ── RAG Faithfulness 채점 (Ragas 대체) ─────────────────────────
            rag_result = judge.judge(
                task_id="llm_judge_rag",
                question="서울의 인구는?",
                response="서울의 인구는 약 950만 명입니다.",
                context="서울은 대한민국의 수도로 인구 약 950만 명이 거주합니다.",
            )
            rag_scores = rag_result.get("scores") or {}
            faithfulness = rag_scores.get("faithfulness")
            if faithfulness is not None:
                print(f"\n  RAG Faithfulness: {faithfulness}/5 (5=모든 주장이 컨텍스트에 근거)")

            # ── G-Eval 커스텀 기준 채점 (DeepEval 대체) ───────────────────
            geval_judge = LLMJudge(
                model=None,
                judge_criteria=["medical_accuracy", "citation_quality"],
            )
            geval_result = geval_judge.judge(
                task_id="llm_judge_geval",
                question="아스피린의 주요 부작용은?",
                response="아스피린은 위장 출혈 위험이 있으며 혈소판 응집을 억제합니다.",
            )
            geval_scores = geval_result.get("scores") or {}
            criteria_scores = geval_scores.get("criteria_scores") or {}
            criteria_overall = geval_scores.get("criteria_overall")
            if criteria_scores:
                print(f"\n  G-Eval 커스텀 기준:")
                for k, v in criteria_scores.items():
                    print(f"    {k}: {v}/5")
                if criteria_overall is not None:
                    print(f"    criteria_overall: {criteria_overall:.2f}")

            # ── 개선 2: AGENT_EVALUATOR_JUDGE_PROVIDER — 모델 우선순위 제어 ─
            # .env 또는 환경변수에 AGENT_EVALUATOR_JUDGE_PROVIDER=anthropic 으로 설정하면
            # 양쪽 키가 모두 있어도 Anthropic을 우선 사용한다.
            import os as _os
            _provider = _os.getenv("AGENT_EVALUATOR_JUDGE_PROVIDER", "auto")
            print(f"\n  [개선 2] 현재 AGENT_EVALUATOR_JUDGE_PROVIDER={_provider!r}")
            print(f"    → 실제 선택된 모델: {judge.model}")
            print(f"    (변경하려면: AGENT_EVALUATOR_JUDGE_PROVIDER=anthropic|openai|auto)")

            # ── 개선 3: GoalAlignmentConfig.llm_blend_weight ─────────────
            # use_llm_scoring=True 일 때 rule-based 점수와 LLM relevance 점수를
            # 가중 블렌딩한다. 0.8 = LLM 80%, rule 20%.
            _blend_monitor = PerformanceMonitor(
                output_dir=_OUTPUT_DIR,
                enable_llm_judge=True,
                judge_model=None,
                use_korean_tokenizer=True,
            )

            @agent_eval(
                _blend_monitor,
                task_type="tool_use",
                task_id_prefix="blend",
                goal_alignment=GoalAlignmentConfig(
                    goal_tool_map={"검색": ["web_search"]},
                    use_llm_scoring=True,
                    llm_blend_weight=0.8,   # LLM 판단 80%, rule 20% 반영
                ),
            )
            def blended_agent(question: str, ground_truth: str = "") -> str:
                return f"web_search 결과: {question}에 대한 검색 완료"

            blended_agent("최신 AI 논문을 검색해줘", ground_truth="검색 결과")
            print(f"\n  [개선 3] GoalAlignmentConfig(llm_blend_weight=0.8) 적용됨")
            print(f"    → goal_alignment 점수 = rule*0.2 + LLM_relevance*0.8")
            print(f"    PlanConfig도 동일하게 llm_blend_weight 지원")

            # ── 개선 4: ajudge() — 비동기 진입점 ────────────────────────
            # async def 에이전트에서 이벤트 루프 블로킹 없이 채점할 때 사용.
            async def _run_async_judge():
                async_judge = LLMJudge(model=None, sample_rate=1.0)
                result = await async_judge.ajudge(
                    task_id="llm_judge_async",
                    question="서울의 인구는?",
                    response="약 950만 명입니다.",
                )
                return result

            async_result = asyncio.run(_run_async_judge())
            async_scores = async_result.get("scores") or {}
            if async_result.get("error"):
                print(f"\n  [개선 4] ajudge() 오류: {async_result['error']}")
            else:
                print(f"\n  [개선 4] ajudge() (비동기) overall={async_scores.get('overall', 0):.2f}")
                print(f"    → asyncio.run_in_executor로 sync judge()를 스레드 풀 실행")
                print(f"    → async def 에이전트에서 await judge.ajudge(...) 사용 권장")

            # ── @agent_eval LLMJudgeConfig(sample_rate=...) 연동 확인 ─────
            # 이전에 sample_rate이 LLMJudge 인스턴스에 연결되지 않던 버그가 수정됨.
            _sr_monitor = PerformanceMonitor(
                output_dir=_OUTPUT_DIR,
                enable_llm_judge=True,
                judge_model=None,
                judge_sample_rate=1.0,
                use_korean_tokenizer=True,
            )

            @agent_eval(
                _sr_monitor,
                task_type="qa",
                task_id_prefix="sr_test",
                llm_judge=LLMJudgeConfig(model=None, sample_rate=0.0),  # 0% → 항상 skip
            )
            def sr_agent(question: str, ground_truth: str = "") -> str:
                return "테스트 응답"

            sr_agent("테스트 질문", ground_truth="테스트")
            _sr_tasks = _sr_monitor.tcr_tracker.tasks
            _sr_judged = [t for t in _sr_tasks if (t.extra or {}).get("llm_judge") and
                          not (t.extra or {})["llm_judge"].get("skipped")]
            print(f"\n  [버그 수정] LLMJudgeConfig(sample_rate=0.0) → 채점된 태스크: {len(_sr_judged)}건 (0이어야 함)")

except Exception as _e:
    print(f"  LLMJudge 실행 중 오류 (skip): {_e}")

# ===========================================================================
# 섹션 추가: ConversationSession 직접 사용
#
# @conversation_eval 데코레이터가 내부적으로 관리하는 ConversationSession을
# 직접 인스턴스화해 멀티턴 대화 지표를 계산합니다.
#
# 패턴 1 — 직접 생성:
#   session = ConversationSession("s_001")
#   session.add_turn(user=..., agent=..., metadata={...})
#   metrics = session.compute_metrics()
#
# 패턴 2 — PerformanceMonitor 컨텍스트 매니저:
#   with monitor.conversation("session_001") as conv:
#       conv.turn(user=..., agent=...)
#
# ConversationMetrics 필드:
#   turn_count, overall_score, context_retention, topic_coherence
#   progressive_depth, session_completion, avg_turn_latency, score_stddev
# ===========================================================================
print("\n=== 섹션 추가: ConversationSession 직접 사용 ===")

# ── 패턴 1: 직접 생성 + add_turn() ──────────────────────────────────────────
print("  [1] ConversationSession — 직접 생성")
session = ConversationSession("cs_demo_001")
session.add_turn(
    user="안녕하세요. 파이썬 학습을 시작하고 싶어요.",
    agent="반갑습니다! 파이썬은 배우기 쉬운 언어입니다. 변수와 자료형부터 시작하면 좋습니다.",
    metadata={"latency": 0.42},
)
session.add_turn(
    user="변수와 자료형이란 정확히 무엇인가요?",
    agent="변수는 값을 저장하는 공간이고, 자료형은 정수·문자열·리스트 등 값의 종류입니다.",
    metadata={"latency": 0.38},
)
session.add_turn(
    user="리스트와 딕셔너리의 차이는 무엇인가요?",
    agent="리스트는 순서가 있는 값의 모음이고, 딕셔너리는 키-값 쌍으로 이루어진 매핑 자료형입니다.",
    metadata={"latency": 0.45},
)
session.add_turn(
    user="파이썬으로 간단한 계산기를 만들 수 있나요?",
    agent="네! 파이썬으로 사칙연산 계산기를 만들 수 있습니다. 함수와 조건문을 활용하면 됩니다.",
    metadata={"latency": 0.51},
)

metrics: ConversationMetrics = session.compute_metrics()
print(f"    세션ID: {session.session_id}  턴 수: {metrics.turn_count}")
print(f"    overall_score={metrics.overall_score:.3f}  stddev={metrics.score_stddev:.3f}")
print(f"    context_retention={metrics.context_retention:.3f}  "
      f"topic_coherence={metrics.topic_coherence:.3f}")
print(f"    progressive_depth={metrics.progressive_depth:.3f}  "
      f"session_completion={metrics.session_completion:.3f}")
if metrics.avg_turn_latency:
    print(f"    avg_turn_latency={metrics.avg_turn_latency:.3f}s")

# ── 패턴 2: PerformanceMonitor 컨텍스트 매니저 ──────────────────────────────
print("  [2] monitor.conversation() 컨텍스트 매니저")
try:
    with monitor.conversation("cs_demo_002") as conv:
        conv.turn(user="머신러닝이란 무엇인가요?",
                  agent="머신러닝은 데이터로부터 패턴을 학습하는 AI 기술입니다.")
        conv.turn(user="지도학습과 비지도학습의 차이는?",
                  agent="지도학습은 정답 레이블이 있는 데이터로, 비지도학습은 레이블 없이 패턴만으로 학습합니다.")
        conv.turn(user="실무에서 가장 많이 쓰이는 알고리즘은?",
                  agent="분류에는 랜덤포레스트·XGBoost, 회귀에는 선형회귀, 군집에는 K-Means가 널리 쓰입니다.")
    print("    cs_demo_002: 3턴 → 자동 지표 계산 + monitor 기록")
except Exception as _e:
    print(f"    컨텍스트 매니저 오류 (skip): {_e}")

print(f"  @conversation_eval vs ConversationSession 직접 사용 비교:")
print(f"    @conversation_eval  → session_id·turn 자동 관리, flush_conversation() 수동 종료")
print(f"    ConversationSession → add_turn() 직접 호출, compute_metrics() 직접 실행")

# ===========================================================================
# 섹션 추가: 버전 비교(Version-Aware Comparison) + Pairwise Judge (v0.9.8+)
#
# 같은 질문 세트를 서로 다른 prompt_version으로 두 번 실행해 별도 결과 파일로
# 저장하면, agent-eval dashboard의 File Compare 탭에서:
#   - "Group by: prompt_version" → 태그별 최신 파일을 자동으로 골라준다
#   - "⚖️ Pairwise Judge" 탭     → task_id가 일치하는 두 파일을 LLM Judge로 A/B 비교한다
# 실제로 확인할 수 있다.
#
# 주의: task_id가 서로 다른 두 결과 파일(예: 서로 다른 챕터 예제)을 비교하면
# 공통 task가 없어 "0 common task(s) judged"만 나온다 — 아래처럼 두 실행이
# 반드시 같은 task_id를 공유해야 Pairwise Judge가 실제 결과를 낸다.
# ===========================================================================
print("\n=== 섹션 추가: 버전 비교(prompt_version) + Pairwise Judge ===")

_VERSION_QA_CASES = [
    ("vcmp_q1", "한국의 수도는 어디인가요?", "서울"),
    ("vcmp_q2", "파이썬의 창시자는 누구인가요?", "귀도 반 로섬"),
    ("vcmp_q3", "TCP와 UDP의 차이점은?", "TCP는 연결 지향, UDP는 비연결"),
]


def baseline_prompt_agent(task_id: str) -> str:
    """v1-baseline: 근거 없이 한 줄짜리 짧은 답변만 반환."""
    # TODO(현업 적용): 아래 Mock 대신 짧게 답하라는 system prompt로 LLM을 호출하세요.
    answers = {
        "vcmp_q1": "서울.",
        "vcmp_q2": "귀도 반 로섬.",
        "vcmp_q3": "TCP는 연결형, UDP는 비연결형입니다.",
    }
    return answers.get(task_id, "모름")


def detailed_prompt_agent(task_id: str) -> str:
    """v2-detailed: 근거를 덧붙인 상세 답변을 반환 — baseline과의 품질 차이를 의도적으로 만든다."""
    # TODO(현업 적용): 아래 Mock 대신 "이유를 함께 설명하라"는 system prompt로 LLM을 호출하세요.
    answers = {
        "vcmp_q1": "한국의 수도는 서울입니다. 서울은 인구 약 950만 명의 대한민국 최대 도시입니다.",
        "vcmp_q2": "파이썬은 귀도 반 로섬(Guido van Rossum)이 1991년에 처음 발표한 프로그래밍 언어입니다.",
        "vcmp_q3": "TCP는 연결 지향 프로토콜로 신뢰성을 보장하고, UDP는 비연결 프로토콜로 속도를 우선합니다.",
    }
    return answers.get(task_id, "모름")


monitor_v1 = PerformanceMonitor(output_dir=_OUTPUT_DIR, prompt_version="v1-baseline")
monitor_v2 = PerformanceMonitor(output_dir=_OUTPUT_DIR, prompt_version="v2-detailed")

for _task_id, _question, _ground_truth in _VERSION_QA_CASES:
    monitor_v1.record_task(create_taskresult(
        task_id=_task_id, question=_question,
        response=baseline_prompt_agent(_task_id), ground_truth=_ground_truth,
        execution_time=0.5,
    ))
    monitor_v2.record_task(create_taskresult(
        task_id=_task_id, question=_question,
        response=detailed_prompt_agent(_task_id), ground_truth=_ground_truth,
        execution_time=0.8,
    ))

monitor_v1.save_to_file("ch12_version_v1_baseline")
monitor_v2.save_to_file("ch12_version_v2_detailed")
_version_task_ids = [c[0] for c in _VERSION_QA_CASES]
print("  결과 저장: results/ch12_version_v1_baseline.json (prompt_version=v1-baseline)")
print("  결과 저장: results/ch12_version_v2_detailed.json (prompt_version=v2-detailed)")
print(f"  → 두 파일은 동일한 task_id {_version_task_ids}를 공유하므로,")
print("    agent-eval dashboard의 File Compare → Pairwise Judge 탭에서 실제 비교가 가능하다.")

# ── judge_pairwise() 직접 호출 (API 키 있을 때만 — 없으면 gracefully skip) ──
try:
    import os as _os_pw
    if bool(_os_pw.getenv("ANTHROPIC_API_KEY") or _os_pw.getenv("OPENAI_API_KEY")):
        pairwise_judge = LLMJudge(model=None)
        _pw_task_id, _pw_question, _ = _VERSION_QA_CASES[0]
        pw_result = pairwise_judge.judge_pairwise(
            question=_pw_question,
            response_a=baseline_prompt_agent(_pw_task_id),
            response_b=detailed_prompt_agent(_pw_task_id),
        )
        if pw_result.get("error"):
            print(f"  judge_pairwise() 오류: {pw_result['error']}")
        else:
            print(f"  judge_pairwise() 직접 호출 — winner={pw_result.get('winner')}  "
                  f"swap_check={pw_result.get('swap_check')}")
    else:
        print("  API 키 없음 — judge_pairwise() 직접 호출 데모 skip")
except Exception as _e:
    print(f"  judge_pairwise() 실행 중 오류 (skip): {_e}")

print("  확인: agent-eval dashboard → File Compare → \"Group by: prompt_version\" 또는")
print("        ch12_version_v1_baseline / ch12_version_v2_detailed 수동 선택 → ⚖️ Pairwise Judge")
