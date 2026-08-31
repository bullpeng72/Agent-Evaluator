"""
agent_evaluator.utils.confidence
===================================
단일 평가 run의 지표에 대한 신뢰구간·표본 적정성·판정 확신도를 계산하는 순수 함수.

새 통계 방법을 발명하지 않는다 — Wilson score interval(이항 비율)·백분위 부트스트랩
(평균)의 교과서 정의를 stdlib(``math``/``random``)만으로 구현한다. numpy/scipy 의존
없음(Layer independence 원칙). 모든 함수는 seed 고정으로 결정적이다 — 리포트를 다시
생성해도 신뢰구간 값이 흔들리지 않는다.

소비처: ``reporting/comprehensive_report.py``(헤더 CI · Executive Summary 확신도 배지 ·
Conclusion Grade 확신도) · ``reporting/insights.py``(per-slice 유의성) · ``cli/abtest.py``
(MDE/검정력 라인).
"""
from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Any

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


def bootstrap_diff_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    ci: float = 0.95,
    n_resamples: int = 2000,
    seed: int = 12345,
) -> tuple[float, float] | None:
    """``mean(a) - mean(b)``의 백분위 부트스트랩 신뢰구간 (0–1 per-task 값 기준).

    두 슬라이스(예: current vs baseline의 같은 task_type)를 각각 복원추출해 평균차
    분포를 만든다. CI가 0을 포함하지 않으면 그 차이는 통계적으로 유의하다고 본다.
    어느 한쪽이라도 3개 미만이면 판정 불가 → ``None``.
    """
    av = [float(v) for v in a if v is not None]
    bv = [float(v) for v in b if v is not None]
    if len(av) < 3 or len(bv) < 3:
        return None
    rng = random.Random(seed)
    na, nb = len(av), len(bv)
    diffs: list[float] = []
    for _ in range(n_resamples):
        sa = sum(av[rng.randrange(na)] for _ in range(na)) / na
        sb = sum(bv[rng.randrange(nb)] for _ in range(nb)) / nb
        diffs.append(sa - sb)
    diffs.sort()
    lo_i = int((1.0 - ci) / 2.0 * n_resamples)
    hi_i = min(n_resamples - 1, int((1.0 + ci) / 2.0 * n_resamples))
    return (diffs[lo_i], diffs[hi_i])


def welch_t_p(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Two-sided p-value for ``mean(a) != mean(b)`` — Welch's t-test with a
    normal approximation to the reference distribution (stdlib only, no scipy).

    For the sample sizes typical of an eval run the normal approximation to the
    t-distribution is close enough to rank / FDR-adjust pairwise comparisons.
    Returns ``None`` when either group has < 2 values or zero pooled variance.
    """
    av = [float(v) for v in a if v is not None]
    bv = [float(v) for v in b if v is not None]
    na, nb = len(av), len(bv)
    if na < 2 or nb < 2:
        return None
    ma = sum(av) / na
    mb = sum(bv) / nb
    va = sum((x - ma) ** 2 for x in av) / (na - 1)
    vb = sum((x - mb) ** 2 for x in bv) / (nb - 1)
    se2 = va / na + vb / nb
    if se2 <= 0:
        return 0.0 if ma != mb else 1.0
    t = (ma - mb) / math.sqrt(se2)
    # two-sided p under N(0,1): 2 * (1 - Phi(|t|))
    phi = 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2.0)))
    return max(0.0, min(1.0, 2.0 * (1.0 - phi)))


def required_n_for_halfwidth(p: float, target_halfwidth: float, z: float = _Z_95) -> int:
    """비율 ``p``를 ±``target_halfwidth``(둘 다 0–1 스케일)로 추정하는 데 필요한
    대략적 표본 수 (정규근사: ``n ≈ z² p(1-p) / h²``)."""
    if target_halfwidth <= 0:
        return 0
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.ceil(z * z * p * (1.0 - p) / (target_halfwidth * target_halfwidth))


_Z_POWER_80 = 0.8416212335729143  # Φ⁻¹(0.80) — one-sided power 0.80


def mde_two_proportions(
    n_a: int,
    n_b: int,
    p_pooled: float = 0.5,
    *,
    z_alpha: float = _Z_95,
    z_power: float = _Z_POWER_80,
) -> float | None:
    """두 비율 비교(A/B)에서 주어진 표본 수로 탐지 가능한 **최소 효과 크기**(MDE),
    0–1 스케일. 관측된 차이가 이 값보다 작으면 "표본이 부족해 노이즈와 구분 불가".

    정규근사 표준식::

        MDE ≈ (z_α/2 + z_β) · sqrt( p(1-p)·(1/n_a + 1/n_b) )

    ``p_pooled``는 두 그룹 합산 비율(모르면 0.5 — 가장 보수적, MDE 최대). 표본이
    없으면 ``None``.
    """
    if n_a <= 0 or n_b <= 0:
        return None
    p = min(max(p_pooled, 1e-6), 1.0 - 1e-6)
    se = math.sqrt(p * (1.0 - p) * (1.0 / n_a + 1.0 / n_b))
    return (z_alpha + z_power) * se


def expected_calibration_error(
    pairs: Sequence[tuple[float, float]], *, n_bins: int = 10,
) -> dict[str, Any] | None:
    """Expected Calibration Error for ``[(confidence, correct 0/1), …]``.

    Bins predictions by confidence into ``n_bins`` equal-width buckets; ECE is the
    sample-weighted mean gap between bucket confidence and bucket accuracy::

        ECE = Σ_b (n_b / N) · | acc_b − conf_b |

    Returns ``{ece, mce, n, bins:[{lo, hi, n, mean_conf, accuracy, gap}]}`` or
    ``None`` when there are no usable pairs. ``mce`` is the worst single bucket gap.
    """
    xs = [
        (min(max(float(c), 0.0), 1.0), 1.0 if y else 0.0)
        for c, y in pairs
        if c is not None
    ]
    if not xs:
        return None
    n = len(xs)
    bins: list[dict[str, Any]] = []
    ece = 0.0
    mce = 0.0
    for b in range(n_bins):
        lo = b / n_bins
        hi = (b + 1) / n_bins
        members = [
            (c, y) for c, y in xs
            if (c > lo or (b == 0 and c == 0.0)) and c <= hi
        ]
        if not members:
            continue
        nb = len(members)
        mean_conf = sum(c for c, _ in members) / nb
        acc = sum(y for _, y in members) / nb
        gap = abs(acc - mean_conf)
        ece += (nb / n) * gap
        mce = max(mce, gap)
        bins.append({
            "lo": round(lo, 3), "hi": round(hi, 3), "n": nb,
            "mean_conf": round(mean_conf, 4), "accuracy": round(acc, 4),
            "gap": round(gap, 4),
        })
    return {"ece": round(ece, 4), "mce": round(mce, 4), "n": n, "bins": bins}


def pearson_r(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson correlation of two equal-length numeric sequences (stdlib).
    ``None`` when < 3 pairs or either side has zero variance."""
    pairs = [
        (float(a), float(b)) for a, b in zip(xs, ys)
        if a is not None and b is not None
    ]
    n = len(pairs)
    if n < 3:
        return None
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    sxx = sum((a - mx) ** 2 for a, _ in pairs)
    syy = sum((b - my) ** 2 for _, b in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((a - mx) * (b - my) for a, b in pairs)
    return round(sxy / math.sqrt(sxx * syy), 4)


def brier_score(pairs: Sequence[tuple[float, float]]) -> float | None:
    """Mean squared error of the confidences: ``Σ (conf − correct)² / N``.
    Lower is better; 0.25 is the coin-flip baseline for a balanced set."""
    xs = [
        (min(max(float(c), 0.0), 1.0), 1.0 if y else 0.0)
        for c, y in pairs if c is not None
    ]
    if not xs:
        return None
    return round(sum((c - y) ** 2 for c, y in xs) / len(xs), 4)


def risk_coverage_points(
    pairs: Sequence[tuple[float, float]],
    *,
    coverages: Sequence[float] = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5),
) -> list[dict[str, float]] | None:
    """Selective-prediction risk/coverage curve. Sort by confidence desc, then for
    each target coverage take that top fraction and report its error rate::

        [{coverage, n, risk}]   risk = 1 − accuracy over the retained slice

    A well-calibrated model's risk drops as coverage shrinks (it abstains on the
    ones it is least sure of first). ``None`` when there are no pairs.
    """
    xs = sorted(
        (
            (min(max(float(c), 0.0), 1.0), 1.0 if y else 0.0)
            for c, y in pairs if c is not None
        ),
        key=lambda t: -t[0],
    )
    if not xs:
        return None
    n = len(xs)
    out: list[dict[str, float]] = []
    seen: set[int] = set()
    for cov in coverages:
        k = max(1, int(round(cov * n)))
        if k in seen:
            continue
        seen.add(k)
        slice_ = xs[:k]
        acc = sum(y for _, y in slice_) / k
        out.append({
            "coverage": round(k / n, 3), "n": k, "risk": round(1.0 - acc, 4),
        })
    return out


_LEVEL_ORDER = {"high": 2, "medium": 1, "low": 0}


def verdict_confidence(
    *,
    n_tasks: int,
    tcr_ci_halfwidth: float | None = None,
    n_gate_components: int | None = None,
    margin_to_threshold: float | None = None,
    judge_trust: str | None = None,
) -> tuple[str, list[str]]:
    """판정 전반의 확신도를 ``"high"`` / ``"medium"`` / ``"low"``로 종합한다.

    각 신호가 등급을 끌어내리며(올리진 못한다), 가장 낮은 등급이 최종이다.

    Args:
        n_tasks: 평가 태스크 수.
        tcr_ci_halfwidth: TCR 95% CI 반폭(0–1 스케일). 없으면 이 신호 무시.
        n_gate_components: fail/warn Gate 판정에 실제로 들어간 측정 컴포넌트 수.
        margin_to_threshold: Gate 점수 − 임계값(0–1). |margin|<0.05면 경계선 판정.
        judge_trust: 평가기(LLM judge) 신뢰도 ``"high"``/``"medium"``/``"low"``
            (SPEC-041 P14, ``insights.evaluator_trust.trust_level``). judge가
            휴리스틱과 불일치하거나·비보정·비일관이면 그 위에 쌓은 판정도 그만큼만
            믿을 수 있으므로 확신도를 같은 등급으로 끌어내린다. 없으면 이 신호 무시.

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

    if judge_trust == "low":
        _demote("low", "the evaluator (LLM judge) is unreliable for this run")
    elif judge_trust == "medium":
        _demote("medium", "the evaluator (LLM judge) has limited reliability for this run")

    return level, reasons
