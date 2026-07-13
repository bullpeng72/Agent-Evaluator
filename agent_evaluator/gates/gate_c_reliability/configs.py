"""
agent_evaluator.gates.gate_c_reliability.configs
===================================================
Gate C(Reliability) Harness Config 데이터클래스 5종.

SPEC-000: agent_evaluator/decorators.py에서 그대로 이관(로직 변경 없음).
decorators.py는 이 모듈을 re-export하여 하위호환을 유지한다.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class ReproducibilityConfig:
    """재현성 추적 설정 — 동일 입력에 동일 결과 (Harness C — Reliability).

    Example::

        @agent_eval(monitor, task_type="qa",
                    reproducibility=ReproducibilityConfig(runs=3, similarity_measure="token_f1"))
        def agent(question, ground_truth=""): ...
    """
    runs: int = 3                                   # 동일 입력 반복 실행 횟수
    similarity_measure: str = "token_f1"            # "token_f1"|"jaccard"|"exact"
    reproducibility_threshold: float = 0.85         # 재현성 임계값
    fail_on_low_reproducibility: bool = False        # 임계값 미달 시 success=False
    skip_side_effects: bool = False                  # 부수효과(DB쓰기 등) 있는 함수 건너뜀

    def __post_init__(self) -> None:
        import warnings as _w
        # C-14: threshold > 1.0 → fail_on_low_reproducibility 항상 발동 → 전체 TCR 붕괴 → Gate C 왜곡
        # threshold < 0.0 → 임계값 사실상 무효화
        if not (0.0 <= self.reproducibility_threshold <= 1.0):
            _w.warn(
                f"ReproducibilityConfig: reproducibility_threshold={self.reproducibility_threshold}는 "
                f"[0.0, 1.0] 범위를 벗어납니다. 클램핑합니다. "
                f"> 1.0이면 fail_on_low_reproducibility가 항상 발동해 모든 태스크가 실패 처리되어 "
                f"TCR이 0에 수렴하고 Gate C 집계가 왜곡됩니다. "
                f"< 0.0이면 임계값이 사실상 무효화됩니다.",
                UserWarning, stacklevel=2,
            )
            self.reproducibility_threshold = max(0.0, min(1.0, self.reproducibility_threshold))
        # C-20: runs < 2 → run_count=1 → score=1.0(미측정) or (0 or 3) 폴백으로 3회 실행
        # runs=0이 특히 위험: Python에서 (0 or 3)=3이므로 데코레이터가 함수를 2회 추가 호출하고
        # Gate C에 예상치 못한 재현성 점수가 기여됨
        if self.runs < 2:
            _w.warn(
                f"ReproducibilityConfig: runs={self.runs} < 2. "
                f"재현성 측정은 최소 2회 실행이 필요합니다. "
                f"runs=0이면 데코레이터의 (runs or 3) 폴백으로 실제 3회 실행이 발동되어 "
                f"예상치 못한 함수 부작용과 Gate C 재현성 기여가 발생합니다. "
                f"runs=2로 보정합니다.",
                UserWarning, stacklevel=2,
            )
            self.runs = 2


@dataclasses.dataclass
class FaultToleranceConfig:
    """장애 내성·폴백 추적 설정 (Harness C — Reliability).

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    fault_tolerance=FaultToleranceConfig(check_fallback_attempts=True))
        def agent(question, ground_truth=""): ...
    """
    check_fallback_attempts: bool = True             # 실패 후 폴백 도구 사용 여부 추적
    partial_success_threshold: float = 0.5           # 부분 성공 임계값 (0.0~1.0)
    score_recovery_quality: bool = True              # 폴백 복구 품질 채점
    expected_fallback_tools: dict[str, list[str]] = dataclasses.field(default_factory=dict)  # 도구명 → 폴백 도구 목록

    def __post_init__(self) -> None:
        import warnings as _w
        # C-12: partial_success_threshold < 0 → recovery_rate >= 음수 항상 True → grade="good"
        # → recovery_quality_score=1.0 (0% 복구율에도) → Gate C 인플레이션
        # > 1.0 → recovery_rate >= 1.0 초과 불가 → grade="good" 절대 부여 안 됨 → Gate C 과소
        if not (0.0 <= self.partial_success_threshold <= 1.0):
            _w.warn(
                f"FaultToleranceConfig: partial_success_threshold={self.partial_success_threshold}는 "
                f"[0.0, 1.0] 범위를 벗어납니다. 클램핑합니다. "
                f"< 0이면 복구율 0%에도 grade='good'이 부여되어 Gate C를 인플레이션시킵니다. "
                f"> 1이면 grade='good'이 절대 부여되지 않아 Gate C가 과소 산출됩니다.",
                UserWarning, stacklevel=2,
            )
            self.partial_success_threshold = max(0.0, min(1.0, self.partial_success_threshold))


@dataclasses.dataclass
class GracefulDegradationConfig:
    """장애/저하 상황에서의 응답 품질 측정 설정 (Harness C — Reliability).

    Example::

        @agent_eval(monitor, task_type="qa",
                    graceful_degradation=GracefulDegradationConfig(quality_floor=0.4))
        def agent(question, ground_truth=""): ...
    """
    partial_result_markers: list[str] = dataclasses.field(default_factory=lambda: [
        "partial", "incomplete", "best effort", "부분", "일부", "완전하지 않"
    ])
    quality_floor: float = 0.3
    detect_timeout_fallback: bool = True
    timeout_threshold_ms: float | None = None  # detect_timeout_fallback 실행 시간 기준(ms); None이면 도구명만 검사
    empty_response_penalty: float = 1.0
    check_error_acknowledgment: bool = True

    def __post_init__(self) -> None:
        import warnings as _w
        # C-1: quality_floor > 1.0 → degradation_score > 1.0 → Gate C 집계 오염
        # quality_floor < 0.0 → 음수 점수 가능 → 마찬가지로 오염
        if not (0.0 <= self.quality_floor <= 1.0):
            _w.warn(
                f"GracefulDegradationConfig: quality_floor={self.quality_floor}는 [0.0, 1.0] 범위를 벗어납니다. "
                f"클램핑합니다. quality_floor > 1.0이면 degradation_score가 1.0을 초과해 "
                f"Gate C 집계를 왜곡합니다.",
                UserWarning,
                stacklevel=2,
            )
            self.quality_floor = max(0.0, min(1.0, self.quality_floor))
        # C-1: empty_response_penalty < 0.0 → 1.0 - negative > 1.0 → degradation_score > 1.0
        if self.empty_response_penalty < 0.0:
            _w.warn(
                f"GracefulDegradationConfig: empty_response_penalty={self.empty_response_penalty} < 0 이므로 "
                f"0.0으로 보정됩니다. 음수 값은 빈 응답의 degradation_score가 1.0을 초과해 "
                f"Gate C 집계를 왜곡합니다.",
                UserWarning,
                stacklevel=2,
            )
            self.empty_response_penalty = 0.0
        # C-26: empty_response_penalty > 1.0 → max(0.0, 1.0 - penalty) = 0.0 → quality_floor와 동일
        # 1.0 초과 값은 수학적으로 추가 패널티 효과가 없으므로 사용자가 의도한 동작과 다를 수 있음
        elif self.empty_response_penalty > 1.0:
            _w.warn(
                f"GracefulDegradationConfig: empty_response_penalty={self.empty_response_penalty} > 1.0. "
                f"빈 응답의 degradation_score는 max(quality_floor, max(0.0, 1.0 - penalty))로 계산됩니다. "
                f"penalty > 1.0이면 score=quality_floor={self.quality_floor}로 1.0과 동일한 결과가 됩니다. "
                f"1.0으로 보정합니다.",
                UserWarning,
                stacklevel=2,
            )
            self.empty_response_penalty = 1.0
        # C-28: timeout_threshold_ms < 0 → execution_time(≥0ms) > 음수 항상 True
        # → 실제 타임아웃이 없어도 모든 태스크가 timeout_fallback=True로 오진됨.
        # Gate C 점수에는 직접 영향 없으나 진단 결과를 심각하게 오도함.
        # None으로 초기화해 timeout 시간 기반 검사 비활성화 (도구명 기반 검사만 유지).
        if self.timeout_threshold_ms is not None and self.timeout_threshold_ms < 0:
            _w.warn(
                f"GracefulDegradationConfig: timeout_threshold_ms={self.timeout_threshold_ms} < 0. "
                f"execution_time >= 0ms이므로 모든 태스크가 timeout_fallback=True로 오진됩니다. "
                f"timeout_threshold_ms=None으로 보정해 시간 기반 타임아웃 검사를 비활성화합니다. "
                f"도구명 기반 폴백 검사(detect_timeout_fallback=True + 도구명 'fallback'/'default')는 유지됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.timeout_threshold_ms = None


@dataclasses.dataclass
class RetryConsistencyConfig:
    """재시도 일관성 측정 설정 (Harness C — Reliability).

    재시도 횟수와 성공 여부를 기반으로 재시도 효율성을 평가한다.

    Example::

        @agent_eval(monitor, task_type="qa",
                    retry_consistency=RetryConsistencyConfig(min_retry_count=2))
        def agent(question, ground_truth=""): ...
    """
    group_by_task_prefix: bool = True
    improvement_threshold: float = 0.1
    penalize_degradation: bool = True
    min_retry_count: int = 2

    def __post_init__(self) -> None:
        import warnings as _w
        # C-11: improvement_threshold < 0 → 실패 태스크의 consistency_score = max(0, accuracy+|thr|)
        # accuracy가 높으면 1.0 초과 → Gate C 집계 오염 (e.g., accuracy=0.95, thr=-0.2 → 1.15)
        if self.improvement_threshold < 0.0:
            _w.warn(
                f"RetryConsistencyConfig: improvement_threshold={self.improvement_threshold} < 0 이므로 "
                f"0.0으로 보정됩니다. 음수 임계값은 실패 태스크의 consistency_score가 1.0을 초과해 "
                f"Gate C 집계를 오염시킵니다.",
                UserWarning, stacklevel=2,
            )
            self.improvement_threshold = 0.0
        # C-13: min_retry_count <= 0 → 단일 시도 태스크도 재시도 평가 대상 (의미 위반)
        if self.min_retry_count < 1:
            _w.warn(
                f"RetryConsistencyConfig: min_retry_count={self.min_retry_count} < 1 이므로 "
                f"1로 보정됩니다. min_retry_count <= 0이면 재시도가 없는 태스크도 평가 대상이 되어 "
                f"재시도 효율성 지표가 부정확해집니다.",
                UserWarning, stacklevel=2,
            )
            self.min_retry_count = 1


@dataclasses.dataclass
class IdempotencyConfig:
    """멱등성 평가 설정 (Group C — Reliability).

    도구 호출이 반복 실행 시 부작용을 발생시키는지 평가한다.
    비멱등 도구를 사용하면 점수가 감점되고, 중복 감지 응답은 보너스를 받는다.

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    idempotency=IdempotencyConfig(non_idempotent_penalty=0.2))
        def agent(question, ground_truth=""): ...
    """
    non_idempotent_patterns: list[str] = dataclasses.field(default_factory=lambda: [
        "create", "delete", "insert", "update", "post", "write",
        "생성", "삭제", "저장", "수정", "전송",
    ])
    duplicate_detection_markers: list[str] = dataclasses.field(default_factory=lambda: [
        "already", "duplicate", "exists", "이미", "중복", "존재",
    ])
    non_idempotent_penalty: float = 0.2
    warn_on_non_idempotent: bool = True

    def __post_init__(self) -> None:
        import warnings as _w
        # C-2: non_idempotent_penalty < 0 → penalty 음수 → 1.0 - negative > 1.0
        # → idempotency_score가 1.0을 초과해 Gate C 집계를 오염시킨다.
        if self.non_idempotent_penalty < 0.0:
            _w.warn(
                f"IdempotencyConfig: non_idempotent_penalty={self.non_idempotent_penalty} < 0 이므로 "
                f"기본값 0.2로 보정됩니다. 음수 penalty는 idempotency_score가 1.0을 초과해 "
                f"Gate C 집계를 왜곡합니다.",
                UserWarning,
                stacklevel=2,
            )
            self.non_idempotent_penalty = 0.2
        # C-18: penalty > 1.0 → 비멱등 도구 1개만 있어도 idempotency_score=0.0 고정
        # → 도구 수에 무관하게 Gate C 과소 산출 (Gate C deflation)
        if self.non_idempotent_penalty > 1.0:
            _w.warn(
                f"IdempotencyConfig: non_idempotent_penalty={self.non_idempotent_penalty} > 1.0. "
                f"비멱등 도구가 1개만 있어도 idempotency_score=0.0이 됩니다. "
                f"도구 수에 비례한 감점이 필요하다면 penalty <= 1.0 / max_expected_tools 로 설정하세요.",
                UserWarning,
                stacklevel=2,
            )
