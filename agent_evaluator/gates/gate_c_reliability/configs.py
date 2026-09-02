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

    runs: int = 3  # 동일 입력 반복 실행 횟수
    similarity_measure: str = "token_f1"  # "token_f1"|"jaccard"|"exact"
    reproducibility_threshold: float = 0.85  # 재현성 임계값
    fail_on_low_reproducibility: bool = False  # 임계값 미달 시 success=False
    skip_side_effects: bool = False  # 부수효과(DB쓰기 등) 있는 함수 건너뜀

    def __post_init__(self) -> None:
        import warnings as _w

        # C-14: threshold > 1.0 → fail_on_low_reproducibility 항상 발동 → 전체 TCR 붕괴 → Gate C 왜곡
        # threshold < 0.0 → 임계값 사실상 무효화
        if not (0.0 <= self.reproducibility_threshold <= 1.0):
            _w.warn(
                f"ReproducibilityConfig: reproducibility_threshold="
                f"{self.reproducibility_threshold} is outside the [0.0, 1.0] range. Clamping. "
                f"If > 1.0, fail_on_low_reproducibility always fires and every task is failed, so "
                f"TCR converges to 0 and the Gate C aggregate is distorted. "
                f"If < 0.0, the threshold is effectively void.",
                UserWarning,
                stacklevel=2,
            )
            self.reproducibility_threshold = max(0.0, min(1.0, self.reproducibility_threshold))
        # C-20: runs < 2 → run_count=1 → score=1.0(미측정) or (0 or 3) 폴백으로 3회 실행
        # runs=0이 특히 위험: Python에서 (0 or 3)=3이므로 데코레이터가 함수를 2회 추가 호출하고
        # Gate C에 예상치 못한 재현성 점수가 기여됨
        if self.runs < 2:
            _w.warn(
                f"ReproducibilityConfig: runs={self.runs} < 2. "
                f"Reproducibility measurement needs at least 2 runs. "
                f"With runs=0, the decorator's (runs or 3) fallback triggers an actual 3 runs, "
                f"causing unexpected function side effects and a Gate C reproducibility "
                f"contribution. Clamping to runs=2.",
                UserWarning,
                stacklevel=2,
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

    check_fallback_attempts: bool = True  # 실패 후 폴백 도구 사용 여부 추적
    partial_success_threshold: float = 0.5  # 부분 성공 임계값 (0.0~1.0)
    score_recovery_quality: bool = True  # 폴백 복구 품질 채점
    expected_fallback_tools: dict[str, list[str]] = dataclasses.field(
        default_factory=dict
    )  # 도구명 → 폴백 도구 목록

    def __post_init__(self) -> None:
        import warnings as _w

        # C-12: partial_success_threshold < 0 → recovery_rate >= 음수 항상 True → grade="good"
        # → recovery_quality_score=1.0 (0% 복구율에도) → Gate C 인플레이션
        # > 1.0 → recovery_rate >= 1.0 초과 불가 → grade="good" 절대 부여 안 됨 → Gate C 과소
        if not (0.0 <= self.partial_success_threshold <= 1.0):
            _w.warn(
                f"FaultToleranceConfig: partial_success_threshold="
                f"{self.partial_success_threshold} is outside the [0.0, 1.0] range. Clamping. "
                f"If < 0, grade='good' is assigned even at a 0% recovery rate, inflating Gate C. "
                f"If > 1, grade='good' is never assigned and Gate C is under-computed.",
                UserWarning,
                stacklevel=2,
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

    partial_result_markers: list[str] = dataclasses.field(
        default_factory=lambda: [
            "partial",
            "incomplete",
            "best effort",
            "부분",
            "일부",
            "완전하지 않",
        ]
    )
    quality_floor: float = 0.3
    detect_timeout_fallback: bool = True
    timeout_threshold_ms: float | None = (
        None  # detect_timeout_fallback 실행 시간 기준(ms); None이면 도구명만 검사
    )
    empty_response_penalty: float = 1.0
    check_error_acknowledgment: bool = True

    def __post_init__(self) -> None:
        import warnings as _w

        # C-1: quality_floor > 1.0 → degradation_score > 1.0 → Gate C 집계 오염
        # quality_floor < 0.0 → 음수 점수 가능 → 마찬가지로 오염
        if not (0.0 <= self.quality_floor <= 1.0):
            _w.warn(
                f"GracefulDegradationConfig: quality_floor={self.quality_floor} is outside the "
                f"[0.0, 1.0] range. Clamping. If quality_floor > 1.0, degradation_score exceeds "
                f"1.0 and distorts the Gate C aggregate.",
                UserWarning,
                stacklevel=2,
            )
            self.quality_floor = max(0.0, min(1.0, self.quality_floor))
        # C-1: empty_response_penalty < 0.0 → 1.0 - negative > 1.0 → degradation_score > 1.0
        if self.empty_response_penalty < 0.0:
            _w.warn(
                f"GracefulDegradationConfig: empty_response_penalty={self.empty_response_penalty} "
                f"< 0; clamping to 0.0. A negative value makes the degradation_score of an empty "
                f"response exceed 1.0, distorting the Gate C aggregate.",
                UserWarning,
                stacklevel=2,
            )
            self.empty_response_penalty = 0.0
        # C-26: empty_response_penalty > 1.0 → max(0.0, 1.0 - penalty) = 0.0 → quality_floor와 동일
        # 1.0 초과 값은 수학적으로 추가 패널티 효과가 없으므로 사용자가 의도한 동작과 다를 수 있음
        elif self.empty_response_penalty > 1.0:
            _w.warn(
                f"GracefulDegradationConfig: empty_response_penalty={self.empty_response_penalty} "
                f"> 1.0. The degradation_score of an empty response is "
                f"max(quality_floor, max(0.0, 1.0 - penalty)). With penalty > 1.0, "
                f"score=quality_floor={self.quality_floor}, the same result as 1.0. "
                f"Clamping to 1.0.",
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
                f"GracefulDegradationConfig: timeout_threshold_ms={self.timeout_threshold_ms} < "
                f"0. Since execution_time >= 0ms, every task is misdiagnosed as "
                f"timeout_fallback=True. Clamping to timeout_threshold_ms=None to disable the "
                f"time-based timeout check. The tool-name-based fallback check "
                f"(detect_timeout_fallback=True + tool name 'fallback'/'default') is kept.",
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
                f"RetryConsistencyConfig: improvement_threshold={self.improvement_threshold} < 0; "
                f"clamping to 0.0. A negative threshold makes the consistency_score of a failed "
                f"task exceed 1.0, contaminating the Gate C aggregate.",
                UserWarning,
                stacklevel=2,
            )
            self.improvement_threshold = 0.0
        # C-13: min_retry_count <= 0 → 단일 시도 태스크도 재시도 평가 대상 (의미 위반)
        if self.min_retry_count < 1:
            _w.warn(
                f"RetryConsistencyConfig: min_retry_count={self.min_retry_count} < 1; "
                f"clamping to 1. With min_retry_count <= 0, tasks with no retries are also "
                f"evaluated, making retry-efficiency metrics inaccurate.",
                UserWarning,
                stacklevel=2,
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

    non_idempotent_patterns: list[str] = dataclasses.field(
        default_factory=lambda: [
            "create",
            "delete",
            "insert",
            "update",
            "post",
            "write",
            "생성",
            "삭제",
            "저장",
            "수정",
            "전송",
        ]
    )
    duplicate_detection_markers: list[str] = dataclasses.field(
        default_factory=lambda: [
            "already",
            "duplicate",
            "exists",
            "이미",
            "중복",
            "존재",
        ]
    )
    non_idempotent_penalty: float = 0.2
    warn_on_non_idempotent: bool = True

    def __post_init__(self) -> None:
        import warnings as _w

        # C-2: non_idempotent_penalty < 0 → penalty 음수 → 1.0 - negative > 1.0
        # → idempotency_score가 1.0을 초과해 Gate C 집계를 오염시킨다.
        if self.non_idempotent_penalty < 0.0:
            _w.warn(
                f"IdempotencyConfig: non_idempotent_penalty={self.non_idempotent_penalty} < 0; "
                f"clamping to the default 0.2. A negative penalty makes idempotency_score exceed "
                f"1.0, distorting the Gate C aggregate.",
                UserWarning,
                stacklevel=2,
            )
            self.non_idempotent_penalty = 0.2
        # C-18: penalty > 1.0 → 비멱등 도구 1개만 있어도 idempotency_score=0.0 고정
        # → 도구 수에 무관하게 Gate C 과소 산출 (Gate C deflation)
        if self.non_idempotent_penalty > 1.0:
            _w.warn(
                f"IdempotencyConfig: non_idempotent_penalty={self.non_idempotent_penalty} > 1.0. "
                f"A single non-idempotent tool makes idempotency_score=0.0. "
                f"If you want a deduction proportional to the tool count, set "
                f"penalty <= 1.0 / max_expected_tools.",
                UserWarning,
                stacklevel=2,
            )
