"""
agent_evaluator.gates.gate_d_performance.configs
===================================================
Gate D(Performance Contract) Harness Config 데이터클래스 5종.

SPEC-000: agent_evaluator/decorators.py에서 그대로 이관(로직 변경 없음).
decorators.py는 이 모듈을 re-export하여 하위호환을 유지한다.

SLAConfig는 Gate C(Reliability)에도 breach_rate로 이중 기여한다 — CLAUDE.md
"SLAConfig dual contribution" 참조.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class SLAConfig:
    """SLA 준수 추적 설정.

    Example::

        @agent_eval(monitor, task_type="qa",
                    sla=SLAConfig(p95_ms=3000, max_cost_per_task=0.005))
        def agent(question, ground_truth=""): ...
    """

    p95_ms: float = 5000.0
    p99_ms: float = 10000.0
    ttft_ms: float | None = None
    breach_window: int = 10
    warn_threshold: int = 2
    fail_threshold: int = 5
    max_cost_per_task: float | None = None
    budget_usd: float | None = None
    token_limit: int | None = None  # 태스크당 최대 허용 토큰 수 (None = 제한 없음)

    def __post_init__(self) -> None:
        import warnings as _w

        # C-10: 음수 SLA 임계값은 모든 태스크가 breach로 처리돼 Gate C를 0에 수렴시킴
        if self.p95_ms < 0:
            _w.warn(
                f"SLAConfig: p95_ms={self.p95_ms} < 0; clamping to the default 5000.0. "
                f"A negative SLA threshold treats every task as a breach, driving Gate C toward 0.",
                UserWarning,
                stacklevel=2,
            )
            self.p95_ms = 5000.0
        if self.p99_ms < 0:
            _w.warn(
                f"SLAConfig: p99_ms={self.p99_ms} < 0; clamping to the default 10000.0. "
                f"A negative SLA threshold treats every task as a breach, driving Gate C toward 0.",
                UserWarning,
                stacklevel=2,
            )
            self.p99_ms = 10000.0
        # warn_threshold >= fail_threshold이면 경고 단계가 항상 실패로 처리됨
        if self.warn_threshold >= self.fail_threshold:
            _w.warn(
                f"SLAConfig: warn_threshold={self.warn_threshold} >= "
                f"fail_threshold={self.fail_threshold}. "
                f"warn_threshold must be less than fail_threshold.",
                UserWarning,
                stacklevel=2,
            )
        # C-15: p99_ms < p95_ms 역전 — p95 breach 없이 p99 breach가 발생할 수 없어
        # p99 임계값이 사실상 무효화되고 latency_ok 판정이 혼란스러워짐
        if self.p99_ms < self.p95_ms:
            _w.warn(
                f"SLAConfig: p99_ms={self.p99_ms} < p95_ms={self.p95_ms}. "
                f"Normally p99 >= p95. "
                f"With the current setting p99 becomes the stricter threshold, so "
                f"the latency_ok=False/True verdict can be counterintuitive.",
                UserWarning,
                stacklevel=2,
            )
        # C-21: breach_window <= 0 — Python list[-0:] = list[0:] = 전체 목록
        # breach_window=0이면 최근 N건 윈도우가 아닌 전체 결과를 기준으로 판정
        if self.breach_window <= 0:
            _w.warn(
                f"SLAConfig: breach_window={self.breach_window} <= 0. "
                f"With breach_window=0, Python slicing list[-0:]=list[0:] means the whole SLA "
                f"history is used as the window instead of the last "
                f"{abs(self.breach_window) or '?'} entries. "
                f"The Gate D window penalty is over-applied. Clamping to 1.",
                UserWarning,
                stacklevel=2,
            )
            self.breach_window = 1
        # C-22: warn_threshold/fail_threshold <= 0 → breach 0건에도 패널티 항상 발동
        if self.warn_threshold <= 0:
            _w.warn(
                f"SLAConfig: warn_threshold={self.warn_threshold} <= 0. "
                f"The warn penalty (Gate D -0.1) always fires even with 0 breaches. "
                f"Clamping to 1.",
                UserWarning,
                stacklevel=2,
            )
            self.warn_threshold = 1
        if self.fail_threshold <= 0:
            _w.warn(
                f"SLAConfig: fail_threshold={self.fail_threshold} <= 0. "
                f"The fail penalty (Gate D -0.3) always fires even with 0 breaches. "
                f"Clamping to 1.",
                UserWarning,
                stacklevel=2,
            )
            self.fail_threshold = 1
        # C-24: token_limit < 0 → _total_tokens <= negative 항상 False → 항상 토큰 breach
        # → Gate C SLA breach rate = 1.0 (의도치 않은 Gate C 왜곡)
        if self.token_limit is not None and self.token_limit < 0:
            _w.warn(
                f"SLAConfig: token_limit={self.token_limit} < 0. "
                f"No token usage can meet this limit, so an SLA breach always occurs. "
                f"The Gate C SLA breach rate becomes 1.0, distorting the Gate C score. "
                f"Clamping to 0.",
                UserWarning,
                stacklevel=2,
            )
            self.token_limit = 0
        # C-25: max_cost_per_task < 0 → cost_usd <= negative 항상 False → 항상 비용 breach
        if self.max_cost_per_task is not None and self.max_cost_per_task < 0.0:
            _w.warn(
                f"SLAConfig: max_cost_per_task={self.max_cost_per_task} < 0. "
                f"Cost always exceeds this negative limit, so an SLA breach always occurs. "
                f"The Gate C SLA breach rate becomes 1.0, distorting the Gate C score. "
                f"Clamping to 0.0.",
                UserWarning,
                stacklevel=2,
            )
            self.max_cost_per_task = 0.0
        # C-27: budget_usd < 0 → 세션 누적 비용이 항상 음수 한도를 초과
        # → max(budget_usd, 1e-9)로 0 나눗셈은 방어되나 _overage가 매우 큰 양수가 되어
        #   Gate D budget penalty가 항상 최대(0.3)로 적용됨
        if self.budget_usd is not None and self.budget_usd < 0.0:
            _w.warn(
                f"SLAConfig: budget_usd={self.budget_usd} < 0. "
                f"Cumulative session cost always exceeds a negative budget, so the Gate D budget "
                f"penalty is always applied at its maximum (-0.3). Clamping to 0.0.",
                UserWarning,
                stacklevel=2,
            )
            self.budget_usd = 0.0


@dataclasses.dataclass
class EfficiencyConfig:
    """비용 대비 완료율(ROI) 측정 설정.

    Example::

        @agent_eval(monitor, task_type="qa",
                    efficiency=EfficiencyConfig(cost_unit="usd", target_cost_per_completion=0.005))
        def agent(question, ground_truth=""): ...
    """

    cost_unit: str = "tokens"  # "tokens" | "usd" | "time_ms"
    target_cost_per_completion: float | None = None
    penalize_failed_tokens: bool = True
    warn_ratio: float = 2.0
    fail_ratio: float = 4.0
    # target_cost_per_completion을 설정하지 않아 calibrated_score가 계산되지 않을 때, Gate D가
    # efficiency_ratio를 0-1로 정규화하는 데 쓰는 기준 비용(이 cost_value가 completion_score=1.0
    # 달성에 필요한 비용이라고 가정하고 1.0점을 매긴다). None(기본값)이면 cost_unit별 기존
    # 하드코딩 기준값(tokens/time_ms=1000.0, usd=0.01)을 그대로 쓴다 — 비용 구조가 다른 팀은
    # target_cost_per_completion(calibrated_score, 권장) 대신 이 값만 조정해도 된다.
    fallback_reference_cost_per_completion: float | None = None

    def __post_init__(self) -> None:
        import warnings as _w

        if self.fallback_reference_cost_per_completion is not None and (
            self.fallback_reference_cost_per_completion <= 0
        ):
            _w.warn(
                f"EfficiencyConfig: fallback_reference_cost_per_completion="
                f"{self.fallback_reference_cost_per_completion} <= 0, so it is ignored and "
                f"the existing per-cost_unit default is used.",
                UserWarning,
                stacklevel=2,
            )
            self.fallback_reference_cost_per_completion = None
        # D-1: cost_unit이 유효하지 않으면 efficiency_ratio 계산에서 "tokens" 폴백되지만
        # 사용자가 오타임을 알 수 없어 의도와 다른 지표가 Gate D에 기여됨
        _valid_units = ("tokens", "usd", "time_ms")
        if self.cost_unit not in _valid_units:
            _w.warn(
                f"EfficiencyConfig: cost_unit={self.cost_unit!r} is not valid. "
                f"Allowed values: {_valid_units}. Clamping to the default 'tokens'.",
                UserWarning,
                stacklevel=2,
            )
            self.cost_unit = "tokens"
        # D-2: warn_ratio <= 0 또는 fail_ratio <= 0 → 계산식 내 max(warn_ratio-1.0, 1e-6)으로
        # 처리되지만 사용자가 오류를 인식할 수 없음
        if self.warn_ratio <= 0:
            _w.warn(
                f"EfficiencyConfig: warn_ratio={self.warn_ratio} <= 0; "
                f"clamping to the default 2.0. warn_ratio must be an allowed multiple of the "
                f"target cost (> 1.0).",
                UserWarning,
                stacklevel=2,
            )
            self.warn_ratio = 2.0
        if self.fail_ratio <= 0:
            _w.warn(
                f"EfficiencyConfig: fail_ratio={self.fail_ratio} <= 0; "
                f"clamping to the default 4.0. fail_ratio must be the fail-verdict multiple of "
                f"the target cost (> warn_ratio).",
                UserWarning,
                stacklevel=2,
            )
            self.fail_ratio = 4.0
        # D-3: warn_ratio <= 1.0 → "목표 비용 이하에서도 warn" — excellent 구간(≤1.0)에서
        # 바로 warn으로 넘어가 good 구간이 존재하지 않음 (의미 위반)
        if self.warn_ratio <= 1.0:
            _w.warn(
                f"EfficiencyConfig: warn_ratio={self.warn_ratio} <= 1.0. "
                f"warn_ratio is a multiple of the target cost, so it must be above 1.0. "
                f"With the current setting, warn fires immediately after the excellent (<= 1.0x) "
                f"band.",
                UserWarning,
                stacklevel=2,
            )
        # D-4: warn_ratio >= fail_ratio → SLAConfig의 warn_threshold >= fail_threshold와 동일 결함.
        # calibrated_score 계산에서 "warn" 단계가 스킵되어 good → fail로 직행함
        if self.warn_ratio >= self.fail_ratio:
            _w.warn(
                f"EfficiencyConfig: warn_ratio={self.warn_ratio} >= fail_ratio={self.fail_ratio}. "
                f"warn_ratio must be < fail_ratio. "
                f"With the current setting there is no 'warn' efficiency step, so "
                f"calibrated_score jumps straight from 'good' to 'fail'.",
                UserWarning,
                stacklevel=2,
            )


@dataclasses.dataclass
class ResourceBudgetConfig:
    """리소스 예산 초과 감지 설정 (Harness D — Performance Contract).

    Example::

        @agent_eval(monitor, task_type="qa",
                    resource_budget=ResourceBudgetConfig(max_tokens=2000, max_cost_usd=0.05))
        def agent(question, ground_truth=""): ...
    """

    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_execution_time_ms: float | None = None
    warn_at_pct: float = 0.8
    count_failed_tokens: bool = True
    rollover: bool = False

    def __post_init__(self) -> None:
        import warnings as _w

        # D-5: warn_at_pct > 1.0 → 경고가 예산 초과 이후에만 발동 (경고 기능 무력화)
        if self.warn_at_pct > 1.0:
            _w.warn(
                f"ResourceBudgetConfig: warn_at_pct={self.warn_at_pct} > 1.0. "
                f"warn_at_pct is a budget-utilization fraction (0-1), not a percentage (0-100). "
                f"Above 1.0, the warning never fires even after the budget is already exceeded. "
                f"Clamping to the default 0.8.",
                UserWarning,
                stacklevel=2,
            )
            self.warn_at_pct = 0.8
        # D-6: warn_at_pct <= 0 → utilization(0 이상)이 항상 warn 영역에 진입
        if self.warn_at_pct <= 0.0:
            _w.warn(
                f"ResourceBudgetConfig: warn_at_pct={self.warn_at_pct} <= 0. "
                f"Every resource use is immediately classified as warn, making the warning "
                f"meaningless. Clamping to the default 0.8.",
                UserWarning,
                stacklevel=2,
            )
            self.warn_at_pct = 0.8
        # D-7: 모든 한도가 None이면 ResourceBudget 평가 자체가 집계에서 제외됨 (Gate D 미기여)
        # 이것은 의도된 동작이지만 사용자가 놓치기 쉬우므로 경고
        if (
            self.max_tokens is None
            and self.max_cost_usd is None
            and self.max_execution_time_ms is None
        ):
            _w.warn(
                "ResourceBudgetConfig: max_tokens, max_cost_usd, and max_execution_time_ms are "
                "all None. At least one limit must be set for the Gate D resource_budget score "
                "to be computed. With the current setting, budget_score=None and it is excluded "
                "from the Gate D aggregate.",
                UserWarning,
                stacklevel=2,
            )


@dataclasses.dataclass
class TTFTVariabilityConfig:
    """TTFT(Time To First Token) 변동성 측정 설정 (Harness D — Performance Contract).

    이 Config는 ``PerformanceMonitor`` 레벨에서 자동 집계되므로
    ``_build_and_record`` 파라미터가 아닌 타입 힌트용으로만 제공된다.

    Example::

        # 이 Config는 현재 decorator param으로 전달하지 않음.
        # monitor._compute_harness_groups()에서 ttft_ms 자동 집계.
        cfg = TTFTVariabilityConfig(max_stddev_ms=300.0)
    """

    max_stddev_ms: float = 500.0
    max_p95_p50_ratio: float = 3.0
    min_samples: int = 5
    remove_outliers: bool = True

    def __post_init__(self) -> None:
        import warnings as _w

        # D-8: max_stddev_ms <= 0 → 1.0 - stddev / max(0, 1.0) 계산에서 _ttft_max_std=1.0으로 보정되나
        # stddev가 1ms만 넘어도 std_score=0.0이 돼 TTFT 변동성 점수가 항상 0에 수렴
        if self.max_stddev_ms <= 0:
            _w.warn(
                f"TTFTVariabilityConfig: max_stddev_ms={self.max_stddev_ms} <= 0; "
                f"clamping to the default 500.0. At 0 or less, even a 1ms deviation makes "
                f"std_score=0.0, so the TTFT variability score always converges to 0.",
                UserWarning,
                stacklevel=2,
            )
            self.max_stddev_ms = 500.0
        # D-9: max_p95_p50_ratio < 1.0 → ratio_score 계산에서 max_ratio - 1.0 ≤ 0
        # max(max_p95_p50_ratio - 1.0, 1.0) 분모가 1.0으로 고정돼 ratio_score가 의도치 않게 낮아짐
        if self.max_p95_p50_ratio < 1.0:
            _w.warn(
                f"TTFTVariabilityConfig: max_p95_p50_ratio={self.max_p95_p50_ratio} < 1.0. "
                f"The p95/p50 ratio is always >= 1.0, so with max_p95_p50_ratio < 1.0 the "
                f"denominator of the ratio_score formula is pinned to 1.0 and every TTFT "
                f"converges to score=0.0. Clamping to the default 3.0.",
                UserWarning,
                stacklevel=2,
            )
            self.max_p95_p50_ratio = 3.0
        # D-10: min_samples <= 0 → len(_ttft_values) >= 0은 항상 True → min_samples 기능 무력화
        if self.min_samples <= 0:
            _w.warn(
                f"TTFTVariabilityConfig: min_samples={self.min_samples} <= 0; "
                f"clamping to the default 5. At 0 or less, variability is computed even with 0 "
                f"TTFT values.",
                UserWarning,
                stacklevel=2,
            )
            self.min_samples = 5


@dataclasses.dataclass
class CostPredictabilityConfig:
    """비용 예측 가능성 평가 설정 (Group D — Performance Contract).

    동일 task_type 내 토큰/비용의 변동 계수(CV)를 측정하여 비용 안정성을 평가한다.
    모니터 수준에서 집계되며, 태스크 단위 extra에는 저장되지 않는다.

    Example::

        monitor = PerformanceMonitor("results/")
        # CostPredictabilityConfig는 _compute_harness_groups()에서 자동 사용됨
    """

    max_coefficient_of_variation: float = 0.3
    outlier_multiplier: float = 3.0
    min_samples: int = 5
    cost_metric: str = "tokens"  # "tokens" | "usd" | "time_ms"

    def __post_init__(self) -> None:
        import warnings as _w

        # D-11: cost_metric 유효하지 않은 값 → _compute_harness_groups에서 "tokens" 폴백되지만
        # 사용자가 오타임을 알 수 없어 의도와 다른 지표로 CV가 계산됨
        _valid_metrics = ("tokens", "usd", "time_ms")
        if self.cost_metric not in _valid_metrics:
            _w.warn(
                f"CostPredictabilityConfig: cost_metric={self.cost_metric!r} is not valid. "
                f"Allowed values: {_valid_metrics}. Clamping to the default 'tokens'.",
                UserWarning,
                stacklevel=2,
            )
            self.cost_metric = "tokens"
        # D-12: max_coefficient_of_variation <= 0 → max(_cost_max_cv, 0.01)으로 보정되지만 경고 없음
        if self.max_coefficient_of_variation <= 0:
            _w.warn(
                f"CostPredictabilityConfig: max_coefficient_of_variation="
                f"{self.max_coefficient_of_variation} <= 0; clamping to the default 0.3. "
                f"At 0 or less, even a tiny CV converges to score=0.0.",
                UserWarning,
                stacklevel=2,
            )
            self.max_coefficient_of_variation = 0.3
        # D-13: min_samples <= 0 → len(tasks) >= 0은 항상 True → min_samples 기능 무력화
        if self.min_samples <= 0:
            _w.warn(
                f"CostPredictabilityConfig: min_samples={self.min_samples} <= 0; "
                f"clamping to the default 5. At 0 or less, CV is computed even with 0 tasks.",
                UserWarning,
                stacklevel=2,
            )
            self.min_samples = 5
        # D-14: outlier_multiplier <= 0 → _filter_outliers가 모든 값을 이상치로 제거할 수 있음
        if self.outlier_multiplier <= 0:
            _w.warn(
                f"CostPredictabilityConfig: outlier_multiplier={self.outlier_multiplier} <= 0; "
                f"clamping to the default 3.0. At 0 or less, every cost value is removed as an "
                f"outlier and the cost_predictability score is not computed.",
                UserWarning,
                stacklevel=2,
            )
            self.outlier_multiplier = 3.0
