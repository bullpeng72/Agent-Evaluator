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

    expected_format: str | None = None  # "json"|"markdown"|"yaml"|"plain"|None
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
    violation_weights: dict[str, float] = dataclasses.field(
        default_factory=dict
    )  # 위반 유형별 가중치 (format/sections/length/forbidden/keywords/language)

    def __post_init__(self) -> None:
        import warnings as _w

        # A-1: violation_weight < 0 → score = clamp01(1.0 - violation_count * negative) →
        # 위반이 많을수록 오히려 점수가 오르는 역전 발생(evaluators.py:278).
        if self.violation_weight < 0.0:
            _w.warn(
                f"InstructionConfig: violation_weight={self.violation_weight} < 0; "
                f"clamping to the default 0.1. A negative weight inverts scoring so that "
                f"more violations raise the score instead of lowering it.",
                UserWarning,
                stacklevel=2,
            )
            self.violation_weight = 0.1
        _neg = {k: v for k, v in (self.violation_weights or {}).items() if v < 0.0}
        if _neg:
            _w.warn(
                f"InstructionConfig: violation_weights contains negative values: {_neg}. "
                f"A negative weight inverts scoring so that detecting that violation type "
                f"raises the score.",
                UserWarning,
                stacklevel=2,
            )
        # A-2: min_chars > max_chars(또는 min_words > max_words)이면 모든 길이가
        # 항상 최소 하나의 조건을 위반해 InstructionConfig가 통과 불가능해진다(evaluators.py:191-201).
        if (
            self.max_chars is not None
            and self.min_chars is not None
            and self.min_chars > self.max_chars
        ):
            _w.warn(
                f"InstructionConfig: min_chars={self.min_chars} > max_chars={self.max_chars}. "
                f"No response length can satisfy both bounds, so every response is flagged "
                f"as a violation.",
                UserWarning,
                stacklevel=2,
            )
        if (
            self.max_words is not None
            and self.min_words is not None
            and self.min_words > self.max_words
        ):
            _w.warn(
                f"InstructionConfig: min_words={self.min_words} > max_words={self.max_words}. "
                f"No word count can satisfy both bounds, so every response is flagged "
                f"as a violation.",
                UserWarning,
                stacklevel=2,
            )


@dataclasses.dataclass
class GoalAlignmentConfig:
    """목표-행동 정렬 추적 설정 (Harness A — Goal Achievement).

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    goal_alignment=GoalAlignmentConfig(goal_tool_map={"search": ["web_search"]}))
        def agent(question, ground_truth=""): ...
    """

    use_keyword_overlap: bool = True  # 질문 키워드 ↔ 도구명 오버랩 계산
    goal_tool_map: dict[str, list[str]] = dataclasses.field(
        default_factory=dict
    )  # 목표 키워드 → 도구 목록 매핑
    use_llm_scoring: bool = False  # LLM-as-Judge 정렬 점수 (opt-in)
    llm_blend_weight: float = 0.5  # LLM judge 블렌딩 비중 (0.0=rule only, 1.0=LLM only)
    alignment_threshold: float = 0.6  # 경고 임계값 (0.0~1.0)
    ignore_no_tool_tasks: bool = True  # 도구 호출 없는 태스크 무시

    def __post_init__(self) -> None:
        import warnings as _w

        # llm_blend_weight는 aggregate.py에서 사용 시점에 이미 clamp되지만(방어적 이중화),
        # Config 값 자체가 범위를 벗어나면 사용자 의도와 실제 적용값이 달라진다는 걸 조기에 알린다.
        if not (0.0 <= self.llm_blend_weight <= 1.0):
            _w.warn(
                f"GoalAlignmentConfig: llm_blend_weight={self.llm_blend_weight} is outside the "
                f"[0.0, 1.0] range. It is clamped automatically at use time, but the effective "
                f"value will differ from what was set (0.0 = rule-based only, 1.0 = LLM only).",
                UserWarning,
                stacklevel=2,
            )
        if not (0.0 <= self.alignment_threshold <= 1.0):
            _w.warn(
                f"GoalAlignmentConfig: alignment_threshold={self.alignment_threshold} is outside "
                f"the [0.0, 1.0] range - alignment scores are normalized to 0-1, so an "
                f"out-of-range threshold can make every task always pass or always warn.",
                UserWarning,
                stacklevel=2,
            )


@dataclasses.dataclass
class PlanConfig:
    """계획 일관성 추적 설정 (Harness A — Goal Achievement).

    Example::

        @agent_eval(monitor, task_type="planning",
                    plan_tracking=PlanConfig(available_tools=["search", "summarize"]))
        def agent(question, ground_truth=""): ...
    """

    plan_field: str = "plan"  # 응답에서 플랜 추출할 JSON 필드명
    steps_field: str = "steps"  # 플랜 내 단계 필드명
    check_goal_coverage: bool = True  # 목표 키워드가 계획 단계에 포함되는지 확인
    check_step_ordering: bool = True  # 단계 순서 논리성 확인
    check_executability: bool = True  # 각 단계가 사용 가능한 도구로 실행 가능한지 확인
    available_tools: list[str] = dataclasses.field(default_factory=list)  # 사용 가능한 도구 목록
    use_llm_scoring: bool = False  # LLM-as-Judge 계획 품질 채점 (opt-in)
    llm_blend_weight: float = 0.5  # LLM judge 블렌딩 비중 (0.0=rule only, 1.0=LLM only)
    min_steps: int = 2  # 최소 계획 단계 수
    max_steps: int = 15  # 최대 계획 단계 수

    def __post_init__(self) -> None:
        import warnings as _w

        # min_steps > max_steps → 어떤 step_count도 두 조건을 동시에 만족할 수 없어
        # min_steps_ok/max_steps_ok가 항상 하나는 False로 고정된다(evaluators.py:559-562).
        if self.min_steps > self.max_steps:
            _w.warn(
                f"PlanConfig: min_steps={self.min_steps} > max_steps={self.max_steps}. "
                f"No step count can satisfy both bounds, so every plan is flagged as a violation.",
                UserWarning,
                stacklevel=2,
            )
        if self.min_steps < 0:
            _w.warn(
                f"PlanConfig: min_steps={self.min_steps} < 0; clamping to 0.",
                UserWarning,
                stacklevel=2,
            )
            self.min_steps = 0
        if not (0.0 <= self.llm_blend_weight <= 1.0):
            _w.warn(
                f"PlanConfig: llm_blend_weight={self.llm_blend_weight} is outside the [0.0, 1.0] "
                f"range. It is clamped automatically at use time, but the effective value differs "
                f"from what was set.",
                UserWarning,
                stacklevel=2,
            )


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

    def __post_init__(self) -> None:
        import warnings as _w

        # entity_weight/goal_weight 결합은 이미 (entity_weight*e + goal_weight*g) / sum으로
        # 자동 정규화되지만(evaluators.py:676-678), 음수 가중치는 정규화로도 못 막는 부호 반전을
        # 일으킨다 — ContextWindowConfig의 동일 패턴과 일관되게 검증한다.
        for _name, _val, _default in [
            ("entity_weight", self.entity_weight, 0.6),
            ("goal_weight", self.goal_weight, 0.4),
        ]:
            if _val < 0.0:
                _w.warn(
                    f"ContextRetentionConfig: {_name}={_val} < 0; clamping to the default "
                    f"{_default}. A negative weight can flip the sign of the combined score.",
                    UserWarning,
                    stacklevel=2,
                )
                setattr(self, _name, _default)
        if self.entity_weight + self.goal_weight <= 0:
            raise ValueError("ContextRetentionConfig: entity_weight + goal_weight must be > 0")
        if not (0.0 <= self.retention_threshold <= 1.0):
            _w.warn(
                f"ContextRetentionConfig: retention_threshold={self.retention_threshold} is "
                f"outside the [0.0, 1.0] range.",
                UserWarning,
                stacklevel=2,
            )
        if not (0.0 <= self.goal_overlap_threshold <= 1.0):
            _w.warn(
                f"ContextRetentionConfig: goal_overlap_threshold={self.goal_overlap_threshold} is "
                f"outside the [0.0, 1.0] range.",
                UserWarning,
                stacklevel=2,
            )


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

    def __post_init__(self) -> None:
        import warnings as _w

        # min_completion_rate는 completion_rate(0-1)와 >= 비교된다(evaluators.py:786,794).
        # 범위 밖 값은 항상 통과 또는 항상 미달을 만든다.
        if not (0.0 <= self.min_completion_rate <= 1.0):
            _w.warn(
                f"SubtaskConfig: min_completion_rate={self.min_completion_rate} is outside the "
                f"[0.0, 1.0] range. It is compared against completion_rate (0-1), so a negative "
                f"value always passes and a value above 1.0 always fails.",
                UserWarning,
                stacklevel=2,
            )


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

    def __post_init__(self) -> None:
        import warnings as _w

        if not (0.0 <= self.retention_threshold <= 1.0):
            _w.warn(
                f"KnowledgeRetentionConfig: retention_threshold={self.retention_threshold} is "
                f"outside the [0.0, 1.0] range.",
                UserWarning,
                stacklevel=2,
            )
        if self.seed_turns < 0:
            _w.warn(
                f"KnowledgeRetentionConfig: seed_turns={self.seed_turns} < 0; clamping to 0. "
                f"A negative value is read by the conversation_history[:seed_turns] slice as "
                f"'exclude the last N turns', so turns other than intended are used as the seed.",
                UserWarning,
                stacklevel=2,
            )
            self.seed_turns = 0
        # check_from_turn < seed_turns이면 시드로 쓴 턴을 다시 검사 대상에 포함하게 되어
        # "시드에서 언급된 사실이 이후에도 유지되는지" 측정 의도와 어긋난다.
        if self.check_from_turn < self.seed_turns:
            _w.warn(
                f"KnowledgeRetentionConfig: check_from_turn={self.check_from_turn} < "
                f"seed_turns={self.seed_turns}. Turns used as the seed are also included in "
                f"the checked set, which can conflict with the intent of measuring "
                f"'retention after the seed'.",
                UserWarning,
                stacklevel=2,
            )
