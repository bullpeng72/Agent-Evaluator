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
    token_limit: int | None = None          # 태스크당 최대 허용 토큰 수 (None = 제한 없음)

    def __post_init__(self) -> None:
        import warnings as _w
        # C-10: 음수 SLA 임계값은 모든 태스크가 breach로 처리돼 Gate C를 0에 수렴시킴
        if self.p95_ms < 0:
            _w.warn(
                f"SLAConfig: p95_ms={self.p95_ms} < 0 이므로 기본값 5000.0으로 보정됩니다. "
                f"음수 SLA 임계값은 모든 태스크가 breach로 처리되어 Gate C를 0에 수렴시킵니다.",
                UserWarning, stacklevel=2,
            )
            self.p95_ms = 5000.0
        if self.p99_ms < 0:
            _w.warn(
                f"SLAConfig: p99_ms={self.p99_ms} < 0 이므로 기본값 10000.0으로 보정됩니다. "
                f"음수 SLA 임계값은 모든 태스크가 breach로 처리되어 Gate C를 0에 수렴시킵니다.",
                UserWarning, stacklevel=2,
            )
            self.p99_ms = 10000.0
        # warn_threshold >= fail_threshold이면 경고 단계가 항상 실패로 처리됨
        if self.warn_threshold >= self.fail_threshold:
            _w.warn(
                f"SLAConfig: warn_threshold={self.warn_threshold} >= "
                f"fail_threshold={self.fail_threshold}. "
                f"warn_threshold는 fail_threshold보다 작아야 합니다.",
                UserWarning, stacklevel=2,
            )
        # C-15: p99_ms < p95_ms 역전 — p95 breach 없이 p99 breach가 발생할 수 없어
        # p99 임계값이 사실상 무효화되고 latency_ok 판정이 혼란스러워짐
        if self.p99_ms < self.p95_ms:
            _w.warn(
                f"SLAConfig: p99_ms={self.p99_ms} < p95_ms={self.p95_ms}. "
                f"일반적으로 p99 >= p95여야 합니다. "
                f"현재 설정에서는 p99가 더 엄격한 임계값이 되어 "
                f"latency_ok=False/True 판정이 직관에 반할 수 있습니다.",
                UserWarning, stacklevel=2,
            )
        # C-21: breach_window <= 0 — Python list[-0:] = list[0:] = 전체 목록
        # breach_window=0이면 최근 N건 윈도우가 아닌 전체 결과를 기준으로 판정
        if self.breach_window <= 0:
            _w.warn(
                f"SLAConfig: breach_window={self.breach_window} <= 0. "
                f"breach_window=0이면 Python 슬라이싱 list[-0:]=list[0:]으로 인해 "
                f"최근 {abs(self.breach_window) or '?'}건이 아닌 전체 SLA 기록을 윈도우로 사용하게 됩니다. "
                f"Gate D 윈도우 패널티가 과대 적용됩니다. 1로 보정합니다.",
                UserWarning, stacklevel=2,
            )
            self.breach_window = 1
        # C-22: warn_threshold/fail_threshold <= 0 → breach 0건에도 패널티 항상 발동
        if self.warn_threshold <= 0:
            _w.warn(
                f"SLAConfig: warn_threshold={self.warn_threshold} <= 0. "
                f"breach가 0건이어도 warn 패널티(Gate D -0.1)가 항상 발동됩니다. "
                f"1로 보정합니다.",
                UserWarning, stacklevel=2,
            )
            self.warn_threshold = 1
        if self.fail_threshold <= 0:
            _w.warn(
                f"SLAConfig: fail_threshold={self.fail_threshold} <= 0. "
                f"breach가 0건이어도 fail 패널티(Gate D -0.3)가 항상 발동됩니다. "
                f"1로 보정합니다.",
                UserWarning, stacklevel=2,
            )
            self.fail_threshold = 1
        # C-24: token_limit < 0 → _total_tokens <= negative 항상 False → 항상 토큰 breach
        # → Gate C SLA breach rate = 1.0 (의도치 않은 Gate C 왜곡)
        if self.token_limit is not None and self.token_limit < 0:
            _w.warn(
                f"SLAConfig: token_limit={self.token_limit} < 0. "
                f"어떤 토큰 사용량도 이 한도를 충족할 수 없어 항상 SLA breach가 발생합니다. "
                f"Gate C SLA breach rate가 1.0이 되어 Gate C 점수가 왜곡됩니다. "
                f"0으로 보정합니다.",
                UserWarning, stacklevel=2,
            )
            self.token_limit = 0
        # C-25: max_cost_per_task < 0 → cost_usd <= negative 항상 False → 항상 비용 breach
        if self.max_cost_per_task is not None and self.max_cost_per_task < 0.0:
            _w.warn(
                f"SLAConfig: max_cost_per_task={self.max_cost_per_task} < 0. "
                f"비용이 항상 이 음수 한도를 초과하여 항상 SLA breach가 발생합니다. "
                f"Gate C SLA breach rate가 1.0이 되어 Gate C 점수가 왜곡됩니다. "
                f"0.0으로 보정합니다.",
                UserWarning, stacklevel=2,
            )
            self.max_cost_per_task = 0.0
        # C-27: budget_usd < 0 → 세션 누적 비용이 항상 음수 한도를 초과
        # → max(budget_usd, 1e-9)로 0 나눗셈은 방어되나 _overage가 매우 큰 양수가 되어
        #   Gate D budget penalty가 항상 최대(0.3)로 적용됨
        if self.budget_usd is not None and self.budget_usd < 0.0:
            _w.warn(
                f"SLAConfig: budget_usd={self.budget_usd} < 0. "
                f"세션 누적 비용이 항상 음수 예산을 초과하여 Gate D budget 패널티가 "
                f"항상 최대(-0.3)로 적용됩니다. 0.0으로 보정합니다.",
                UserWarning, stacklevel=2,
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
    cost_unit: str = "tokens"   # "tokens" | "usd" | "time_ms"
    target_cost_per_completion: float | None = None
    penalize_failed_tokens: bool = True
    warn_ratio: float = 2.0
    fail_ratio: float = 4.0

    def __post_init__(self) -> None:
        import warnings as _w
        # D-1: cost_unit이 유효하지 않으면 efficiency_ratio 계산에서 "tokens" 폴백되지만
        # 사용자가 오타임을 알 수 없어 의도와 다른 지표가 Gate D에 기여됨
        _valid_units = ("tokens", "usd", "time_ms")
        if self.cost_unit not in _valid_units:
            _w.warn(
                f"EfficiencyConfig: cost_unit={self.cost_unit!r}은 유효하지 않습니다. "
                f"허용 값: {_valid_units}. 기본값 'tokens'로 보정됩니다.",
                UserWarning, stacklevel=2,
            )
            self.cost_unit = "tokens"
        # D-2: warn_ratio <= 0 또는 fail_ratio <= 0 → 계산식 내 max(warn_ratio-1.0, 1e-6)으로
        # 처리되지만 사용자가 오류를 인식할 수 없음
        if self.warn_ratio <= 0:
            _w.warn(
                f"EfficiencyConfig: warn_ratio={self.warn_ratio} <= 0 이므로 "
                f"기본값 2.0으로 보정됩니다. warn_ratio는 목표 비용 대비 허용 배수(>1.0)여야 합니다.",
                UserWarning, stacklevel=2,
            )
            self.warn_ratio = 2.0
        if self.fail_ratio <= 0:
            _w.warn(
                f"EfficiencyConfig: fail_ratio={self.fail_ratio} <= 0 이므로 "
                f"기본값 4.0으로 보정됩니다. fail_ratio는 목표 비용 대비 실패 판정 배수(>warn_ratio)여야 합니다.",
                UserWarning, stacklevel=2,
            )
            self.fail_ratio = 4.0
        # D-3: warn_ratio <= 1.0 → "목표 비용 이하에서도 warn" — excellent 구간(≤1.0)에서
        # 바로 warn으로 넘어가 good 구간이 존재하지 않음 (의미 위반)
        if self.warn_ratio <= 1.0:
            _w.warn(
                f"EfficiencyConfig: warn_ratio={self.warn_ratio} <= 1.0. "
                f"warn_ratio는 목표 비용 대비 배수이므로 1.0 초과여야 합니다. "
                f"현재 설정에서는 excellent(≤1.0x) 구간 바로 다음에 warn이 발동됩니다.",
                UserWarning, stacklevel=2,
            )
        # D-4: warn_ratio >= fail_ratio → SLAConfig의 warn_threshold >= fail_threshold와 동일 결함.
        # calibrated_score 계산에서 "warn" 단계가 스킵되어 good → fail로 직행함
        if self.warn_ratio >= self.fail_ratio:
            _w.warn(
                f"EfficiencyConfig: warn_ratio={self.warn_ratio} >= fail_ratio={self.fail_ratio}. "
                f"warn_ratio < fail_ratio 여야 합니다. "
                f"현재 설정에서는 'warn' 효율 단계가 존재하지 않아 "
                f"calibrated_score가 'good'에서 'fail'로 직행합니다.",
                UserWarning, stacklevel=2,
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
                f"warn_at_pct는 예산 사용률 분율(0–1)입니다 — 퍼센트(0–100)가 아닙니다. "
                f"1.0 초과이면 예산을 이미 초과한 후에도 경고가 발동되지 않습니다. "
                f"기본값 0.8로 보정됩니다.",
                UserWarning, stacklevel=2,
            )
            self.warn_at_pct = 0.8
        # D-6: warn_at_pct <= 0 → utilization(0 이상)이 항상 warn 영역에 진입
        if self.warn_at_pct <= 0.0:
            _w.warn(
                f"ResourceBudgetConfig: warn_at_pct={self.warn_at_pct} <= 0. "
                f"모든 리소스 사용이 즉시 warn으로 분류되어 경고가 무의미해집니다. "
                f"기본값 0.8로 보정됩니다.",
                UserWarning, stacklevel=2,
            )
            self.warn_at_pct = 0.8
        # D-7: 모든 한도가 None이면 ResourceBudget 평가 자체가 집계에서 제외됨 (Gate D 미기여)
        # 이것은 의도된 동작이지만 사용자가 놓치기 쉬우므로 경고
        if self.max_tokens is None and self.max_cost_usd is None and self.max_execution_time_ms is None:
            _w.warn(
                "ResourceBudgetConfig: max_tokens, max_cost_usd, max_execution_time_ms가 모두 None입니다. "
                "최소 하나 이상의 한도를 설정해야 Gate D resource_budget 점수가 산출됩니다. "
                "현재 설정에서는 budget_score=None이 되어 Gate D 집계에서 제외됩니다.",
                UserWarning, stacklevel=2,
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
                f"TTFTVariabilityConfig: max_stddev_ms={self.max_stddev_ms} <= 0 이므로 "
                f"기본값 500.0으로 보정됩니다. 0 이하이면 1ms 편차만 있어도 std_score=0.0이 돼 "
                f"TTFT 변동성 점수가 항상 0에 수렴합니다.",
                UserWarning, stacklevel=2,
            )
            self.max_stddev_ms = 500.0
        # D-9: max_p95_p50_ratio < 1.0 → ratio_score 계산에서 max_ratio - 1.0 ≤ 0
        # max(max_p95_p50_ratio - 1.0, 1.0) 분모가 1.0으로 고정돼 ratio_score가 의도치 않게 낮아짐
        if self.max_p95_p50_ratio < 1.0:
            _w.warn(
                f"TTFTVariabilityConfig: max_p95_p50_ratio={self.max_p95_p50_ratio} < 1.0. "
                f"p95/p50 비율은 항상 ≥ 1.0이므로 max_p95_p50_ratio < 1.0이면 "
                f"ratio_score 계산식의 분모가 1.0으로 고정돼 모든 TTFT가 score=0.0에 수렴합니다. "
                f"기본값 3.0으로 보정됩니다.",
                UserWarning, stacklevel=2,
            )
            self.max_p95_p50_ratio = 3.0
        # D-10: min_samples <= 0 → len(_ttft_values) >= 0은 항상 True → min_samples 기능 무력화
        if self.min_samples <= 0:
            _w.warn(
                f"TTFTVariabilityConfig: min_samples={self.min_samples} <= 0 이므로 "
                f"기본값 5로 보정됩니다. 0 이하이면 TTFT 값 0건으로도 변동성 계산을 시도합니다.",
                UserWarning, stacklevel=2,
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
                f"CostPredictabilityConfig: cost_metric={self.cost_metric!r}은 유효하지 않습니다. "
                f"허용 값: {_valid_metrics}. 기본값 'tokens'로 보정됩니다.",
                UserWarning, stacklevel=2,
            )
            self.cost_metric = "tokens"
        # D-12: max_coefficient_of_variation <= 0 → max(_cost_max_cv, 0.01)으로 보정되지만 경고 없음
        if self.max_coefficient_of_variation <= 0:
            _w.warn(
                f"CostPredictabilityConfig: max_coefficient_of_variation={self.max_coefficient_of_variation} <= 0 이므로 "
                f"기본값 0.3으로 보정됩니다. 0 이하이면 CV가 아주 작아도 score=0.0에 수렴합니다.",
                UserWarning, stacklevel=2,
            )
            self.max_coefficient_of_variation = 0.3
        # D-13: min_samples <= 0 → len(tasks) >= 0은 항상 True → min_samples 기능 무력화
        if self.min_samples <= 0:
            _w.warn(
                f"CostPredictabilityConfig: min_samples={self.min_samples} <= 0 이므로 "
                f"기본값 5로 보정됩니다. 0 이하이면 태스크 0건으로도 CV 계산을 시도합니다.",
                UserWarning, stacklevel=2,
            )
            self.min_samples = 5
        # D-14: outlier_multiplier <= 0 → _filter_outliers가 모든 값을 이상치로 제거할 수 있음
        if self.outlier_multiplier <= 0:
            _w.warn(
                f"CostPredictabilityConfig: outlier_multiplier={self.outlier_multiplier} <= 0 이므로 "
                f"기본값 3.0으로 보정됩니다. 0 이하이면 모든 비용 값이 이상치로 제거돼 "
                f"cost_predictability 점수가 산출되지 않습니다.",
                UserWarning, stacklevel=2,
            )
            self.outlier_multiplier = 3.0
