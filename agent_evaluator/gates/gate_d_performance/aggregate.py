"""
agent_evaluator.gates.gate_d_performance.aggregate
=====================================================
Gate D(Performance Contract) 집계 로직.

SPEC-000: agent_evaluator/core/trackers/monitor.py의 `_compute_harness_groups`
Gate D 블록에서 이관. 로직은 원본과 완전히 동일(위치 이관이 목적이며 SPEC-003 최적화는
별도 범위).

SLA 데이터(_sla_results/_sla_window_penalty/_sla_budget_penalty)는 Gate C(Reliability)
섹션에서도 breach_rate로 사용되는 공유 데이터다 — Gate C가 아직 이관되지 않았으므로
monitor.py가 계속 계산해 이 함수에 파라미터로 전달한다(SLAConfig 이중 귀속,
CLAUDE.md "SLAConfig dual contribution" 참조). Gate C 이관 시 이 공유 계산을
gates/shared_metrics.py 등으로 정리할 수 있다.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional

from agent_evaluator.gates.base import _g, _min_sample_warning


def compute(
    tasks: list,
    latency_tracker: Any,
    ttft_variability_config: Optional[Any],
    cost_predictability_config: Optional[Any],
    min_samples_default: int,
    sla_results: List[Dict[str, Any]],
    sla_window_penalty: float,
    sla_budget_penalty: float,
    sla_warning: Optional[str],
) -> Dict[str, Any]:
    """Gate D(Performance Contract) 그룹 딕셔너리를 계산한다.

    Args:
        tasks: TaskResult 리스트.
        latency_tracker: PerformanceMonitor.latency_tracker.
        ttft_variability_config: PerformanceMonitor._ttft_variability_config.
        cost_predictability_config: PerformanceMonitor._cost_predictability_config.
        min_samples_default: SPEC-002 최소 표본 가드 기본값.
        sla_results: Gate C 섹션에서 계산된 태스크별 SLA 평가 결과 목록(공유 데이터).
        sla_window_penalty: Gate C 섹션에서 계산된 breach_window 패널티(공유 데이터).
        sla_budget_penalty: Gate C 섹션에서 계산된 budget_usd 패널티(공유 데이터).
        sla_warning: Gate C 섹션에서 계산된 SLA 표본 부족 경고 문자열(공유 데이터, SPEC-002).

    Returns:
        {name, score, status, gate, details} — monitor.py의 groups["D"]와 동일한 형태.
    """
    _p95 = 0.0
    try:
        _lat_stats = latency_tracker.get_latency_stats()
        _p95 = float(_lat_stats.get("p95", 0.0))
    except Exception:
        pass

    # calibrated_score 우선 사용 (target_cost_per_completion 설정 시); 없으면 efficiency_ratio
    _eff_calibrated_vals: List[float] = []
    _eff_ratios_by_unit: Dict[str, List[float]] = {}  # unit → ratios (단위 혼재 방지)
    for _t in tasks:
        _eff = ((_t.extra or {}).get("efficiency") or {})
        if not _eff:
            continue
        if "calibrated_score" in _eff:
            _eff_calibrated_vals.append(float(_eff["calibrated_score"]))
        _er = _eff.get("efficiency_ratio")
        if _er is not None:  # cost_value=0(측정 불가) → None 제외
            _unit = str(_eff.get("cost_unit") or "tokens")
            _eff_ratios_by_unit.setdefault(_unit, []).append(float(_er))
    # 가장 많이 사용된 단위의 ratio만 평균 (단위 혼재 시 배율 오류 방지)
    _eff_ratios: List[float] = max(
        _eff_ratios_by_unit.values(), key=len, default=[]
    )
    _eff_cost_unit: str = (
        max(_eff_ratios_by_unit, key=lambda u: len(_eff_ratios_by_unit[u]))
        if _eff_ratios_by_unit else "tokens"
    )
    # calibrated_score가 있는 태스크가 절반 이상이면 calibrated_score 사용
    if len(_eff_calibrated_vals) >= max(1, len(_eff_ratios) // 2):
        avg_eff_calibrated: Optional[float] = (
            sum(_eff_calibrated_vals) / len(_eff_calibrated_vals)
        )
    else:
        avg_eff_calibrated = None
    avg_eff_ratio = sum(_eff_ratios) / len(_eff_ratios) if _eff_ratios else None

    # resource_budget → Group D (Phase 4)
    _rb_tasks = [t for t in tasks if (t.extra or {}).get("resource_budget") is not None]
    _avg_budget: Optional[float] = None
    if _rb_tasks:
        _rb_cfg = (_rb_tasks[-1].extra.get("resource_budget") or {}).get("_config", {})
        _use_rollover = bool(_rb_cfg.get("rollover", False))
        if _use_rollover and (_rb_cfg.get("max_tokens") or _rb_cfg.get("max_cost_usd") or _rb_cfg.get("max_execution_time_ms")):
            # rollover=True: 태스크별 개별 예산 대신 세션 누적 소비를 전체 한도와 비교
            _total_tokens_consumed = sum(
                float((t.extra["resource_budget"].get("_consumed") or {}).get("tokens", 0))
                for t in _rb_tasks
            )
            _total_cost_consumed = sum(
                float((t.extra["resource_budget"].get("_consumed") or {}).get("cost_usd", 0))
                for t in _rb_tasks
            )
            _total_time_consumed = sum(
                float((t.extra["resource_budget"].get("_consumed") or {}).get("time_ms", 0))
                for t in _rb_tasks
            )
            _n_tasks = max(len(_rb_tasks), 1)
            # D-F: 총 한도는 태스크별 Config 합산 (last-task × n_tasks 오류 수정)
            # 태스크마다 max_tokens 설정이 다를 수 있으므로 각 태스크의 Config 값을 개별 합산한다.
            _max_tok = sum(
                int((t.extra["resource_budget"].get("_config") or {}).get("max_tokens") or 0)
                for t in _rb_tasks
            )
            _max_cost = sum(
                float((t.extra["resource_budget"].get("_config") or {}).get("max_cost_usd") or 0.0)
                for t in _rb_tasks
            )
            _max_time = sum(
                float(
                    (t.extra["resource_budget"].get("_config") or {}).get("max_execution_time_ms") or 0.0
                )
                for t in _rb_tasks
            )
            _utils: List[float] = []
            if _max_tok > 0:
                _utils.append(_total_tokens_consumed / _max_tok)
            if _max_cost > 0:
                _utils.append(_total_cost_consumed / _max_cost)
            if _max_time > 0:
                _utils.append(_total_time_consumed / _max_time)
            _avg_budget = max(0.0, 1.0 - max(_utils)) if _utils else None
        else:
            _budget_scores = [
                t.extra["resource_budget"].get("budget_score")
                for t in _rb_tasks
            ]
            _budget_scores_f = [s for s in _budget_scores if s is not None]
            _avg_budget = sum(_budget_scores_f) / len(_budget_scores_f) if _budget_scores_f else None

    # TTFT variability — TTFTVariabilityConfig 파라미터 우선 사용
    _ttft_cfg = ttft_variability_config
    _ttft_min_samples: int = int(getattr(_ttft_cfg, "min_samples", 5)) if _ttft_cfg else 5
    _ttft_max_std: float = float(getattr(_ttft_cfg, "max_stddev_ms", 500.0)) if _ttft_cfg else 500.0
    _ttft_max_ratio: float = float(getattr(_ttft_cfg, "max_p95_p50_ratio", 3.0)) if _ttft_cfg else 3.0
    _ttft_remove_outliers: bool = bool(getattr(_ttft_cfg, "remove_outliers", True)) if _ttft_cfg else True

    _ttft_values: List[float] = []
    for _t in tasks:
        _ttft = None
        if _t.extra:
            _ttft = _t.extra.get("ttft_ms") or _t.extra.get("ttft")
        if _ttft is not None:
            try:
                _ttft_values.append(float(_ttft))
            except (TypeError, ValueError):
                pass

    # D-B: task.extra["ttft_ms"]에 데이터가 없으면 LatencyTracker._ttft_records를 폴백으로 사용.
    # @agent_eval(ttft_seconds=N) 파라미터 또는 스트리밍 EvalStep이 측정한 per-task TTFT는
    # LatencyTracker.track_ttft()에만 저장되고 task.extra에는 기록되지 않아
    # TTFTVariabilityConfig가 완전히 작동하지 않는 문제를 수정한다.
    # 폴백은 task.extra 데이터가 하나도 없을 때만 적용 (혼재 방지).
    if not _ttft_values:
        try:
            for _rec in latency_tracker._ttft_records:
                _ttft_s = _rec.get("ttft")
                if _ttft_s is not None:
                    _ttft_values.append(float(_ttft_s) * 1000.0)  # seconds → ms
        except Exception:
            pass

    _avg_ttft_variability: Optional[float] = None
    _ttft_stddev: Optional[float] = None
    _ttft_p50: Optional[float] = None
    _ttft_p95: Optional[float] = None
    if len(_ttft_values) >= _ttft_min_samples:
        _ttft_sorted = sorted(_ttft_values)
        if _ttft_remove_outliers and len(_ttft_sorted) >= 4:
            _q1 = _ttft_sorted[len(_ttft_sorted) // 4]
            _q3 = _ttft_sorted[3 * len(_ttft_sorted) // 4]
            _iqr = _q3 - _q1
            _ttft_clean = [
                v for v in _ttft_sorted
                if _q1 - 1.5 * _iqr <= v <= _q3 + 1.5 * _iqr
            ]
        else:
            _ttft_clean = _ttft_sorted

        if len(_ttft_clean) >= 2:
            _ttft_stddev = statistics.stdev(_ttft_clean)
            _ttft_sorted_clean = sorted(_ttft_clean)
            _n_clean = len(_ttft_sorted_clean)
            # p50: 짝수 N에서 두 중앙값 평균 (정확한 중앙값)
            _mid = _n_clean // 2
            _ttft_p50 = (
                (_ttft_sorted_clean[_mid - 1] + _ttft_sorted_clean[_mid]) / 2.0
                if _n_clean % 2 == 0
                else _ttft_sorted_clean[_mid]
            )
            # p95: nearest-rank (ceil 기반) — int(0.95 * N)은 N=20n일 때 max를 반환하는 off-by-one 있음
            _p95_idx = min(int(math.ceil(0.95 * _n_clean)) - 1, _n_clean - 1)
            _ttft_p95 = _ttft_sorted_clean[_p95_idx]
            _ttft_ratio = _ttft_p95 / max(_ttft_p50, 1.0)
            _std_score = max(0.0, 1.0 - _ttft_stddev / max(_ttft_max_std, 1.0))
            _ratio_score = min(1.0, max(0.0, 1.0 - (_ttft_ratio - 1.0) / max(_ttft_max_ratio - 1.0, 1.0)))
            _avg_ttft_variability = (_std_score + _ratio_score) / 2.0

    # cost_predictability — CostPredictabilityConfig 파라미터 우선 사용
    _cost_cfg = cost_predictability_config
    _cost_min_samples: int = int(getattr(_cost_cfg, "min_samples", 5)) if _cost_cfg else 5
    _cost_max_cv: float = float(getattr(_cost_cfg, "max_coefficient_of_variation", 0.3)) if _cost_cfg else 0.3
    _cost_metric: str = str(getattr(_cost_cfg, "cost_metric", "tokens")) if _cost_cfg else "tokens"
    _outlier_mult: float = float(getattr(_cost_cfg, "outlier_multiplier", 3.0)) if _cost_cfg else 3.0

    def _filter_outliers(values: List[float], multiplier: float) -> List[float]:
        """mean ± multiplier * std 범위 밖의 값을 제거한다."""
        if len(values) < 4:
            return values
        _mean = statistics.mean(values)
        _std = statistics.stdev(values)
        if _std == 0:
            return values
        return [v for v in values if abs(v - _mean) <= multiplier * _std]

    _avg_cost_predictability: Optional[float] = None
    if len(tasks) >= _cost_min_samples:
        _costs_by_type: Dict[str, List[float]] = {}
        for _ct in tasks:
            _ttype_d = str(_ct.task_type) if _ct.task_type else "unknown"
            # cost_metric: "tokens" | "usd" | "time_ms"
            if _cost_metric == "usd":
                _cv_cost = float((_ct.extra or {}).get("cost_usd") or 0.0)
            elif _cost_metric == "time_ms":
                _cv_cost = float((_ct.execution_time or 0.0) * 1000.0)
            else:  # "tokens" (default)
                _tu = _ct.tokens_used or 0
                if isinstance(_tu, dict):
                    # D-1: `_tu.get("total") or (input+output)` 패턴은 total=0(명시적 0토큰)을
                    # falsy로 처리해 input+output 합산으로 폴백 → CV 집계 왜곡.
                    # None-only 폴백으로 수정 (BUG-C23과 동일 패턴).
                    _raw_total_cv = _tu.get("total")
                    if _raw_total_cv is not None:
                        try:
                            _cv_cost = float(_raw_total_cv)
                        except (TypeError, ValueError):
                            _cv_cost = 0.0
                    else:
                        _cv_cost = float(
                            _tu.get("input", 0) + _tu.get("output", 0)
                        )
                else:
                    try:
                        _cv_cost = float(_tu)
                    except (TypeError, ValueError):
                        _cv_cost = 0.0
            # 미측정(None→0.0) 태스크를 집계에 포함하면 CV가 허위 팽창하므로 제외
            if _cv_cost <= 0.0:
                continue
            _costs_by_type.setdefault(_ttype_d, []).append(_cv_cost)
        _cv_scores_d: List[float] = []
        for _costs_list in _costs_by_type.values():
            # outlier_multiplier로 이상치 제거 후 CV 계산
            _filtered = _filter_outliers(_costs_list, _outlier_mult)
            if len(_filtered) >= 2:
                _cv_mean = statistics.mean(_filtered)
                if _cv_mean > 0:
                    _cv_std = statistics.stdev(_filtered)
                    _cv_val = _cv_std / _cv_mean
                    # Config의 max_cv를 임계값으로 사용: CV가 max_cv 이하면 1.0
                    _cv_score_d = max(0.0, 1.0 - _cv_val / max(_cost_max_cv, 0.01))
                    _cv_scores_d.append(_cv_score_d)
        if _cv_scores_d:
            _avg_cost_predictability = sum(_cv_scores_d) / len(_cv_scores_d)

    # ── D 그룹: insufficient_data 경고 수집 ──
    _d_insufficient: List[str] = []
    if _ttft_values and len(_ttft_values) < _ttft_min_samples:
        _d_insufficient.append(
            f"ttft_variability: {len(_ttft_values)} samples < min_samples={_ttft_min_samples}"
        )
    # 아웃라이어 제거 후 2개 미만 남을 때 — _avg_ttft_variability=None으로 조용히 제외되므로 경고 추가
    elif (
        _ttft_values
        and len(_ttft_values) >= _ttft_min_samples
        and _avg_ttft_variability is None
    ):
        _d_insufficient.append(
            f"ttft_variability: outlier removal reduced {len(_ttft_values)} samples to < 2 "
            f"(remove_outliers={_ttft_remove_outliers}) — score excluded from Gate D"
        )
    if len(tasks) < _cost_min_samples:
        _d_insufficient.append(
            f"cost_predictability: {len(tasks)} tasks < min_samples={_cost_min_samples}"
        )
    # SPEC-002 REQ-3: Gate C와 동일한 sla_warning을 재사용 — 두 Gate가 동일 문자열을 공유
    if sla_warning:
        _d_insufficient.append(sla_warning)

    _perf_vals: List[float] = []
    if _p95 > 0:
        # SLAConfig.p95_ms 전체 평균을 임계값으로 사용 (태스크별 설정 혼재 시 last-task-wins 방지)
        # 없으면 기본 10s 기준
        _p95_threshold_s = 10.0
        if sla_results:
            _p95_ms_values = [
                float(s["_config"]["p95_ms"])
                for s in sla_results
                if s.get("_config") and s["_config"].get("p95_ms") is not None
            ]
            if _p95_ms_values:
                _p95_threshold_s = sum(_p95_ms_values) / len(_p95_ms_values) / 1000.0
        _perf_vals.append(max(0.0, 1.0 - min(1.0, _p95 / max(_p95_threshold_s, 1.0))))
    if avg_eff_calibrated is not None:
        # target_cost_per_completion 기반 calibrated_score 사용 (0-1 직접 사용)
        _perf_vals.append(avg_eff_calibrated)
    elif avg_eff_ratio is not None:
        # Normalize: token/time_ms ratio ~0.001 maps to 1.0.
        # USD ratio is ~100-1000; $0.01/completion = threshold (ratio=100 → 1.0).
        if _eff_cost_unit == "usd":
            _norm_eff = min(1.0, avg_eff_ratio * 0.01)
        else:
            _norm_eff = min(1.0, avg_eff_ratio * 1000.0)
        _perf_vals.append(_norm_eff)
    if _avg_budget is not None:
        _perf_vals.append(_avg_budget)
    if _avg_ttft_variability is not None:
        _perf_vals.append(_avg_ttft_variability)
    if _avg_cost_predictability is not None:
        _perf_vals.append(_avg_cost_predictability)
    _perf_score: Optional[float] = sum(_perf_vals) / len(_perf_vals) if _perf_vals else None
    # SLA breach_window/budget_usd 패널티 적용 (데이터 있을 때만)
    if _perf_score is not None:
        _perf_score = max(0.0, _perf_score - sla_window_penalty - sla_budget_penalty)

    _d_s = round(float(_perf_score), 4) if _perf_score is not None else None

    return _g(_d_s, "Performance Contract", {
        "p95_latency_s": round(_p95, 4),
        # calibrated_score 우선 사용 시 두 값 모두 노출 (역추적 가능성 확보)
        "avg_efficiency_calibrated_score": round(avg_eff_calibrated, 4) if avg_eff_calibrated is not None else None,
        "avg_efficiency_ratio": round(avg_eff_ratio, 8) if avg_eff_ratio is not None else None,
        "avg_budget_score": round(_avg_budget, 4) if _avg_budget is not None else None,
        "ttft_variability_score": round(_avg_ttft_variability, 4) if _avg_ttft_variability is not None else None,
        "ttft_stddev_ms": round(_ttft_stddev, 4) if _ttft_stddev is not None else None,
        "ttft_p50_ms": round(_ttft_p50, 4) if _ttft_p50 is not None else None,
        "ttft_p95_ms": round(_ttft_p95, 4) if _ttft_p95 is not None else None,
        "avg_cost_predictability": round(_avg_cost_predictability, 4) if _avg_cost_predictability is not None else None,
        "insufficient_data_warnings": _d_insufficient if _d_insufficient else None,
    })
