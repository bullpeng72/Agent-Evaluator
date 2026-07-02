"""
agent_evaluator.gates.gate_c_reliability.aggregate
=====================================================
Gate C(Reliability) 집계 로직.

SPEC-000: agent_evaluator/core/trackers/monitor.py의 `_compute_harness_groups` 내부
Gate C 블록에서 그대로 이관(로직 변경 없음). monitor.py는 이 모듈의 `compute()`와
`compute_sla_shared_data()`를 호출해 위임한다.

이 모듈은 두 개의 교차 Gate 공유 데이터의 원천이다:

- **SLA 공유 데이터(Gate D가 소비)**: `compute_sla_shared_data(tasks)`는 tasks만으로
  계산 가능한 순수 함수다. monitor.py가 한 번 호출해 그 결과를 `compute()`(Gate C 자신의
  breach_rate 기여분 계산용)와 `gate_d_aggregate.compute()`(window/budget penalty용)
  양쪽에 전달한다.
- **hallucination_rate/avg_llm_faithfulness(Gate G가 소비, 미이관)**: `compute()`는
  `(group_dict, shared_raw)` 튜플을 반환한다. `group_dict`는 다른 Gate와 동일한 `_g()`
  형식(JSON 리포트에 노출되는 형태 — 이관 전과 완전히 동일)이고, `shared_raw`는 반올림되지
  않은 원본값(`hall_rate`, `avg_llm_faithfulness`)을 담아 Gate G 섹션이 재사용할 수 있게
  한다(정밀도 손실 방지 — 이중 반올림으로 인한 byte-diff 불일치를 피하기 위해 raw 값을
  별도로 넘긴다).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agent_evaluator.gates.base import _g, _min_sample_warning


def compute_sla_shared_data(tasks: List[Any]) -> Dict[str, Any]:
    """SLA 관련 공유 데이터 계산 (Gate C·D 양쪽에서 소비).

    Args:
        tasks: 기록된 TaskResult 리스트.

    Returns:
        {sla_results, sla_breach_count, sla_breach_rate, sla_warning,
         sla_window_penalty, sla_budget_penalty}
    """
    _sla_results = [
        t.extra["sla"]
        for t in tasks
        if (t.extra or {}).get("sla") is not None
    ]
    _sla_breach_count = sum(1 for s in _sla_results if not s.get("sla_met", True))
    _sla_breach_rate = _sla_breach_count / len(_sla_results) if _sla_results else None

    # SPEC-002: SLA 표본 부족 경고는 Gate C·D 양쪽에서 공유되는 원천 데이터이므로 한 번만 계산한다
    # (REQ-3) — Gate D의 min_samples=5 계약값을 그대로 재사용, 이 기본값 자체는 변경하지 않는다.
    _sla_warning: Optional[str] = _min_sample_warning("sla", len(_sla_results), 5)

    # breach_window/warn_threshold/fail_threshold: 최근 window 내 연속 breach 감지
    _sla_window_penalty: float = 0.0
    _sla_cfg_summary: Dict[str, Any] = {}
    if _sla_results:
        _sla_cfg_summary = next(
            (s.get("_config") for s in reversed(_sla_results) if s.get("_config")), {}
        )
        _breach_window = int(_sla_cfg_summary.get("breach_window", 10))
        _warn_thr = int(_sla_cfg_summary.get("warn_threshold", 2))
        _fail_thr = int(_sla_cfg_summary.get("fail_threshold", 5))
        _recent = _sla_results[-_breach_window:]
        _recent_breach_count = sum(1 for s in _recent if not s.get("sla_met", True))
        if _recent_breach_count >= _fail_thr:
            _sla_window_penalty = 0.3   # Gate D 점수 30% 감점
        elif _recent_breach_count >= _warn_thr:
            _sla_window_penalty = 0.1   # 10% 감점

    # budget_usd: 세션 전체 누적 비용 예산 초과 감지
    _sla_budget_penalty: float = 0.0
    if _sla_results:
        _budget_usd = _sla_cfg_summary.get("budget_usd")
        if _budget_usd is not None:
            _total_session_cost = sum(
                float((t.extra.get("sla") or {}).get("cost_usd") or 0.0)
                for t in tasks
                if (t.extra or {}).get("sla") is not None
            )
            if _total_session_cost > float(_budget_usd):
                _overage = _total_session_cost / max(float(_budget_usd), 1e-9) - 1.0
                _sla_budget_penalty = min(0.3, _overage * 0.1)

    return {
        "sla_results": _sla_results,
        "sla_breach_count": _sla_breach_count,
        "sla_breach_rate": _sla_breach_rate,
        "sla_warning": _sla_warning,
        "sla_window_penalty": _sla_window_penalty,
        "sla_budget_penalty": _sla_budget_penalty,
    }


def compute(
    tasks: List[Any],
    hallucination_detector: Any,
    tcr_tracker: Any,
    gate_c_tcr_weight: float,
    min_samples_default: int,
    sla_shared: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Gate C(신뢰성) 점수를 집계한다.

    Args:
        tasks: 기록된 TaskResult 리스트.
        hallucination_detector: `HallucinationDetector` 인스턴스.
        tcr_tracker: `TaskCompletionTracker` 인스턴스.
        gate_c_tcr_weight: TCR 컴포넌트 가중치.
        min_samples_default: 표본 부족 경고 최소 임계치.
        sla_shared: `compute_sla_shared_data(tasks)`의 반환값.

    Returns:
        (group_dict, shared_raw) 튜플.
        - group_dict: gates/base.py의 `_g()` 형식 Gate 결과 dict (JSON 리포트에 그대로 노출).
        - shared_raw: {"hall_rate": Optional[float], "avg_llm_faithfulness": Optional[float]}
          — Gate G(미이관)가 반올림 없이 재사용할 원본값.
    """
    tcr_pct = 0.0
    try:
        _tcr_stats = tcr_tracker.calculate_tcr()
        tcr_pct = float(_tcr_stats.get("tcr", 0.0))
    except Exception:
        pass

    # hall_rate: Gate C(신뢰성)와 Gate G(관측성) 양쪽에서 사용 — 여기서 한 번만 계산 (0-1 스케일)
    # 실제 감지 건수가 있을 때만 설정 — 감지 자체가 없으면 None 유지 (점수에 미기여)
    hall_rate = None
    try:
        if hallucination_detector._detections:
            _hall_data = hallucination_detector.get_hallucination_rate()
            _hall_overall = _hall_data.get("overall_rate")  # 0-100 percentage
            if _hall_overall is not None:
                hall_rate = float(_hall_overall) / 100.0
    except Exception:
        pass

    _rel_vals: List[float] = [tcr_pct / 100.0]

    _sla_results = sla_shared["sla_results"]
    _sla_breach_count = sla_shared["sla_breach_count"]
    _sla_breach_rate = sla_shared["sla_breach_rate"]
    _sla_warning = sla_shared["sla_warning"]
    if _sla_breach_rate is not None:
        _rel_vals.append(max(0.0, 1.0 - _sla_breach_rate))

    # reproducibility → Group C
    # C-3: run_count < 2 (skip_side_effects=True 또는 runs ≤ 1 오설정)이면
    # compute_reproducibility_score는 score=1.0을 반환하지만 실제 재현성 측정이 이루어지지 않았음.
    # 이 값을 Gate C에 포함하면 측정되지 않은 데이터가 점수를 인플레이션시키므로 제외한다.
    _repro_scores = [
        float(t.extra.get("reproducibility", {}).get("score"))
        for t in tasks
        if (t.extra or {}).get("reproducibility") is not None
        and (t.extra or {}).get("reproducibility", {}).get("score") is not None
        and int((t.extra or {}).get("reproducibility", {}).get("run_count", 2)) >= 2
    ]
    avg_reproducibility: Optional[float] = sum(_repro_scores) / len(_repro_scores) if _repro_scores else None
    if avg_reproducibility is not None:
        _rel_vals.append(avg_reproducibility)

    # fault_tolerance → Group C
    # grade="none" 제외: tool_calls가 없어 평가 자체가 불가한 경우 집계에서 제외
    # recovery_quality_score 우선 사용 (grade 세분화 반영: wrong_fallback=0.2 등)
    # 없으면 raw recovery_rate 폴백
    _ft_scores = []
    for _ft_t in tasks:
        _ft = (_ft_t.extra or {}).get("fault_tolerance")
        # "none": tool_calls 없어 평가 불가 → 제외
        # "untracked": check_fallback_attempts=False로 의도적 추적 비활성 → 제외
        if _ft is None or _ft.get("grade") in ("none", "untracked"):
            continue
        _ft_sc = (
            _ft["recovery_quality_score"]
            if "recovery_quality_score" in _ft
            else _ft.get("recovery_rate", 1.0)
        )
        _ft_scores.append(float(_ft_sc))
    avg_ft: Optional[float] = sum(_ft_scores) / len(_ft_scores) if _ft_scores else None
    if avg_ft is not None:
        _rel_vals.append(avg_ft)

    # graceful_degradation → Group C (Phase 4)
    _deg_scores = [
        float(t.extra.get("graceful_degradation", {}).get("degradation_score"))
        for t in tasks
        if (t.extra or {}).get("graceful_degradation") is not None
        and (t.extra or {}).get("graceful_degradation", {}).get("degradation_score") is not None
    ]
    _avg_degradation: Optional[float] = sum(_deg_scores) / len(_deg_scores) if _deg_scores else None
    if _avg_degradation is not None:
        _rel_vals.append(_avg_degradation)

    # retry_consistency → Group C (Phase 5)
    # group_by_task_prefix=True: task_id 접두사 기준으로 그룹화 후 그룹별 평균 산출
    _rc_tasks_with_score = [
        t for t in tasks
        if (t.extra or {}).get("retry_consistency") is not None
    ]
    _avg_retry_consistency: Optional[float] = None
    if _rc_tasks_with_score:
        _use_prefix = any(
            (t.extra.get("retry_consistency") or {}).get("_config", {}).get("group_by_task_prefix", True)
            for t in _rc_tasks_with_score
        )
        if _use_prefix:
            # task_id를 '_' 기준으로 접두사별 그룹화 후 그룹별 평균 산출
            # 정렬 후 첫→마지막 accuracy delta로 cross-task 개선/저하 보너스/페널티 적용
            _rc_by_prefix: Dict[str, List] = {}
            for _t in _rc_tasks_with_score:
                _tid = str(getattr(_t, "task_id", "") or "")
                _parts = _tid.rsplit("_", 1)
                _prefix = _parts[0] if len(_parts) > 1 else _tid
                _sc = _t.extra["retry_consistency"].get("consistency_score")
                if _sc is not None:
                    _rc_by_prefix.setdefault(_prefix, []).append({
                        "score": float(_sc),
                        "task_id": _tid,
                        "accuracy": float(getattr(_t, "accuracy_score", 0.0) or 0.0),
                        "config": (_t.extra["retry_consistency"].get("_config") or {}),
                    })
            _group_avgs = []
            for _rc_entries in _rc_by_prefix.values():
                if not _rc_entries:
                    continue
                _rc_entries.sort(key=lambda e: e["task_id"])
                _rc_avg = sum(e["score"] for e in _rc_entries) / len(_rc_entries)
                if len(_rc_entries) >= 2:
                    _rc_cfg = _rc_entries[0]["config"]
                    _imp_thr = float(_rc_cfg.get("improvement_threshold", 0.1))
                    _penalize = bool(_rc_cfg.get("penalize_degradation", True))
                    _acc_delta = _rc_entries[-1]["accuracy"] - _rc_entries[0]["accuracy"]
                    if _acc_delta >= _imp_thr:
                        _rc_avg = min(1.0, _rc_avg + 0.1)
                    elif _acc_delta < -_imp_thr and _penalize:
                        _rc_avg = max(0.0, _rc_avg - 0.1)
                _group_avgs.append(_rc_avg)
            _avg_retry_consistency = sum(_group_avgs) / len(_group_avgs) if _group_avgs else None
        else:
            _rc_scores = [
                t.extra["retry_consistency"].get("consistency_score")
                for t in _rc_tasks_with_score
            ]
            _rc_scores_f = [s for s in _rc_scores if s is not None]
            _avg_retry_consistency = sum(_rc_scores_f) / len(_rc_scores_f) if _rc_scores_f else None
    if _avg_retry_consistency is not None:
        _rel_vals.append(_avg_retry_consistency)

    # idempotency → Group C (Phase 6)
    _idem_scores = [
        float(t.extra.get("idempotency", {}).get("idempotency_score"))
        for t in tasks
        if t.extra and t.extra.get("idempotency")
        and t.extra.get("idempotency", {}).get("idempotency_score") is not None
    ]
    _avg_idempotency: Optional[float] = (
        sum(_idem_scores) / len(_idem_scores) if _idem_scores else None
    )
    if _avg_idempotency is not None:
        _rel_vals.append(_avg_idempotency)

    # 출력 사실 충실성 → Gate C (우선순위 대체: LLM Judge > HallucinationDetector)
    # LLM Judge faithfulness(0–5)가 있으면 /5 정규화 후 사용; 없으면 1−hall_rate 폴백
    _faith_scores = [
        float(t.llm_judge["scores"]["faithfulness"])
        for t in tasks
        if getattr(t, "llm_judge", None)
        and not (t.llm_judge or {}).get("skipped")
        and isinstance((t.llm_judge or {}).get("scores", {}).get("faithfulness"), (int, float))
    ]
    _avg_llm_faithfulness: Optional[float] = (
        sum(_faith_scores) / len(_faith_scores) if _faith_scores else None
    )
    if _avg_llm_faithfulness is not None:
        _rel_vals.append(max(0.0, min(1.0, _avg_llm_faithfulness / 5.0)))
    elif hall_rate is not None:
        _rel_vals.append(max(0.0, 1.0 - float(hall_rate)))

    # ── C 그룹: insufficient_data 경고 수집 (SPEC-002) ──
    # hall_rate 폴백 분기는 "측정값 없음 시 대체 신호"이므로 표본 개념이 없어 제외한다.
    _c_insufficient: List[str] = []
    if _sla_warning:
        _c_insufficient.append(_sla_warning)
    for _name, _cnt in (
        ("reproducibility", len(_repro_scores)),
        ("fault_tolerance", len(_ft_scores)),
        ("graceful_degradation", len(_deg_scores)),
        ("retry_consistency", len(_rc_tasks_with_score)),
        ("idempotency", len(_idem_scores)),
    ):
        _w = _min_sample_warning(_name, _cnt, min_samples_default)
        if _w:
            _c_insufficient.append(_w)
    if _avg_llm_faithfulness is not None:
        _w = _min_sample_warning("llm_faithfulness", len(_faith_scores), min_samples_default)
        if _w:
            _c_insufficient.append(_w)

    # Gate C: TCR(index 0)와 Config 지표를 gate_c_tcr_weight로 가중 평균
    # _rel_vals는 TCR로 항상 초기화되므로 항상 non-empty.
    _tcr_c = _rel_vals[0]
    _config_c_vals = _rel_vals[1:]
    if _config_c_vals:
        _config_c_avg = sum(_config_c_vals) / len(_config_c_vals)
        _rel_score = (
            gate_c_tcr_weight * _tcr_c
            + (1.0 - gate_c_tcr_weight) * _config_c_avg
        )
    else:
        _rel_score = float(_tcr_c)
    # C-17: defense-in-depth — 이전 버전 저장 데이터 또는 예상치 못한 경로에서
    # _rel_vals 원소가 1.0을 초과할 경우 최종 집계값도 1.0을 초과할 수 있음.
    _rel_score = max(0.0, min(1.0, _rel_score))

    _c_s = round(float(_rel_score), 4)

    group = _g(_c_s, "Reliability", {
        "tcr_pct": round(tcr_pct, 2),
        "gate_c_tcr_weight": gate_c_tcr_weight,
        "sla_breach_rate": round(_sla_breach_rate, 4) if _sla_breach_rate is not None else None,
        "sla_breach_count": _sla_breach_count if _sla_results else None,
        "avg_reproducibility": round(avg_reproducibility, 4) if avg_reproducibility is not None else None,
        "avg_fault_tolerance": round(avg_ft, 4) if avg_ft is not None else None,
        "avg_degradation": round(_avg_degradation, 4) if _avg_degradation is not None else None,
        "avg_retry_consistency": round(_avg_retry_consistency, 4) if _avg_retry_consistency is not None else None,
        "avg_idempotency": round(_avg_idempotency, 4) if _avg_idempotency is not None else None,
        "avg_llm_faithfulness": round(_avg_llm_faithfulness, 4) if _avg_llm_faithfulness is not None else None,
        "hallucination_rate": round(hall_rate, 4) if hall_rate is not None else None,
        "insufficient_data_warnings": _c_insufficient if _c_insufficient else None,
    })

    shared_raw = {"hall_rate": hall_rate, "avg_llm_faithfulness": _avg_llm_faithfulness}
    return group, shared_raw
