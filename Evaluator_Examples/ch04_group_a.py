"""
Chapter 04 — Gate A: 목표달성 실전 예제
=========================================
Gate A Config 6종 전체 + FAIL 시나리오 2개를 실행해볼 수 있는 독립 예제.

실행:
    python Evaluator_Examples/ch04_group_a.py

섹션 구성:
    섹션 1 — InstructionConfig    : 응답 형식·필수 키워드·최소 길이 기준
    섹션 2 — GoalAlignmentConfig  : 목표-도구 정렬 임계값
    섹션 3 — PlanConfig           : 계획 완성도·단계 완주율
    섹션 4 — SubtaskConfig        : 하위 태스크 분해·완료율
    섹션 5 — ContextRetentionConfig: 핵심 엔티티 보존
    섹션 6 — KnowledgeRetentionConfig: 대화 중 사실 보존
    섹션 7 — FAIL 시나리오 6       : InstructionConfig + GoalAlignmentConfig 동시 위반
    섹션 8 — FAIL 시나리오 7       : ContextRetentionConfig + KnowledgeRetentionConfig 위반
"""

import json
from pathlib import Path

from agent_evaluator import (
    ContextRetentionConfig,
    GoalAlignmentConfig,
    InstructionConfig,
    KnowledgeRetentionConfig,
    PerformanceMonitor,
    PlanConfig,
    SubtaskConfig,
    agent_eval,
    load_env,
    setup_otel,
)

load_env()

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    import socket

    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch04-group-a")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ── 공유 monitor ─────────────────────────────────────────────────────────────
monitor = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

# =============================================================================
# 섹션 1 — InstructionConfig: 응답 형식·필수 키워드·최소 길이 기준
# =============================================================================

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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return json.dumps({"result": f"{question}에 대한 답변", "confidence": 0.92})


# =============================================================================
# 섹션 2 — GoalAlignmentConfig: 목표-도구 정렬 임계값
# =============================================================================

@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="a_goal",
    goal_alignment=GoalAlignmentConfig(
        goal_tool_map={"분석": ["analyze_tool", "search"]},
        alignment_threshold=0.5,
    ),
)
def goal_aligned_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"분석 결과: {question}에 대한 검색 및 분석 완료"


# =============================================================================
# 섹션 3 — PlanConfig: 계획 완성도·단계 완주율
# =============================================================================
# 지원 형식: {"steps": [...]} 또는 {"plan": [...]} (plan 키가 직접 리스트)
# 주의: {"plan": {"steps": [...]}} 중첩 구조는 PlanConfig가 파싱하지 못함

@agent_eval(
    monitor,
    task_type="planning",
    task_id_prefix="a_plan",
    plan_tracking=PlanConfig(
        check_goal_coverage=True,
        min_steps=2,
        available_tools=["search", "analyze"],
        check_executability=True,
    ),
)
def plan_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return json.dumps({"steps": ["search로 정보 검색", "analyze로 결과 분석", "요약 작성"]})


# =============================================================================
# 섹션 4 — SubtaskConfig: 하위 태스크 분해·완료율
# =============================================================================

@agent_eval(
    monitor,
    task_type="planning",
    task_id_prefix="a_subtask",
    subtask_tracking=SubtaskConfig(
        expected_subtasks=["데이터 수집", "분석", "요약"],
        min_completion_rate=0.7,
    ),
)
def subtask_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return "데이터 수집 완료, 분석 완료, 요약 작성 완료"


# =============================================================================
# 섹션 5 — ContextRetentionConfig: 핵심 엔티티 보존
# =============================================================================

@agent_eval(
    monitor,
    task_type="information_retrieval",
    task_id_prefix="a_context",
    context_retention=ContextRetentionConfig(
        key_entities=["GPT-4", "Claude", "Gemini"],
        retention_threshold=0.7,
    ),
)
def context_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"GPT-4, Claude, Gemini를 비교하면: {question}에 대해 각 모델이 다른 접근을 취합니다."


# =============================================================================
# 섹션 6 — KnowledgeRetentionConfig: 대화 중 사실 보존
# =============================================================================

@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="a_knowledge",
    knowledge_retention=KnowledgeRetentionConfig(
        facts_to_retain=["OpenAI", "Anthropic"],
        retention_threshold=0.7,
    ),
)
def knowledge_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"OpenAI와 Anthropic은 대표적인 AI 기업입니다. {question}"


# =============================================================================
# 섹션 1~6 정상 경로 실행
# =============================================================================

def run_normal_scenarios() -> None:
    print("\n=== 섹션 1~6: Gate A 정상 경로 ===")
    instruction_agent("서울의 인구는?", ground_truth="약 950만 명")
    goal_aligned_agent("이 데이터를 분석해줘", ground_truth="분석 완료")
    plan_agent("리서치 계획을 세워줘", ground_truth="계획 수립")
    subtask_agent("프로젝트를 완료해줘", ground_truth="완료")
    context_agent("주요 LLM 모델을 비교해줘", ground_truth="모델 비교")
    knowledge_agent("주요 AI 기업을 알려줘", ground_truth="AI 기업 목록")

    report = monitor.generate_report()
    monitor.save_to_file("ch04_group_a_normal")
    d = report.to_dict()
    harness = (d.get("extra_metrics") or {}).get("harness_groups", {})
    gate_a = harness.get("A", {})
    print(f"Gate A 점수: {gate_a.get('score', 'n/a')}")
    print(f"Gate A 상태: {gate_a.get('status', 'n/a')}")
    print("→ results/ch04_group_a_normal.json + .html")


# =============================================================================
# 섹션 7 — FAIL 시나리오 6: InstructionConfig + GoalAlignmentConfig 동시 위반
# =============================================================================

monitor_fail = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)


@agent_eval(
    monitor_fail,
    task_type="qa",
    task_id_prefix="bad_a_goal",
    instructions=InstructionConfig(
        expected_format="json",
        required_keywords=["result", "confidence", "reasoning"],
        min_chars=100,
    ),
    goal_alignment=GoalAlignmentConfig(
        goal_tool_map={"분석": ["analyze_tool", "search"]},
        alignment_threshold=0.6,
        ignore_no_tool_tasks=False,
    ),
)
def goal_failing_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 이 함수는 Gate A FAIL을 시연하는 역케이스입니다.
    #   실제 에이전트에서는 expected_format 준수 + required_keywords 포함 + 목표 도구 사용이 필요합니다.
    # JSON 형식 미준수, required_keywords 없음, 목표 도구(analyze_tool) 미사용
    return f"네, {question} 처리했습니다."


# =============================================================================
# 섹션 8 — FAIL 시나리오 7: ContextRetentionConfig + KnowledgeRetentionConfig 위반
# =============================================================================

@agent_eval(
    monitor_fail,
    task_type="qa",
    task_id_prefix="bad_a_context",
    context_retention=ContextRetentionConfig(
        key_entities=["GPT-4", "Claude", "Gemini", "LLaMA"],
        retention_threshold=0.8,
    ),
    knowledge_retention=KnowledgeRetentionConfig(
        facts_to_retain=["OpenAI", "Anthropic", "Google", "Meta"],
        retention_threshold=0.8,
    ),
)
def context_forgetting_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 이 함수는 Gate A FAIL을 시연하는 역케이스입니다.
    #   실제 에이전트에서는 key_entities를 응답에 반드시 포함해야 합니다.
    # 핵심 엔티티를 전혀 언급하지 않음 → context_retention_score=0.0
    return f"이 주제에 대해 AI 업계에서 연구 중입니다. {question}"


def run_fail_scenarios() -> None:
    print("\n=== 섹션 7~8: Gate A FAIL 시나리오 ===")
    goal_failing_agent("이 데이터를 분석해줘", ground_truth="분석 완료")
    # → instruction_score=0.0 (format 위반) + goal_alignment=0.0 (도구 미사용)

    context_forgetting_agent("주요 LLM 모델들을 비교해줘", ground_truth="모델 비교")
    # → context_retention=0.0 + knowledge_retention=0.0

    report_fail = monitor_fail.generate_report()
    monitor_fail.save_to_file("ch04_group_a_fail")
    d = report_fail.to_dict()
    harness = (d.get("extra_metrics") or {}).get("harness_groups", {})
    gate_a = harness.get("A", {})
    _score = gate_a.get("score")
    _score_str = f"{_score:.3f}" if _score is not None else "n/a"
    print(f"Gate A 점수: {_score_str}  ← 약 46% 예상")
    print(f"Gate A 상태: {gate_a.get('status', 'n/a')}")
    print("→ results/ch04_group_a_fail.json + .html")


if __name__ == "__main__":
    run_normal_scenarios()
    run_fail_scenarios()
    print("\n완료. agent-eval dashboard results/ 로 결과를 확인하세요.")
