"""
agent_evaluator.gates.gate_b_behavioral.aggregate
====================================================
Gate B(Behavioral Integrity) 집계 로직.

SPEC-000: agent_evaluator/core/trackers/monitor.py의 `_compute_harness_groups` 내부
Gate B 블록에서 그대로 이관(로직 변경 없음). monitor.py는 이 모듈의 `compute()`를
호출해 위임한다.

Gate A(Goal Achievement)의 avg_goal_alignment/avg_plan_coherence는 진단용으로만
재참조한다(Gate B 스코어링에는 미포함) — 호출자(monitor.py)가 `_a_group["details"]`에서
이미 계산된 값을 파라미터로 전달한다 (SLA가 Gate C→D로 전달되는 것과 동일한 공유 패턴).
"""
from __future__ import annotations

from typing import Any

from agent_evaluator.gates.base import _g, _min_sample_warning


def compute(
    tasks: list[Any],
    gate_b_loop_weight: float,
    min_samples_default: int,
    avg_goal_alignment_ref: float | None,
    avg_plan_coherence_ref: float | None,
    shared_running: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Gate B(행동 무결성) 점수를 집계한다.

    Args:
        tasks: 기록된 TaskResult 리스트.
        gate_b_loop_weight: 루프 감지 점수 가중치(0.0이면 가용 지표 단순 평균).
        min_samples_default: 표본 부족 경고 최소 임계치.
        avg_goal_alignment_ref: Gate A(gate_a_goal.aggregate.compute)에서 이미 계산된
            avg_goal_alignment — 진단용 재참조(Gate B 스코어링 미포함).
        avg_plan_coherence_ref: 위와 동일, avg_plan_coherence.
        shared_running: (SPEC-018) retention_mode="windowed"일 때
            ``GateBSharedAgg.snapshot()``이 제공하는 전체 이력 기준 6개 지표 집계값.
            ``None``(기본값, "full" 모드)이면 기존과 100% 동일하게 `tasks`에서 매번
            재계산한다.

    Returns:
        gates/base.py의 `_g()` 형식 Gate 결과 dict.
    """
    # avg_goal_a / avg_plan_a: Gate A(gates/gate_a_goal/aggregate.py)에서 이미 계산됨 —
    # 파라미터로 전달받아 진단용으로만 재참조 (재계산하지 않음, SPEC-000)
    _avg_goal_a_ref = avg_goal_alignment_ref
    _avg_plan_a_ref = avg_plan_coherence_ref

    if shared_running is not None:
        _loop_counts = shared_running["loop_count"]
        _n_loop_tasks = shared_running["loop_n"]
        avg_sc = shared_running["sc_avg"]
        _sc_n = shared_running["sc_count"]
        _deadlock_count = shared_running["deadlock_count"]
        _n_dl_tasks = shared_running["deadlock_n"]
        _deadlock_by_type: dict[str, int] = shared_running["deadlock_by_type"]
        avg_scope_score = shared_running["scope_avg"]
        _scope_n = shared_running["scope_count"]
        avg_tool_param_safety: float | None = shared_running["tps_avg"]
        _tps_n = shared_running["tps_count"]
        _avg_context_window: float | None = shared_running["cw_avg"]
        _cw_n = shared_running["cw_count"]
    else:
        _loop_counts = sum(
            1 for t in tasks
            if (t.extra or {}).get("loop_detection", {}).get("detected", False)
        )
        # LoopDetectionConfig가 설정된 태스크 수를 분모로 사용 — DeadlockConfig와 동일 패턴
        # 전체 n을 사용하면 부분 배포 시 루프율이 희석되어 Gate B가 허위 부풀려짐
        _n_loop_tasks = sum(1 for t in tasks if (t.extra or {}).get("loop_detection") is not None)

        # consistency_score=None (checks_total=0, 검사 미설정) 제외 — A-1 수정 이후 None 포함 가능
        _sc_scores = [
            t.extra["state_consistency"]["consistency_score"]
            for t in tasks
            if (t.extra or {}).get("state_consistency") is not None
            and t.extra["state_consistency"].get("consistency_score") is not None
        ]
        avg_sc = sum(_sc_scores) / len(_sc_scores) if _sc_scores else None
        _sc_n = len(_sc_scores)

        _deadlock_count = sum(
            1 for t in tasks
            if (t.extra or {}).get("deadlock", {}).get("deadlock_detected", False)
        )
        # DeadlockConfig가 설정된(deadlock extra 존재하는) 태스크 수: 분모 및 score 포함 여부 결정
        _n_dl_tasks = sum(1 for t in tasks if (t.extra or {}).get("deadlock") is not None)
        _deadlock_by_type = {}
        for _t in tasks:
            _dl = (_t.extra or {}).get("deadlock", {})
            if _dl.get("deadlock_detected") and _dl.get("deadlock_type"):
                _dtype = str(_dl["deadlock_type"])
                _deadlock_by_type[_dtype] = _deadlock_by_type.get(_dtype, 0) + 1

        _scope_vals = [
            float(t.extra.get("scope", {}).get("scope_score"))
            for t in tasks
            if (t.extra or {}).get("scope") is not None
            and (t.extra or {}).get("scope", {}).get("scope_score") is not None
        ]
        avg_scope_score = sum(_scope_vals) / len(_scope_vals) if _scope_vals else None
        _scope_n = len(_scope_vals)

        # tool_parameter_safety → Group B (Phase 5)
        _tps_vals = [
            float(t.extra.get("tool_parameter_safety", {}).get("safety_score"))
            for t in tasks
            if (t.extra or {}).get("tool_parameter_safety") is not None
            and (t.extra or {}).get("tool_parameter_safety", {}).get("safety_score") is not None
        ]
        avg_tool_param_safety = (
            sum(_tps_vals) / len(_tps_vals) if _tps_vals else None
        )
        _tps_n = len(_tps_vals)

        # context_window → Group B (Phase 6)
        _cw_scores = [
            float(t.extra.get("context_window", {}).get("context_window_score"))
            for t in tasks
            if t.extra and t.extra.get("context_window")
            and t.extra.get("context_window", {}).get("context_window_score") is not None
        ]
        _avg_context_window = (
            sum(_cw_scores) / len(_cw_scores) if _cw_scores else None
        )
        _cw_n = len(_cw_scores)

    _loop_rate = _loop_counts / _n_loop_tasks if _n_loop_tasks > 0 else 0.0

    # avg_goal_align / avg_plan: Gate A 직접 기여 항목 — Gate B 이중 집계 제거 (진단 목적으로만 유지)
    # loop_detection: 실제 측정 데이터가 있는 태스크가 하나 이상 있을 때만 포함
    # (LoopDetectionConfig 미설정 = 측정 안 함; 루프 없음(1.0)으로 계산하면 Gate B가 허위 부풀려짐)
    _has_loop_data = _n_loop_tasks > 0
    _loop_score: float | None = min(1.0, max(0.0, 1.0 - _loop_rate)) if _has_loop_data else None
    _deadlock_score: float | None = (
        min(1.0, max(0.0, 1.0 - _deadlock_count / _n_dl_tasks)) if _n_dl_tasks > 0 else None
    )
    _other_bint_vals = [
        v for v in [avg_sc, _deadlock_score, avg_scope_score, avg_tool_param_safety, _avg_context_window]
        if v is not None
    ]

    _gate_b_lw = gate_b_loop_weight
    if _gate_b_lw > 0.0 and _loop_score is not None and _other_bint_vals:
        # 루프 감지 가중치 적용 — gate_a_tcr_weight·gate_c_tcr_weight와 동일 패턴
        _bint_score: float | None = (
            _gate_b_lw * _loop_score
            + (1.0 - _gate_b_lw) * (sum(_other_bint_vals) / len(_other_bint_vals))
        )
    elif _gate_b_lw > 0.0 and _loop_score is not None:
        # 루프 데이터만 있는 경우 loop score 그대로
        _bint_score = _loop_score
    else:
        # 기본값(0.0): 가용 지표 단순 평균 (backward compatible)
        _all_bint = ([_loop_score] if _loop_score is not None else []) + _other_bint_vals
        _bint_score = sum(_all_bint) / len(_all_bint) if _all_bint else None

    # ── B 그룹: insufficient_data 경고 수집 (SPEC-002) ──
    # goal_alignment/plan_coherence는 Gate A 진단용 재참조일 뿐 Gate B 스코어링에 미포함되므로
    # 여기서 중복 경고하지 않는다 — Gate A의 insufficient_data_warnings에서 이미 표시됨.
    _b_insufficient: list[str] = []
    for _name, _cnt in (
        ("loop_detection", _n_loop_tasks),
        ("state_consistency", _sc_n),
        ("deadlock", _n_dl_tasks),
        ("scope", _scope_n),
        ("tool_parameter_safety", _tps_n),
        ("context_window", _cw_n),
    ):
        _w = _min_sample_warning(_name, _cnt, min_samples_default)
        if _w:
            _b_insufficient.append(_w)

    # gate_b_loop_weight를 사용자가 명시적으로 설정했는데 loop_detection 데이터가 없어
    # 조용히 단순평균으로 폴백된 경우 — 이전에는 이 사실이 어디에도 안 남아 사용자가
    # 자기 설정이 실제로 적용됐는지 알 방법이 없었다.
    if _gate_b_lw > 0.0 and _loop_score is None:
        _b_insufficient.append(
            f"gate_b_loop_weight={_gate_b_lw} is set but there is no loop_detection data, "
            "so it is not applied (falling back to a simple average of the available metrics)"
        )

    _b_s = round(float(_bint_score), 4) if _bint_score is not None else None

    return _g(_b_s, "Behavioral Integrity", {
        "loop_detection_rate": round(_loop_rate, 4),
        "loop_count": _loop_counts,
        "gate_b_loop_weight": gate_b_loop_weight,
        # 아래 두 항목은 Gate A 계산값 재참조(진단용) — Gate B 점수에는 포함되지 않는다.
        "gate_a_ref__avg_goal_alignment": _avg_goal_a_ref,
        "gate_a_ref__avg_plan_coherence": _avg_plan_a_ref,
        "avg_state_consistency": round(avg_sc, 4) if avg_sc is not None else None,
        "deadlock_count": _deadlock_count,
        "deadlock_by_type": _deadlock_by_type if _deadlock_by_type else None,
        # 점수 계산에 쓴 _deadlock_score를 그대로 재참조 — 별도 공식 재구현으로 인한 drift 방지
        "avg_deadlock_score": round(_deadlock_score, 4) if _deadlock_score is not None else None,
        "avg_scope_score": round(avg_scope_score, 4) if avg_scope_score is not None else None,
        "avg_tool_parameter_safety": round(avg_tool_param_safety, 4) if avg_tool_param_safety is not None else None,
        "avg_context_window": round(_avg_context_window, 4) if _avg_context_window is not None else None,
        "insufficient_data_warnings": _b_insufficient if _b_insufficient else None,
    })
