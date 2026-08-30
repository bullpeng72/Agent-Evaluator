"""
agent_evaluator.utils.confidence
===================================
단일 평가 run의 지표에 대한 신뢰구간·표본 적정성·판정 확신도를 계산하는 순수 함수.

새 통계 방법을 발명하지 않는다 — Wilson score interval(이항 비율)·백분위 부트스트랩
(평균)의 교과서 정의를 stdlib(``math``/``random``)만으로 구현한다. numpy/scipy 의존
없음(Layer independence 원칙). 모든 함수는 seed 고정으로 결정적이다 — 리포트를 다시
생성해도 신뢰구간 값이 흔들리지 않는다.

소비처: ``reporting/comprehensive_report.py``(헤더 CI · Executive Summary 확신도 배지 ·
Conclusion Grade 확신도).
"""
from __future__ import annotations

import math
import random
from collections.abc import Sequence

_Z_95 = 1.959963984540054  # Φ⁻¹(0.975) — 양측 95%


def wilson_interval(k: int, n: int, z: float = _Z_95) -> tuple[float, float]:
    """이항 비율 ``p = k/n``의 Wilson score 신뢰구간(0–1).

    표본이 작거나 p가 0/1에 가까울 때도 [0,1]을 벗어나지 않는다(정규근사 대비 장점).
    ``n <= 0``이면 정보 없음 → ``(0.0, 1.0)``.
    """
    if n <= 0:
        return (0.0, 1.0)
    k = max(0, min(k, n))
    phat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def bootstrap_mean_ci(
    values: Sequence[float],
    *,
    ci: float = 0.95,
    n_resamples: int = 2000,
    seed: int = 12345,
) -> tuple[float, float]:
    """평균의 백분위 부트스트랩 신뢰구간.

    ``completion_score``/``accuracy_score``처럼 [0,1] per-task 값의 평균(=TCR/100,
    accuracy/100)에 쓴다. 표본이 3개 미만이면 부트스트랩이 무의미하므로
    ``(min, max)``로 폴백한다. ``seed`` 고정 → 결정적.
    """
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n == 0:
        return (0.0, 0.0)
    if n < 3:
        return (min(vals), max(vals))
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += vals[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo_i = int((1.0 - ci) / 2.0 * n_resamples)
    hi_i = min(n_resamples - 1, int((1.0 + ci) / 2.0 * n_resamples))
    return (means[lo_i], means[hi_i])


def required_n_for_halfwidth(p: float, target_halfwidth: float, z: float = _Z_95) -> int:
    """비율 ``p``를 ±``target_halfwidth``(둘 다 0–1 스케일)로 추정하는 데 필요한
    대략적 표본 수 (정규근사: ``n ≈ z² p(1-p) / h²``)."""
    if target_halfwidth <= 0:
        return 0
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.ceil(z * z * p * (1.0 - p) / (target_halfwidth * target_halfwidth))


_LEVEL_ORDER = {"high": 2, "medium": 1, "low": 0}


def verdict_confidence(
    *,
    n_tasks: int,
    tcr_ci_halfwidth: float | None = None,
    n_gate_components: int | None = None,
    margin_to_threshold: float | None = None,
) -> tuple[str, list[str]]:
    """판정 전반의 확신도를 ``"high"`` / ``"medium"`` / ``"low"``로 종합한다.

    각 신호가 등급을 끌어내리며(올리진 못한다), 가장 낮은 등급이 최종이다.

    Args:
        n_tasks: 평가 태스크 수.
        tcr_ci_halfwidth: TCR 95% CI 반폭(0–1 스케일). 없으면 이 신호 무시.
        n_gate_components: fail/warn Gate 판정에 실제로 들어간 측정 컴포넌트 수.
        margin_to_threshold: Gate 점수 − 임계값(0–1). |margin|<0.05면 경계선 판정.

    Returns:
        ``(level, reasons)`` — ``reasons``는 등급을 끌어내린 요인 문자열만.
    """
    level = "high"
    reasons: list[str] = []

    def _demote(to: str, why: str) -> None:
        nonlocal level
        if _LEVEL_ORDER[to] < _LEVEL_ORDER[level]:
            level = to
        reasons.append(why)

    if n_tasks < 20:
        _demote("low", f"only {n_tasks} task(s) evaluated")
    elif n_tasks < 50:
        _demote("medium", f"{n_tasks} tasks (50+ recommended for a stable verdict)")

    if tcr_ci_halfwidth is not None:
        if tcr_ci_halfwidth > 0.30:
            _demote("low", f"TCR 95% CI spans ±{tcr_ci_halfwidth * 100:.0f}pp")
        elif tcr_ci_halfwidth > 0.15:
            _demote("medium", f"TCR 95% CI spans ±{tcr_ci_halfwidth * 100:.0f}pp")

    if n_gate_components is not None and n_gate_components > 0:
        if n_gate_components < 2:
            _demote("low", f"{n_gate_components} gate score component measured")
        elif n_gate_components < 4:
            _demote("medium", f"{n_gate_components} gate score components measured")

    if margin_to_threshold is not None and abs(margin_to_threshold) < 0.05:
        _demote("medium", "score is within 5% of the pass/fail threshold")

    return level, reasons
