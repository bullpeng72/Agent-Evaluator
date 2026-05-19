"""
ch04_group_a.py — Gate A: Goal Achievement
===========================================
Book Chapter 04 — Gate A: Goal Achievement

InstructionConfig, GoalAlignmentConfig, PlanConfig, SubtaskConfig,
ContextRetentionConfig, KnowledgeRetentionConfig — 6개 Config 전체 시연.

역케이스(_monitor_a_fail)로 Gate A FAIL 유도 비교도 포함한다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch04_group_a.py

결과:
    results/ch04_group_a.json  (+ .html)
    → 전체 33개 Config 통합 예제: Evaluator_Examples/.deprecated/08_harness_eval.py
"""

import json
import socket
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    create_taskresult,
    setup_otel,
    # Group A — Goal Achievement
    InstructionConfig,
    GoalAlignmentConfig,
    PlanConfig,
    SubtaskConfig,
    ContextRetentionConfig,
    KnowledgeRetentionConfig,
)
from agent_evaluator.decorators import agent_eval

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch04-group-a")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Gate A 전용 monitor
# ---------------------------------------------------------------------------
monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_hallucination_detection=False,
    enable_security_metrics=False,
    enable_transparency=True,
    enable_llm_judge=bool(__import__("os").getenv("ANTHROPIC_API_KEY") or __import__("os").getenv("OPENAI_API_KEY")),
    judge_model=None,
    judge_sample_rate=1.0,
)

# ===========================================================================
# 섹션 1: Group A — Goal Achievement
# ===========================================================================
print("\n=== 섹션 1: Group A — Goal Achievement ===")


@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="a_instruction",
    instructions=InstructionConfig(
        expected_format="json",
        required_keywords=["result", "confidence"],
        min_chars=20,
    ),
)
def instruction_agent(question: str, ground_truth: str = "") -> str:
    """응답 형식·키워드 준수 에이전트 (mock)."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return json.dumps({"result": f"{question}에 대한 답변", "confidence": 0.92})


@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="a_goal",
    goal_alignment=GoalAlignmentConfig(
        goal_tool_map={"분析": ["analyze_tool", "search"]},
        alignment_threshold=0.5,
        # LLM Judge와 rule-based 점수를 가중 블렌딩 (개선 3)
        # enable_llm_judge=True + use_llm_scoring=True 조합 시 Gate A 점수에 반영됨
        # llm_blend_weight: 0.0=rule only, 1.0=LLM only, 0.5=50:50(기본)
        use_llm_scoring=True,
        llm_blend_weight=0.5,
    ),
)
def goal_aligned_agent(question: str, ground_truth: str = "") -> str:
    """목표-도구 정렬 에이전트 (mock)."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"분析 결과: {question}에 대한 검색 및 분析 완료"


@agent_eval(
    monitor,
    task_type="planning",
    task_id_prefix="a_plan",
    plan_tracking=PlanConfig(
        check_goal_coverage=True,
        min_steps=2,
        available_tools=["search", "analyze"],
        # LLM Judge relevance와 rule-based plan score를 블렌딩 (개선 3)
        use_llm_scoring=True,
        llm_blend_weight=0.5,
    ),
)
def plan_agent(question: str, ground_truth: str = "") -> str:
    """계획 일관성 에이전트 (mock)."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    plan = {
        "plan": {
            "steps": [
                {"name": "search", "tool": "search", "description": "정보 검색"},
                {"name": "analyze", "tool": "analyze", "description": "결과 分析"},
                {"name": "summarize", "tool": "analyze", "description": "요약 작성"},
            ]
        }
    }
    return json.dumps(plan)


@agent_eval(
    monitor,
    task_type="planning",
    task_id_prefix="a_subtask",
    subtask_tracking=SubtaskConfig(
        expected_subtasks=["데이터 수집", "분析", "요약"],
        min_completion_rate=0.7,
    ),
)
def subtask_agent(question: str, ground_truth: str = "") -> str:
    """하위 작업 완료율 에이전트 (mock)."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return "데이터 수집 완료, 分析 완료, 요약 작성 완료"


# ── 갭 보완: ContextRetentionConfig · KnowledgeRetentionConfig ─────────────────
# Gate A 점수는 최대 7개 sub-score(TCR·instruction·goal·plan·subtask·context·knowledge)
# 의 평균이다. 이 두 Config 없이는 다중 턴 컨텍스트 유지 능력이 반영되지 않는다.

@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="a_context_ret",
    context_retention=ContextRetentionConfig(
        key_entities=["GPT-4", "Claude", "Gemini"],  # 응답에 재등장해야 할 핵심 엔티티
        retention_threshold=0.5,                      # 엔티티 재등장 비율 임계값
    ),
)
def context_retaining_agent(question: str, ground_truth: str = "") -> str:
    """컨텍스트 유지 에이전트 — 이전 대화의 핵심 엔티티를 응답에 재참조."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return (
        f"이전 대화에서 언급된 GPT-4와 Claude, Gemini를 바탕으로 답변합니다. "
        f"'{question}'에 대해: 세 모델 모두 강력한 추론 능력을 갖추며, "
        f"GPT-4·Claude·Gemini 각각의 강점이 다릅니다."
    )


@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="a_knowledge_ret",
    knowledge_retention=KnowledgeRetentionConfig(
        # 이후 응답에서 재등장해야 할 사전 사실 목록
        facts_to_retain=["GPT-4", "OpenAI", "Claude", "Anthropic"],
        retention_threshold=0.5,
    ),
)
def knowledge_retaining_agent(question: str, ground_truth: str = "") -> str:
    """지식 보존 에이전트 — 초기 주입된 사실을 응답에 재활용."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return (
        f"GPT-4는 OpenAI가 개발한 모델이고, Claude는 Anthropic이 개발한 모델입니다. "
        f"'{question}'에 대해: 두 모델 모두 2024년 이후 주요 벤치마크에서 우수한 성능을 보입니다."
    )


# 섹션 1 실행
GOAL_CASES = [
    ("데이터 분析 보고서를 작성해줘", "분析 결과"),
    ("시장 트렌드를 검색하고 분析해줘", "트렌드 분析"),
    ("프로젝트 계획을 세워줘", "계획 수립"),
]

for q, gt in GOAL_CASES:
    instruction_agent(q, ground_truth=gt)
    goal_aligned_agent(q, ground_truth=gt)
    plan_agent(q, ground_truth=gt)
    subtask_agent(q, ground_truth=gt)
    context_retaining_agent(q, ground_truth=gt)
    knowledge_retaining_agent(q, ground_truth=gt)

print(f"  섹션 1 완료: {len(GOAL_CASES) * 6}건 기록 (ContextRetention·KnowledgeRetention 포함)")

# ── 역케이스: Gate A FAIL 유도 ─────────────────────────────────────────────
# TCR=100%이 1.0으로 항상 포함 → 나머지 4개 서브지표를 0으로 만들어야 Gate A < 0.5 보장
_monitor_a_fail = PerformanceMonitor(output_dir=_OUTPUT_DIR)

@agent_eval(
    _monitor_a_fail, task_type="qa", task_id_prefix="a_fail_inst",
    instructions=InstructionConfig(
        expected_format="json",
        required_keywords=["result", "confidence", "evidence"],
        min_chars=200,
    ),
    goal_alignment=GoalAlignmentConfig(
        goal_tool_map={"분析": ["analyze_tool", "search_db", "validate"]},
        alignment_threshold=0.9,
        ignore_no_tool_tasks=False,
    ),
    context_retention=ContextRetentionConfig(
        key_entities=["KPI지표", "ROI지수", "벤치마크"],  # 응답에 없는 도메인 엔티티
        check_original_goal=False,  # goal 체크 비활성화 → entity 점수만 반영
    ),
    knowledge_retention=KnowledgeRetentionConfig(
        facts_to_retain=["KPI", "ROI", "분기실적", "벤치마크"],  # 응답에 없는 사실들
        retention_threshold=0.9,
    ),
)
def _a_fail_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"알겠습니다: {question}"   # JSON 없음, 키워드 없음, 도구 없음, context 없음

for _q in ["분기 실적을 分析해줘", "전략을 수립해줘", "데이터를 검토해줘"]:
    _a_fail_agent(_q)

_r = _monitor_a_fail.generate_report().to_dict()
_s = (_r.get("extra_metrics") or {}).get("harness_groups", {}).get("A", {})
_pct = f"{_s['score']*100:.1f}%" if _s.get("score") is not None else "n/a"
print(f"  ▶ 역케이스 Gate A: {_pct}  {'FAIL 확인 ✓' if (_s.get('gate','').upper()=='FAIL') else '예상과 다름'}")

# Gate A 점수 출력
_report = monitor.generate_report().to_dict()
_harness = (_report.get("extra_metrics") or {}).get("harness_groups", {})
_gd = _harness.get("A", {})
_score = _gd.get("score")
_status = _gd.get("status", "n/a")
if _score is not None:
    _bar = "█" * int(_score * 10) + "░" * (10 - int(_score * 10))
    print(f"\n  Gate A [Goal Achievement      ] {_bar} {_score:.3f} ({_status})")

monitor.save_to_file("ch04_group_a")
print("\n결과 저장 완료: results/ch04_group_a.json")
print("확인: agent-eval dashboard results/")
