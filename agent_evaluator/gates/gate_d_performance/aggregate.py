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
from typing import Any

from agent_evaluator.gates.base import _g


def compute(
    tasks: list,
    latency_tracker: Any,
    ttft_variability_config: Any | None,
    cost_predictability_config: Any | None,
    min_samples_default: int,
    sla_results: list[dict[str, Any]],
    sla_window_penalty: float,
    sla_budget_penalty: float,
    sla_warning: str | None,
    shared_running: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        shared_running: (SPEC-018 Phase 7) retention_mode="windowed"일 때
            ``GateDSharedAgg.snapshot()``이 제공하는 집계값. efficiency/resource_budget는
            전체 이력과 항등인 정확한 값이다. ttft_variability/cost_predictability는
            **의도적으로 승인된 근사치**다 — 원시값을 O(1) 메모리로 정확히 재현할 수
            없어, `window_size`와 독립적인 별도의 최근 2,000개 슬라이딩 샘플
            (`GateDSharedAgg._RESERVOIR_SIZE`)에서 계산한다. p95 latency는 이 파라미터와
            무관하게 항상 `latency_tracker`(retention_mode와 무관하게 이미 무제한
            증식하는 트래커)에서 온다 — 애초부터 전체 이력 반영, 수정 불필요.
            ``None``(기본값, "full" 모드)이면 기존과 100% 동일하게 `tasks`에서 매번
            재계산한다.

    Returns:
        {name, score, status, gate, details} — monitor.py의 groups["D"]와 동일한 형태.
    """
    _p95 = 0.0
    try:
        _lat_stats = latency_tracker.get_latency_stats()
        _p95 = float(_lat_stats.get("p95", 0.0))
    except Exception:
        pass

    if shared_running is not None:
        # efficiency — 정확 (SPEC-018 Phase 7): 단순 평균/카운트만 필요해 항등 재현 가능.
        _eff_cost_unit: str = shared_running["eff_cost_unit"]
        _eff_ratio_n = shared_running["eff_ratio_count"]
        avg_eff_ratio = shared_running["eff_ratio_avg"]
        _eff_calibrated_n = shared_running["eff_calibrated_count"]
        if _eff_calibrated_n >= max(1, _eff_ratio_n // 2):
            avg_eff_calibrated: float | None = shared_running["eff_calibrated_avg"]
        else:
            avg_eff_calibrated = None
        # fallback_reference_cost_per_completion: windowed 모드는 이 값을 러닝 집계로
        # 전달받지 않는다(GateDSharedAgg 확장 범위 밖) — "full" 모드와 달리 항상 cost_unit별
        # 기존 하드코딩 기본값(1000.0/0.01)을 쓴다. calibrated_score 없는 태스크의 fallback
        # 정규화이므로 windowed에서만 근사가 하나 더 느는 것이지 회귀는 아니다.
        _eff_fallback_ref: float | None = None

        # resource_budget — 정확 (SPEC-018 Phase 7): 누적합/최근 config 덮어쓰기로 항등 재현.
        _rb_n = shared_running["rb_n"]
        _avg_budget: float | None = None
        if _rb_n > 0:
            _rb_cfg = shared_running["rb_config"]
            _use_rollover = bool(_rb_cfg.get("rollover", False))
            if _use_rollover and (
                _rb_cfg.get("max_tokens") or _rb_cfg.get("max_cost_usd")
                or _rb_cfg.get("max_execution_time_ms")
            ):
                _total_tokens_consumed = shared_running["rb_tokens_consumed"]
                _total_cost_consumed = shared_running["rb_cost_consumed"]
                _total_time_consumed = shared_running["rb_time_consumed"]
                _max_tok = shared_running["rb_max_tokens"]
                _max_cost = shared_running["rb_max_cost"]
                _max_time = shared_running["rb_max_time"]
                _utils: list[float] = []
                if _max_tok > 0:
                    _utils.append(_total_tokens_consumed / _max_tok)
                if _max_cost > 0:
                    _utils.append(_total_cost_consumed / _max_cost)
                if _max_time > 0:
                    _utils.append(_total_time_consumed / _max_time)
                _avg_budget = max(0.0, 1.0 - max(_utils)) if _utils else None
            else:
                _avg_budget = shared_running["rb_budget_score_avg"]
    else:
        # calibrated_score 우선 사용 (target_cost_per_completion 설정 시); 없으면 efficiency_ratio
        _eff_calibrated_vals: list[float] = []
        _eff_ratios_by_unit: dict[str, list[float]] = {}  # unit → ratios (단위 혼재 방지)
        # unit별 fallback_reference_cost_per_completion — 마지막으로 관측된 값을 사용
        # (다른 Gate D Config 값들의 "마지막 태스크 설정 우선" 관례와 동일, resource_budget 참조)
        _fallback_ref_by_unit: dict[str, float] = {}
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
                _ref = (_eff.get("_config") or {}).get("fallback_reference_cost_per_completion")
                if _ref is not None:
                    _fallback_ref_by_unit[_unit] = float(_ref)
        # 가장 많이 사용된 단위의 ratio만 평균 (단위 혼재 시 배율 오류 방지)
        _eff_ratios: list[float] = max(
            _eff_ratios_by_unit.values(), key=len, default=[]
        )
        _eff_cost_unit = (
            max(_eff_ratios_by_unit, key=lambda u: len(_eff_ratios_by_unit[u]))
            if _eff_ratios_by_unit else "tokens"
        )
        _eff_fallback_ref: float | None = _fallback_ref_by_unit.get(_eff_cost_unit)
        # calibrated_score가 있는 태스크가 절반 이상이면 calibrated_score 사용
        if len(_eff_calibrated_vals) >= max(1, len(_eff_ratios) // 2):
            avg_eff_calibrated = (
                sum(_eff_calibrated_vals) / len(_eff_calibrated_vals)
            )
        else:
            avg_eff_calibrated = None
        avg_eff_ratio = sum(_eff_ratios) / len(_eff_ratios) if _eff_ratios else None

        # resource_budget → Group D (Phase 4)
        _rb_tasks = [t for t in tasks if (t.extra or {}).get("resource_budget") is not None]
        _avg_budget = None
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
                _utils = []
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

    if shared_running is not None:
        # ttft_variability — 근사 (SPEC-018 Phase 7): window_size와 독립적인 최근
        # GateDSharedAgg._RESERVOIR_SIZE(기본 2000)개 슬라이딩 샘플에서 계산한다.
        # 전체 이력이 이 샘플 크기를 넘으면 가장 오래된 원시값부터 밀려나 있을 수 있다
        # (승인된 의도적 근사 — 아래 sorted/IQR/stddev/percentile 계산 자체는 정확하다,
        # 다만 "무엇을 대상으로" 계산하는지가 전체 이력이 아닌 샘플이라는 차이다).
        _ttft_values: list[float] = list(shared_running["ttft_values"])
    else:
        _ttft_values = []
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
    # 폴백은 task.extra 데이터가 하나도 없을 때만 적용 (혼재 방지). latency_tracker 자체는
    # retention_mode와 무관하게 이미 무제한 증식하므로 이 폴백 경로는 shared_running
    # 유무와 상관없이 항상 전체 이력을 반영한다(수정 불필요).
    if not _ttft_values:
        try:
            for _rec in latency_tracker._ttft_records:
                _ttft_s = _rec.get("ttft")
                if _ttft_s is not None:
                    _ttft_values.append(float(_ttft_s) * 1000.0)  # seconds → ms
        except Exception:
            pass

    _avg_ttft_variability: float | None = None
    _ttft_stddev: float | None = None
    _ttft_p50: float | None = None
    _ttft_p95: float | None = None
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

    def _filter_outliers(values: list[float], multiplier: float) -> list[float]:
        """mean ± multiplier * std 범위 밖의 값을 제거한다."""
        if len(values) < 4:
            return values
        _mean = statistics.mean(values)
        _std = statistics.stdev(values)
        if _std == 0:
            return values
        return [v for v in values if abs(v - _mean) <= multiplier * _std]

    _avg_cost_predictability: float | None = None
    _cost_gate_n = shared_running["total_n"] if shared_running is not None else len(tasks)
    if _cost_gate_n >= _cost_min_samples:
        if shared_running is not None:
            # cost_predictability — 근사 (SPEC-018 Phase 7): ttft_variability와 동일한
            # 이유로 window_size와 독립적인 최근 샘플(task_type별 별도 링버퍼)에서 계산한다.
            _costs_by_type: dict[str, list[float]] = dict(
                shared_running["cost_by_metric"].get(_cost_metric, {})
            )
        else:
            _costs_by_type = {}
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
        _cv_scores_d: list[float] = []
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
    _d_insufficient: list[str] = []
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
    if _cost_gate_n < _cost_min_samples:
        _d_insufficient.append(
            f"cost_predictability: {_cost_gate_n} tasks < min_samples={_cost_min_samples}"
        )
    # SPEC-002 REQ-3: Gate C와 동일한 sla_warning을 재사용 — 두 Gate가 동일 문자열을 공유
    if sla_warning:
        _d_insufficient.append(sla_warning)

    _perf_vals: list[float] = []
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
    _eff_ratio_reference_used: float | None = None
    if avg_eff_calibrated is not None:
        # target_cost_per_completion 기반 calibrated_score 사용 (0-1 직접 사용)
        _perf_vals.append(avg_eff_calibrated)
    elif avg_eff_ratio is not None:
        # Normalize: efficiency_ratio(completion/cost) * reference_cost_per_completion == 1.0
        # when actual cost == reference cost. EfficiencyConfig.fallback_reference_cost_per_completion가
        # 설정돼 있으면 그 값을, 없으면 cost_unit별 기존 기본값(tokens/time_ms=1000.0, usd=0.01)을 쓴다
        # — 팀마다 다른 비용 구조에서 이 하드코딩 기준이 무의미한 점수를 만드는 문제(검사 5-D)를 해소.
        _eff_ratio_reference_used = (
            _eff_fallback_ref if _eff_fallback_ref is not None
            else (0.01 if _eff_cost_unit == "usd" else 1000.0)
        )
        _norm_eff = min(1.0, avg_eff_ratio * _eff_ratio_reference_used)
        _perf_vals.append(_norm_eff)
    if _avg_budget is not None:
        _perf_vals.append(_avg_budget)
    if _avg_ttft_variability is not None:
        _perf_vals.append(_avg_ttft_variability)
    if _avg_cost_predictability is not None:
        _perf_vals.append(_avg_cost_predictability)
    _perf_score_pre_penalty: float | None = sum(_perf_vals) / len(_perf_vals) if _perf_vals else None
    _perf_score = _perf_score_pre_penalty
    # SLA breach_window/budget_usd 패널티 적용 (데이터 있을 때만) — 이 패널티는 Gate C
    # (compute_sla_shared_data)가 계산한 값을 그대로 전달받은 것이므로, details에 노출하지
    # 않으면 avg_efficiency/avg_budget/ttft/cost_predictability를 아무리 평균해도 최종 점수와
    # 안 맞는 "역추적 불가" 상태가 된다. 두 값을 details에 그대로 기록해 역추적 가능하게 한다.
    if _perf_score is not None:
        _perf_score = max(0.0, _perf_score - sla_window_penalty - sla_budget_penalty)

    _d_s = round(float(_perf_score), 4) if _perf_score is not None else None

    return _g(_d_s, "Performance Contract", {
        "p95_latency_s": round(_p95, 4),
        # calibrated_score 우선 사용 시 두 값 모두 노출 (역추적 가능성 확보)
        "avg_efficiency_calibrated_score": round(avg_eff_calibrated, 4) if avg_eff_calibrated is not None else None,
        "avg_efficiency_ratio": round(avg_eff_ratio, 8) if avg_eff_ratio is not None else None,
        # avg_efficiency_calibrated_score가 None일 때만(폴백 정규화 경로) 실제 사용된 기준 비용 노출.
        # EfficiencyConfig(fallback_reference_cost_per_completion=...) 미설정 시 cost_unit별 레거시
        # 기본값(tokens/time_ms=1000.0, usd=0.01)이 그대로 사용됐다는 뜻 — 역추적/감사용.
        "efficiency_ratio_reference_cost": _eff_ratio_reference_used,
        "avg_budget_score": round(_avg_budget, 4) if _avg_budget is not None else None,
        "ttft_variability_score": round(_avg_ttft_variability, 4) if _avg_ttft_variability is not None else None,
        "ttft_stddev_ms": round(_ttft_stddev, 4) if _ttft_stddev is not None else None,
        "ttft_p50_ms": round(_ttft_p50, 4) if _ttft_p50 is not None else None,
        "ttft_p95_ms": round(_ttft_p95, 4) if _ttft_p95 is not None else None,
        "avg_cost_predictability": round(_avg_cost_predictability, 4) if _avg_cost_predictability is not None else None,
        # Gate C(compute_sla_shared_data)가 계산해 이 함수로 전달한 SLA 패널티 —
        # 최종 score = round(perf_score_pre_sla_penalty - sla_window_penalty - sla_budget_penalty, 4)
        # 역추적용. 0.0이어도(패널티 미발동) 명시적으로 노출해 "SLA 데이터 자체가 없음"과 구분한다.
        "perf_score_pre_sla_penalty": round(_perf_score_pre_penalty, 4) if _perf_score_pre_penalty is not None else None,
        "sla_window_penalty": round(sla_window_penalty, 4),
        "sla_budget_penalty": round(sla_budget_penalty, 4),
        "insufficient_data_warnings": _d_insufficient if _d_insufficient else None,
    })
