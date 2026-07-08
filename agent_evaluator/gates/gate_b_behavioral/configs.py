"""
agent_evaluator.gates.gate_b_behavioral.configs
==================================================
Gate B(Behavioral Integrity) Harness Config 데이터클래스 6종.

SPEC-000: agent_evaluator/decorators.py에서 그대로 이관(로직 변경 없음).
decorators.py는 이 모듈을 re-export하여 하위호환을 유지한다.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, List, Optional


@dataclasses.dataclass
class LoopDetectionConfig:
    """도구 호출 루프·반복 패턴 감지 설정 (Harness B — Behavioral Integrity).

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3))
        def agent(question, ground_truth=""): ...
    """
    consecutive_repeat_threshold: int = 3       # N회 연속 동일 도구 호출 시 루프 감지
    window_size: int = 5                         # 슬라이딩 윈도우 크기
    duplicate_in_window_threshold: int = 3       # 윈도우 내 중복 도구 호출 허용 횟수 (2는 정상 멀티스텝 에이전트에서 false positive 유발)
    check_response_loop: bool = False            # 응답 텍스트 루프 여부 추가 검사
    response_similarity_threshold: float = 0.95  # 응답 유사도 임계값 (check_response_loop=True 시)
    on_loop_detected: str = "record"             # "record"|"warn"|"fail"

    def __post_init__(self) -> None:
        import warnings as _w
        _valid = {"record", "warn", "fail"}
        if self.on_loop_detected not in _valid:
            _w.warn(
                f"LoopDetectionConfig: on_loop_detected={self.on_loop_detected!r} is not one of "
                f"{sorted(_valid)}. Defaulting to 'record'.",
                UserWarning,
                stacklevel=2,
            )
            self.on_loop_detected = "record"
        # B-17: threshold=0/1은 threshold=2와 동일하게 동작 — consecutive는 반복 분기 진입 시점에 이미 2
        # consecutive_repeat_threshold < 2는 사용자 의도와 다르게 threshold=2로 작동하므로 보정
        if self.consecutive_repeat_threshold < 2:
            _w.warn(
                f"LoopDetectionConfig: consecutive_repeat_threshold={self.consecutive_repeat_threshold} "
                f"은 2 미만이므로 2로 보정됩니다. "
                f"consecutive 카운터는 반복 발생 시점에 이미 2가 되어 0/1 임계값은 실질적으로 2와 동일하게 작동합니다.",
                UserWarning,
                stacklevel=2,
            )
            self.consecutive_repeat_threshold = 2
        if self.window_size < 2:
            _w.warn(
                f"LoopDetectionConfig: window_size={self.window_size} 은 2 미만이므로 2로 보정됩니다. "
                f"크기 1 미만의 윈도우는 슬라이딩 중복 탐지에 의미가 없습니다.",
                UserWarning,
                stacklevel=2,
            )
            self.window_size = 2
        # B-28: duplicate_in_window_threshold < 2 → count >= 1 조건이 항상 참이 되어
        # 윈도우 내 모든 도구가 "window_duplicate" 루프로 오탐됨.
        # 어떤 도구든 윈도우 내 최소 1번 등장하므로 threshold=1은 오탐을 유발한다.
        if self.duplicate_in_window_threshold < 2:
            _w.warn(
                f"LoopDetectionConfig: duplicate_in_window_threshold={self.duplicate_in_window_threshold} "
                f"< 2 이므로 2로 보정됩니다. "
                f"count >= 1은 윈도우 내 어떤 도구에도 참이 되어 모든 도구가 window_duplicate로 오탐됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.duplicate_in_window_threshold = 2
        # B-35: duplicate_in_window_threshold > window_size → 윈도우 내 최대 count=window_size < threshold
        # → count >= threshold가 절대 참이 될 수 없어 window_duplicate 탐지 영구 비활성화.
        # 보정 대신 경고만 발행 (사용자가 의도적으로 threshold를 높여 window_dup을 비활성화할 수도 있으므로).
        if self.duplicate_in_window_threshold > self.window_size:
            _w.warn(
                f"LoopDetectionConfig: duplicate_in_window_threshold={self.duplicate_in_window_threshold} "
                f"> window_size={self.window_size} 이므로 window_duplicate 탐지가 영구 비활성화됩니다. "
                f"크기 {self.window_size}의 윈도우에서 동일 도구의 최대 count는 {self.window_size}로 "
                f"threshold를 절대 충족할 수 없습니다. "
                f"window_dup 탐지를 활성화하려면 duplicate_in_window_threshold ≤ window_size로 설정하세요.",
                UserWarning,
                stacklevel=2,
            )
        # B-26: response_similarity_threshold 범위 검증
        # threshold=0.0 → similarity >= 0.0 항상 참 → 모든 응답 쌍이 루프로 탐지
        # threshold>1.0 → similarity <= 1.0이므로 절대 탐지 불가
        if self.check_response_loop:
            if not (0.0 < self.response_similarity_threshold <= 1.0):
                _corrected = max(0.01, min(1.0, self.response_similarity_threshold))
                _w.warn(
                    f"LoopDetectionConfig: response_similarity_threshold="
                    f"{self.response_similarity_threshold} 은 (0, 1] 범위를 벗어납니다 "
                    f"({_corrected:.2f}로 보정). "
                    f"0.0이면 모든 응답이 루프로 탐지되고, 1.0 초과이면 동일 응답도 탐지되지 않습니다.",
                    UserWarning,
                    stacklevel=2,
                )
                self.response_similarity_threshold = _corrected


@dataclasses.dataclass
class StateConsistencyConfig:
    """실행 전후 상태 일관성 검증 설정 (Gate B — Behavioral Integrity).

    ``state_fn`` 은 실행 전후 각각 한 번씩 호출되어 현재 시스템 상태 딕셔너리를 반환해야 한다.

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    state_consistency=StateConsistencyConfig(
                        state_fn=lambda: {"row_count": db.count()},
                        expected_changes={"row_count": lambda b, a: a == b + 1},
                        unchanged_keys=["user_permissions"],
                    ))
        def agent(question, ground_truth=""): ...
    """
    state_fn: Optional[Callable[[], Dict[str, Any]]] = None
    expected_changes: Dict[str, Any] = dataclasses.field(default_factory=dict)
    unchanged_keys: List[str] = dataclasses.field(default_factory=list)
    fail_on_unexpected_change: bool = False

    def __post_init__(self) -> None:
        import warnings as _w
        if self.state_fn is None and (self.expected_changes or self.unchanged_keys):
            _w.warn(
                "StateConsistencyConfig: expected_changes 또는 unchanged_keys가 설정되어 있지만 "
                "state_fn=None이어서 상태 수집이 이루어지지 않습니다. "
                "state_fn=lambda: {...} 를 지정하세요.",
                UserWarning,
                stacklevel=2,
            )
        # B-23: unchanged_keys와 expected_changes에 동일한 key가 있으면 의미론 모순
        # 같은 key에 대해 checks_total이 2번 카운트되어 consistency_score가 왜곡됨
        # 예: unchanged_keys=['count'] + expected_changes={'count':1} →
        #   count가 변경되면 invariant_violations 발생(불변 위반)과 동시에
        #   expected change matched(기대 변화 일치)로 1패스/1실패 → score=0.5
        _overlap = set(self.unchanged_keys) & set(self.expected_changes.keys())
        if _overlap:
            _w.warn(
                f"StateConsistencyConfig: 다음 key가 unchanged_keys와 expected_changes 양쪽에 있습니다: "
                f"{sorted(_overlap)}. unchanged_keys는 '변경 없음'을, expected_changes는 '변경 있음'을 "
                f"기대하므로 서로 모순됩니다. 같은 key에 대해 checks_total이 2회 계산되어 "
                f"consistency_score가 왜곡됩니다. 한쪽 목록에서 제거하세요.",
                UserWarning,
                stacklevel=2,
            )


@dataclasses.dataclass
class DeadlockConfig:
    """다중 에이전트 교착(Deadlock) 탐지 설정 (Gate B — Behavioral Integrity).

    Example::

        @agent_eval(monitor, task_type="multi_agent",
                    deadlock=DeadlockConfig(check_circular_delegation=True, max_delegation_depth=8))
        def agent(question, ground_truth=""): ...
    """
    check_circular_delegation: bool = True
    check_starvation: bool = True
    starvation_threshold: int = 3
    check_livelock: bool = False
    livelock_window: int = 6
    max_delegation_depth: int = 10
    fail_on_deadlock: bool = False  # True: 교착 탐지 시 task_result.success=False 기록

    def __post_init__(self) -> None:
        import warnings as _w
        # B-32: starvation_threshold < 1 → count >= threshold 조건이 모든 호출에 참이 되어
        # 단 1번 실패도 starvation으로 오탐. threshold는 "N회 이상 호출됐으나 성공 없음" 기준이므로
        # 최소 1이어야 한다. 0 이하는 의미없는 값 — 1로 보정.
        if self.check_starvation and self.starvation_threshold < 1:
            _w.warn(
                f"DeadlockConfig: starvation_threshold={self.starvation_threshold} < 1 이므로 "
                f"1로 보정됩니다. "
                f"starvation_threshold는 'N회 이상 호출되었으나 성공이 없을 때 starvation으로 판정'하는 "
                f"최소 호출 횟수 기준입니다. 0 이하 값은 호출 여부와 무관하게 항상 orifitation을 유발합니다.",
                UserWarning,
                stacklevel=2,
            )
            self.starvation_threshold = 1
        # B-39: max_delegation_depth < 0 → delegation_depth(≥0) > max_depth(<0) 항상 참
        # → 위임이 없어도 (delegation_depth=0 > -1=True) 항상 depth_exceeded=True 오탐
        if self.max_delegation_depth < 0:
            _w.warn(
                f"DeadlockConfig: max_delegation_depth={self.max_delegation_depth} < 0 이므로 "
                f"기본값 10으로 보정됩니다. "
                f"음수 depth는 delegation_depth(≥0) > max_depth(<0)를 항상 참으로 만들어 "
                f"위임이 없는 태스크도 deadlock_type=depth_exceeded로 오탐됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.max_delegation_depth = 10
        # B-24: livelock 탐지 루프는 range(2, window//2+1)로 주기 p를 순회
        # 최소 주기 p=2를 탐지하려면 window >= 4 필요 (range(2,3) 이상)
        # window=2,3 → range(2,2)=[] → 탐지 루프 비실행 → check_livelock=True여도 항상 미탐지
        if self.check_livelock and self.livelock_window < 4:
            import warnings as _w
            _w.warn(
                f"DeadlockConfig: check_livelock=True이지만 livelock_window={self.livelock_window} < 4 이므로 "
                f"4로 보정됩니다. livelock 탐지는 최소 주기 p=2를 찾기 위해 window >= 4 가 필요합니다 "
                f"(range(2, window//2+1) 가 비어 있으면 어떤 패턴도 탐지되지 않습니다).",
                UserWarning,
                stacklevel=2,
            )
            self.livelock_window = 4


@dataclasses.dataclass
class ScopeConfig:
    """도구 사용 범위 경계 설정 (Harness B — Behavioral Integrity).

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    scope=ScopeConfig(allowed_tools=["search", "summarize"], fail_on_violation=True))
        def agent(question, ground_truth=""): ...
    """
    allowed_tools: List[str] = dataclasses.field(default_factory=list)
    forbidden_tools: List[str] = dataclasses.field(default_factory=list)
    max_tool_calls: Optional[int] = None
    max_unique_tools: Optional[int] = None
    fail_on_violation: bool = False
    violation_penalty: float = 0.2  # 위반 1건당 penalty (forbidden/out_of_scope/excess)

    def __post_init__(self) -> None:
        import warnings as _w
        # B-34: allowed_tools=None / forbidden_tools=None → set(None) → TypeError 크래시
        # default_factory=list가 기본이지만 명시적으로 None을 전달하면 발생.
        # None은 "제한 없음(빈 리스트)"으로 정규화한다.
        if self.allowed_tools is None:
            self.allowed_tools = []
        if self.forbidden_tools is None:
            self.forbidden_tools = []
        overlap = set(self.allowed_tools) & set(self.forbidden_tools)
        if overlap:
            _w.warn(
                f"ScopeConfig: tools appear in both allowed_tools and forbidden_tools: {sorted(overlap)}. "
                "They will be treated as forbidden.",
                UserWarning,
                stacklevel=2,
            )
        # B-36: max_tool_calls < 0 → excess_calls = len - negative → 부풀린 값 (len+|limit|)
        # 예: max_tool_calls=-1, 1 call → excess_calls=2 (실제로는 초과 없음)
        # 음수 한계는 의미 없으므로 None으로 보정해 검사 비활성화.
        if self.max_tool_calls is not None and self.max_tool_calls < 0:
            _w.warn(
                f"ScopeConfig: max_tool_calls={self.max_tool_calls} < 0 이므로 None으로 보정됩니다. "
                f"음수 한계는 excess_calls를 의도치 않게 부풀립니다 "
                f"(excess = len(calls) - max = len + {abs(self.max_tool_calls)}). "
                f"제한 없음으로 처리하려면 None을 사용하세요.",
                UserWarning,
                stacklevel=2,
            )
            self.max_tool_calls = None
        if self.max_unique_tools is not None and self.max_unique_tools < 0:
            _w.warn(
                f"ScopeConfig: max_unique_tools={self.max_unique_tools} < 0 이므로 None으로 보정됩니다. "
                f"음수 한계는 excess_unique를 의도치 않게 부풀립니다.",
                UserWarning,
                stacklevel=2,
            )
            self.max_unique_tools = None
        # B-25: violation_penalty < 0 → scope_score = max(0, 1 - count×음수) > 1.0 → Gate B 집계 왜곡
        # ToolParameterSafetyConfig(B-22)와 동일 패턴으로 검증 통일
        if self.violation_penalty <= 0:
            _w.warn(
                f"ScopeConfig: violation_penalty={self.violation_penalty} ≤ 0 이므로 "
                f"기본값 0.2로 보정됩니다. 음수 penalty는 scope_score > 1.0을 만들어 Gate B 집계를 왜곡시킵니다.",
                UserWarning,
                stacklevel=2,
            )
            self.violation_penalty = 0.2


@dataclasses.dataclass
class ToolParameterSafetyConfig:
    """도구 파라미터 안전성 검사 설정 (Harness B — Behavioral Integrity).

    도구 호출 파라미터에 위험 패턴·금지 키·스키마 위반이 있는지 검사한다.

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    tool_parameter_safety=ToolParameterSafetyConfig(
                        forbidden_argument_keys={"shell_exec": ["cmd"]}))
        def agent(question, ground_truth=""): ...
    """
    tool_schemas: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    dangerous_patterns: List[str] = dataclasses.field(default_factory=lambda: [
        r"\.\./", r"&&", r"\|\|", r";.*rm\s", r"__import__", r"eval\(", r"exec\(",
    ])
    # SPEC-024 REQ-1: dangerous_patterns 검사를 지정된 도구 이름으로만 한정한다.
    # None(기본값)이면 기존과 동일하게 모든 도구 호출을 검사한다(하위 호환).
    # 이 필드가 필요해진 이유: dangerous_patterns는 도구 이름과 무관하게 모든 호출의
    # 파라미터를 JSON 직렬화한 문자열 전체에 매치되므로(evaluators.py의
    # `_json.dumps(args)`), 예를 들어 셸 명령을 잡기 위한 패턴이 셸과 무관한 도구
    # (예: 메모리 저장 도구)의 자연어 파라미터 안에서도 매치될 수 있다 — 실제로
    # `dangerous_patterns=[r"\brm\s+\S"]`가 `save_memory` 도구의
    # "...rm 시도가 거부됨..." 같은 텍스트를 오탐하는 것을 재현해 확인했다.
    scope_tool_names: Optional[List[str]] = None
    forbidden_argument_keys: Dict[str, List[str]] = dataclasses.field(default_factory=dict)
    max_argument_length: int = 2000
    fail_on_dangerous: bool = False
    violation_penalty: float = 0.25  # 위험 도구 1개당 penalty (IdempotencyConfig.non_idempotent_penalty와 동일 역할)
    # SPEC-033: True면 인자 문자열에서 base64/hex로 보이는 하위 문자열을 디코드해
    # dangerous_patterns를 재매치한다(예: base64로 인코딩된 "rm -rf /" 탐지). 기본값
    # False는 기존 동작과 100% 동일 — 새 탐지 규칙이 아니라 검사 대상 텍스트를
    # 하나 더(디코드 결과) 추가하는 순수 전처리 계층이다.
    decode_encodings: bool = False

    def __post_init__(self) -> None:
        import warnings as _w
        # B-22: violation_penalty < 0 → safety_score = max(0, 1 - penalty) > 1.0 → Gate B 집계 왜곡
        # penalty는 "감점 비율"이므로 0 초과여야 의미 있음; 0이면 위험 도구 감지 불능
        if self.violation_penalty <= 0:
            _w.warn(
                f"ToolParameterSafetyConfig: violation_penalty={self.violation_penalty} ≤ 0 이므로 "
                f"기본값 0.25로 보정됩니다. 음수 penalty는 safety_score > 1.0을 만들어 Gate B 집계를 왜곡시킵니다.",
                UserWarning,
                stacklevel=2,
            )
            self.violation_penalty = 0.25
        if self.max_argument_length <= 0:
            _w.warn(
                f"ToolParameterSafetyConfig: max_argument_length={self.max_argument_length} ≤ 0 이므로 "
                f"기본값 2000으로 보정됩니다. 0 이하 값은 모든 비빈 인자를 'arg_too_long'으로 처리합니다.",
                UserWarning,
                stacklevel=2,
            )
            self.max_argument_length = 2000
        # B-45: dangerous_patterns에 빈 문자열("")이 있으면 re.search("", any_str)가 항상 매치됨
        # → 모든 도구 호출이 "dangerous"로 표시되어 safety_score가 의도치 않게 급락
        # B-46: dangerous_patterns에 None이 있으면 re.search(None, str) → TypeError
        # → 외부 try/except Exception이 TypeError를 삼켜 평가 전체가 묵살됨
        # 두 경우 모두 정규식으로 유효하지 않은 항목이므로 UserWarning 후 목록에서 제거한다.
        _bad_patterns = [p for p in (self.dangerous_patterns or []) if not isinstance(p, str) or not p.strip()]
        if _bad_patterns:
            _w.warn(
                f"ToolParameterSafetyConfig: dangerous_patterns에 빈 문자열 또는 None 항목이 있습니다: "
                f"{_bad_patterns!r}. 해당 항목을 제거합니다. "
                f"빈 문자열은 re.search('', str)이 항상 매치되어 모든 도구 호출을 위험으로 표시하고, "
                f"None은 TypeError를 유발해 안전성 평가 전체가 묵살됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.dangerous_patterns = [p for p in (self.dangerous_patterns or []) if isinstance(p, str) and p.strip()]
        # SPEC-024 REQ-1: scope_tool_names=[](빈 리스트)는 "어떤 도구도 스코프에 없음"이 되어
        # dangerous_patterns 검사가 조용히 전부 비활성화된다 — None(전체 검사, 기본값)과
        # 의미가 다르므로 사용자가 실수로 빈 리스트를 넘겼을 가능성을 경고한다.
        if self.scope_tool_names is not None and len(self.scope_tool_names) == 0:
            _w.warn(
                "ToolParameterSafetyConfig: scope_tool_names=[](빈 리스트)는 어떤 도구도 "
                "dangerous_patterns 검사 대상이 되지 않는다는 뜻입니다 — 사실상 위험 패턴 감지가 "
                "전부 비활성화됩니다. 모든 도구를 검사하려면 scope_tool_names=None(기본값)을 "
                "쓰세요.",
                UserWarning,
                stacklevel=2,
            )
        # B-50: tool_schemas spec 값이 dict가 아니면 eval에서 TypeError → 평가 전체 묵살.
        # __post_init__에서 조기 경고하여 사용자가 설정 오류를 빠르게 발견하도록 한다.
        _bad_specs = [
            f"{tool!r}.{param!r}"
            for tool, schema in (self.tool_schemas or {}).items()
            if isinstance(schema, dict)
            for param, spec in schema.items()
            if not isinstance(spec, dict)
        ]
        if _bad_specs:
            _w.warn(
                f"ToolParameterSafetyConfig: tool_schemas의 파라미터 spec이 dict가 아닙니다: "
                f"{_bad_specs}. "
                f"올바른 형식: {{\"type\": \"int\", \"min\": 0, \"max\": 100}}. "
                f"잘못된 spec은 평가 시 건너뜁니다.",
                UserWarning,
                stacklevel=2,
            )


@dataclasses.dataclass
class ContextWindowConfig:
    """컨텍스트 윈도우 활용 평가 설정 (Gate B — Behavioral Integrity).

    토큰 포화도, 반복 패턴, 정보 밀도를 측정하여 응답 품질을 평가한다.

    Example::

        @agent_eval(monitor, task_type="qa",
                    context_window=ContextWindowConfig(window_size_tokens=128000))
        def agent(question, ground_truth=""): ...
    """
    window_size_tokens: int = 128000
    warn_at_pct: float = 0.7
    saturated_at_pct: float = 0.9
    repetition_threshold: int = 3
    min_information_density: float = 0.3
    repetition_penalty_factor: float = 2.0  # 반복 비율 × 이 값이 감점 (기본 2.0: 50% 반복 시 score=0)
    # combined score 가중치 (합계가 1.0이 아니면 자동 정규화)
    saturation_weight: float = 0.5   # 포화도 가중치
    repetition_weight: float = 0.3   # 반복 패턴 가중치
    density_weight: float = 0.2      # 정보 밀도 가중치

    def __post_init__(self) -> None:
        import warnings as _w
        # B-37: warn_at_pct > 1.0 / saturated_at_pct > 1.0 → utilization(=tokens/window)은 정상 사용 시
        # 0–1 범위이므로 임계값이 1.0을 크게 초과하면 포화 경고/탐지가 영구 비활성화됨.
        # 예: warn_at_pct=75 (0-100% 범위로 착각) → utilization ≈ 0.004 << 75 → 절대 미발동.
        if self.warn_at_pct > 1.0:
            _w.warn(
                f"ContextWindowConfig: warn_at_pct={self.warn_at_pct} > 1.0 이므로 "
                f"기본값 0.7로 보정됩니다. "
                f"warn_at_pct는 컨텍스트 창 사용률 분율(0–1)입니다 — 퍼센트(0–100)가 아닙니다. "
                f"1.0 초과 값은 정상 사용 범위(utilization ≤ 1.0)에서 절대 발동되지 않아 "
                f"포화 경고가 영구 비활성화됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.warn_at_pct = 0.7
        if self.saturated_at_pct > 1.0:
            _w.warn(
                f"ContextWindowConfig: saturated_at_pct={self.saturated_at_pct} > 1.0 이므로 "
                f"기본값 0.9로 보정됩니다. "
                f"saturated_at_pct는 컨텍스트 창 사용률 분율(0–1)입니다 — 퍼센트(0–100)가 아닙니다. "
                f"1.0 초과 값은 정상 사용 범위에서 절대 발동되지 않아 포화 탐지가 영구 비활성화됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.saturated_at_pct = 0.9
        # B-47a: warn_at_pct < 0.0 → 음수 warning 임계값은 utilization(≥0)이 항상 초과
        # → 0% 사용률도 warning 영역에 진입해 saturation_score < 1.0으로 과도한 패널티 발생.
        # 예: warn=-0.3, sat=0.5 → 10% 사용률에서 score=0.25 (정상이면 ~1.0이어야 함).
        # B-52: 이전 보정 목적지 0.0은 여전히 0%부터 warn zone을 시작시켜 정상 사용률에 과도한 페널티.
        # warn > 1.0이면 0.7(기본값)로 복원하는 것과 일관되게, sat 기반으로 최대 0.7까지 복원.
        # sat <= 0이면 step B-47b에서 0.9로 보정 예정이므로 effective_sat=0.9를 선제 반영.
        if self.warn_at_pct < 0.0:
            _eff_sat = self.saturated_at_pct if self.saturated_at_pct > 0.0 else 0.9
            _corrected_warn = min(0.7, max(0.0, _eff_sat - 0.05))
            _w.warn(
                f"ContextWindowConfig: warn_at_pct={self.warn_at_pct} < 0 이므로 "
                f"{_corrected_warn}로 보정됩니다. "
                f"음수 warn_at_pct는 utilization(0 이상)이 항상 warning 영역에 진입하게 만들어 "
                f"0% 사용률에서도 saturation_score < 1.0으로 오탐됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.warn_at_pct = _corrected_warn
        # B-47b: saturated_at_pct <= 0.0 → utilization(≥0)이 항상 포화 임계값 이상
        # → 1 token만 사용해도 is_saturated=True 오탐.
        # 예: sat=-0.2 → utilization=0.00008 > -0.2 → 항상 saturation_score=0.0.
        if self.saturated_at_pct <= 0.0:
            _w.warn(
                f"ContextWindowConfig: saturated_at_pct={self.saturated_at_pct} ≤ 0 이므로 "
                f"기본값 0.9로 보정됩니다. "
                f"0 이하 포화 임계값은 모든 utilization(≥0)을 항상 saturated로 만들어 "
                f"모든 태스크가 is_saturated=True로 오탐됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.saturated_at_pct = 0.9
        # B-37/B-47 보정 후 순서 무결성 검사 (warn < saturated 보장)
        if self.warn_at_pct >= self.saturated_at_pct:
            raise ValueError(
                f"ContextWindowConfig: warn_at_pct ({self.warn_at_pct}) must be "
                f"< saturated_at_pct ({self.saturated_at_pct})"
            )
        # B-31: window_size_tokens ≤ 0 → eval_context_window에서 max(window_size_tokens, 1)=1로 대체
        # → utilization = tokens/1 (매우 큰 값) → is_saturated=True 항상 오탐
        # → window_utilization이 실제 비율이 아닌 절대 토큰 수로 표시됨
        if self.window_size_tokens <= 0:
            _w.warn(
                f"ContextWindowConfig: window_size_tokens={self.window_size_tokens} ≤ 0 이므로 "
                f"기본값 128000으로 보정됩니다. "
                f"0 이하 값은 eval_context_window에서 분모가 1로 대체되어 "
                f"모든 입력이 항상 is_saturated=True로 오탐됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.window_size_tokens = 128000
        # B-29: min_information_density > 1.0 → word-level density = unique/total ≤ 1.0 이므로
        # density_ok가 항상 False가 되어 모든 응답이 "정보 밀도 부족"으로 오탐됨.
        if self.min_information_density > 1.0:
            _w.warn(
                f"ContextWindowConfig: min_information_density={self.min_information_density} > 1.0 이므로 "
                f"1.0으로 보정됩니다. "
                f"단어 수준 정보 밀도(unique_words/total_words)는 항상 ≤ 1.0이므로 "
                f"이 값을 초과하면 모든 응답이 '밀도 부족'으로 오탐됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.min_information_density = 1.0
        elif self.min_information_density <= 0.0:
            _w.warn(
                f"ContextWindowConfig: min_information_density={self.min_information_density} ≤ 0 이므로 "
                f"기본값 0.3으로 보정됩니다. "
                f"0 이하 값은 모든 응답이 '밀도 충분'으로 간주되어 탐지가 비활성화됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.min_information_density = 0.3
        # B-19: repetition_threshold < 2 → 모든 n-gram이 "반복"으로 집계되어 repetition_score=0.0 고정
        # n-gram count는 항상 >= 1이므로 threshold=1은 "2번 이상 등장" 기준과 동일하게 작동해야 하는
        # threshold=2와 구별되지 않음. 최소 2로 보정해 의미론 일관성 보장.
        if self.repetition_threshold < 2:
            _w.warn(
                f"ContextWindowConfig: repetition_threshold={self.repetition_threshold} "
                f"< 2 이므로 2로 보정됩니다. 1 이하 임계값은 모든 4-gram을 '반복'으로 간주해 "
                f"repetition_score를 항상 0.0으로 만듭니다.",
                UserWarning,
                stacklevel=2,
            )
            self.repetition_threshold = 2
        # B-40: repetition_penalty_factor <= 0 → repetition_score > 1.0 (음수) 또는 탐지 비활성화 (0)
        # 음수 factor: 1.0 - ratio*neg = 1.0 + positive > 1.0 → max(0.0, ...) 가 1.0 초과를 막지 못함 → Gate B 집계 왜곡
        # 0: 1.0 - ratio*0 = 1.0 항상 → 반복 아무리 많아도 repetition_score=1.0 → 탐지 비활성화
        if self.repetition_penalty_factor <= 0.0:
            _w.warn(
                f"ContextWindowConfig: repetition_penalty_factor={self.repetition_penalty_factor} ≤ 0 이므로 "
                f"기본값 2.0으로 보정됩니다. "
                f"0은 반복 탐지를 영구 비활성화하고, 음수는 repetition_score > 1.0을 만들어 "
                f"context_window_score가 1.0을 초과해 Gate B 집계를 왜곡시킵니다.",
                UserWarning,
                stacklevel=2,
            )
            self.repetition_penalty_factor = 2.0
        # B-41: 개별 음수 가중치 → combined score < 0 또는 의미론 반전
        # 음수 saturation_weight: 포화 상태(saturation_score=0.0)가 오히려 점수를 높이는 역설 발생
        # max(0.0, combined)가 없으므로 음수 combined가 그대로 context_window_score로 저장됨 → Gate B 오염
        for _wname, _wval, _wdefault in [
            ("saturation_weight", self.saturation_weight, 0.5),
            ("repetition_weight", self.repetition_weight, 0.3),
            ("density_weight", self.density_weight, 0.2),
        ]:
            if _wval < 0.0:
                _w.warn(
                    f"ContextWindowConfig: {_wname}={_wval} < 0 이므로 기본값 {_wdefault}로 보정됩니다. "
                    f"음수 가중치는 해당 지표의 페널티를 보너스로 반전시켜 context_window_score를 왜곡시킵니다.",
                    UserWarning,
                    stacklevel=2,
                )
                setattr(self, _wname, _wdefault)
        _total_w = self.saturation_weight + self.repetition_weight + self.density_weight
        if _total_w <= 0:
            raise ValueError("ContextWindowConfig: saturation_weight + repetition_weight + density_weight must be > 0")
        if abs(_total_w - 1.0) > 1e-6:
            _w.warn(
                f"ContextWindowConfig: weights sum to {_total_w:.4f} (not 1.0) — will be auto-normalized.",
                UserWarning,
                stacklevel=2,
            )
