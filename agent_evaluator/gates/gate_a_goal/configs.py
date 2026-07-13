"""
agent_evaluator.gates.gate_a_goal.configs
============================================
Gate A(Goal Achievement) Harness Config 데이터클래스 6종.

SPEC-000: agent_evaluator/decorators.py에서 그대로 이관(로직 변경 없음).
decorators.py는 이 모듈을 re-export하여 하위호환을 유지한다.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class InstructionConfig:
    """응답 형식·길이·언어 준수 여부 추적 설정 (Harness A — Goal Achievement).

    Example::

        @agent_eval(monitor, task_type="qa",
                    instructions=InstructionConfig(expected_format="json", required_keywords=["result"]))
        def agent(question, ground_truth=""): ...
    """
    expected_format: str | None = None                     # "json"|"markdown"|"yaml"|"plain"|None
    required_sections: list[str] = dataclasses.field(default_factory=list)
    max_chars: int | None = None
    min_chars: int | None = None
    max_words: int | None = None
    min_words: int | None = None
    forbidden_phrases: list[str] = dataclasses.field(default_factory=list)
    required_keywords: list[str] = dataclasses.field(default_factory=list)
    expected_language: str | None = None
    fail_on_violation: bool = False
    violation_weight: float = 0.1
    violation_weights: dict[str, float] = dataclasses.field(default_factory=dict)  # 위반 유형별 가중치 (format/sections/length/forbidden/keywords/language)


@dataclasses.dataclass
class GoalAlignmentConfig:
    """목표-행동 정렬 추적 설정 (Harness A — Goal Achievement).

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    goal_alignment=GoalAlignmentConfig(goal_tool_map={"search": ["web_search"]}))
        def agent(question, ground_truth=""): ...
    """
    use_keyword_overlap: bool = True                              # 질문 키워드 ↔ 도구명 오버랩 계산
    goal_tool_map: dict[str, list[str]] = dataclasses.field(default_factory=dict)  # 목표 키워드 → 도구 목록 매핑
    use_llm_scoring: bool = False                                 # LLM-as-Judge 정렬 점수 (opt-in)
    llm_blend_weight: float = 0.5                                 # LLM judge 블렌딩 비중 (0.0=rule only, 1.0=LLM only)
    alignment_threshold: float = 0.6                             # 경고 임계값 (0.0~1.0)
    ignore_no_tool_tasks: bool = True                            # 도구 호출 없는 태스크 무시


@dataclasses.dataclass
class PlanConfig:
    """계획 일관성 추적 설정 (Harness A — Goal Achievement).

    Example::

        @agent_eval(monitor, task_type="planning",
                    plan_tracking=PlanConfig(available_tools=["search", "summarize"]))
        def agent(question, ground_truth=""): ...
    """
    plan_field: str = "plan"                          # 응답에서 플랜 추출할 JSON 필드명
    steps_field: str = "steps"                        # 플랜 내 단계 필드명
    check_goal_coverage: bool = True                  # 목표 키워드가 계획 단계에 포함되는지 확인
    check_step_ordering: bool = True                  # 단계 순서 논리성 확인
    check_executability: bool = True                  # 각 단계가 사용 가능한 도구로 실행 가능한지 확인
    available_tools: list[str] = dataclasses.field(default_factory=list)  # 사용 가능한 도구 목록
    use_llm_scoring: bool = False                     # LLM-as-Judge 계획 품질 채점 (opt-in)
    llm_blend_weight: float = 0.5                     # LLM judge 블렌딩 비중 (0.0=rule only, 1.0=LLM only)
    min_steps: int = 2                                # 최소 계획 단계 수
    max_steps: int = 15                               # 최대 계획 단계 수


@dataclasses.dataclass
class ContextRetentionConfig:
    """핵심 컨텍스트 엔티티 및 원래 목표 보존 여부 추적 설정 (Harness A — Goal Achievement).

    Example::

        @agent_eval(monitor, task_type="qa",
                    context_retention=ContextRetentionConfig(key_entities=["Seoul", "Korea"]))
        def agent(question, ground_truth=""): ...
    """
    key_entities: list[str] = dataclasses.field(default_factory=list)
    context_arg: str = "context"
    retention_threshold: float = 0.7
    check_original_goal: bool = True
    entity_weight: float = 0.6
    goal_weight: float = 0.4
    goal_overlap_threshold: float = 0.3  # 원래 목표 키워드 오버랩 임계값 (낮을수록 관대)


@dataclasses.dataclass
class SubtaskConfig:
    """예상 하위 작업 완료율 추적 설정 (Harness A — Goal Achievement).

    Example::

        @agent_eval(monitor, task_type="planning",
                    subtask_tracking=SubtaskConfig(expected_subtasks=["검색", "요약", "작성"]))
        def agent(question, ground_truth=""): ...
    """
    expected_subtasks: list[str] = dataclasses.field(default_factory=list)
    completion_markers: list[str] = dataclasses.field(
        default_factory=lambda: ["done", "completed", "finished", "✓", "완료", "처리"]
    )
    check_ordering: bool = False
    min_completion_rate: float = 0.8
    auto_extract: bool = False


@dataclasses.dataclass
class KnowledgeRetentionConfig:
    """대화 중 사실 보존 측정 설정 (Harness A — Goal Achievement).

    시드 턴에서 언급된 사실이 이후 응답에서 유지되는지 검사한다.

    Example::

        @agent_eval(monitor, task_type="qa",
                    knowledge_retention=KnowledgeRetentionConfig(
                        facts_to_retain=["서울", "2024"], seed_turns=2))
        def agent(question, ground_truth=""): ...
    """
    facts_to_retain: list[str] = dataclasses.field(default_factory=list)
    seed_turns: int = 2
    check_from_turn: int = 3
    allow_implicit_retention: bool = True
    retention_threshold: float = 0.6
    auto_extract_seed: bool = False  # True 시 seed 턴에서 사실 자동 추출 (opt-in)
