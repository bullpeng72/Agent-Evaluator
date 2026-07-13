"""
agent_evaluator.gates.gate_a_goal.aggregate
==============================================
Gate A(Goal Achievement) 집계 로직.

SPEC-000: agent_evaluator/core/trackers/monitor.py의 `_compute_harness_groups`
Gate A 블록에서 이관. 로직은 원본과 완전히 동일(위치 이관이 목적이며 SPEC-003 최적화는
별도 범위).

Gate B(Behavioral Integrity)가 avg_goal_alignment/avg_plan_coherence를 진단용으로
재참조한다 — 이 함수의 반환 details에 이미 포함되므로, monitor.py의 Gate B 섹션은
이 함수의 반환값에서 값을 읽어온다(재계산하지 않음).
"""
from __future__ import annotations

from typing import Any

from agent_evaluator.gates.base import _g, _min_sample_warning


def compute(
    tasks: list,
    tcr_tracker: Any,
    accuracy_evaluator: Any,
    quality_evaluator: Any,
    gate_a_tcr_weight: float,
    min_samples_default: int,
    shared_running: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Gate A(Goal Achievement) 그룹 딕셔너리를 계산한다.

    Args:
        tasks: TaskResult 리스트.
        tcr_tracker: PerformanceMonitor.tcr_tracker.
        accuracy_evaluator: PerformanceMonitor.accuracy_evaluator.
        quality_evaluator: PerformanceMonitor.quality_evaluator.
        gate_a_tcr_weight: PerformanceMonitor._gate_a_tcr_weight.
        min_samples_default: SPEC-002 최소 표본 가드 기본값.
        shared_running: (SPEC-018) retention_mode="windowed"일 때
            ``GateASharedAgg.snapshot()``이 제공하는 전체 이력 기준 6개 지표 집계값
            (instruction_adherence/goal_alignment/plan_coherence/subtask_completion/
            context_retention/knowledge_retention — goal_alignment/plan_coherence는
            LLM-judge 블렌딩 이후의 최종 스칼라를 누적한다). TCR 컴포넌트(tcr_tracker)와
            accuracy_evaluator/quality_evaluator 기반 부분은 이 스펙 범위 밖(기존
            _RunningTCRView 및 별도 무제한 트래커 그대로). ``None``(기본값, "full"
            모드)이면 기존과 100% 동일하게 `tasks`에서 매번 재계산한다.

    Returns:
        {name, score, status, gate, details} — monitor.py의 groups["A"]와 동일한 형태.
        details에는 avg_goal_alignment/avg_plan_coherence가 포함되어 있어
        Gate B가 진단용으로 재참조할 수 있다.
    """
    tcr_pct_a = 0.0
    try:
        _tcr_stats_a = tcr_tracker.calculate_tcr()
        tcr_pct_a = float(_tcr_stats_a.get("tcr", 0.0))
    except Exception:
        pass

    if shared_running is not None:
        avg_ifr = shared_running["ifr_avg"]
        _ifr_n = shared_running["ifr_count"]
        avg_goal_a = shared_running["goal_avg"]
        _goal_a_n = shared_running["goal_count"]
        avg_plan_a = shared_running["plan_avg"]
        _plan_a_n = shared_running["plan_count"]
        avg_subtask = shared_running["subtask_avg"]
        _subtask_n = shared_running["subtask_count"]
        avg_context_r = shared_running["context_retention_avg"]
        _cr_n = shared_running["context_retention_count"]
        avg_knowledge_ret: float | None = shared_running["knowledge_retention_avg"]
        _kr_n = shared_running["knowledge_retention_count"]
    else:
        _ifr_scores = [
            float(t.extra.get("instruction_adherence", {}).get("score"))
            for t in tasks
            if (t.extra or {}).get("instruction_adherence") is not None
            and (t.extra or {}).get("instruction_adherence", {}).get("score") is not None
        ]
        avg_ifr = sum(_ifr_scores) / len(_ifr_scores) if _ifr_scores else None
        _ifr_n = len(_ifr_scores)

        _goal_a_vals: list[float] = []
        _goal_a_excluded = 0
        for _t in tasks:
            _ga = ((_t.extra or {}).get("goal_alignment") or {})
            if not _ga:
                continue
            _ga_score_raw = _ga.get("score")
            if _ga_score_raw is None:   # goal_tool_map 불일치·미측정 태스크 → 집계 제외
                _goal_a_excluded += 1
                continue
            _ga_score = float(_ga_score_raw)
            # use_llm_scoring=True 이고 LLM judge relevance 점수가 있으면 블렌딩 (추가 API 호출 없음)
            if _ga.get("use_llm_scoring"):
                _lj = (_t.extra or {}).get("llm_judge") or {}
                _lj_scores = _lj.get("scores") or {}
                _rel = _lj_scores.get("relevance")
                if _rel is not None:
                    try:
                        _rel_norm = min(1.0, max(0.0, float(_rel) / 5.0))  # 0-5 → 0-1 정규화 + 범위 클램프
                        _w = max(0.0, min(1.0, float(_ga.get("llm_blend_weight", 0.5))))
                        _ga_score = _ga_score * (1 - _w) + _rel_norm * _w
                    except (TypeError, ValueError):
                        pass
            _goal_a_vals.append(_ga_score)
        avg_goal_a = sum(_goal_a_vals) / len(_goal_a_vals) if _goal_a_vals else None
        _goal_a_n = len(_goal_a_vals)
        if avg_goal_a is None and _goal_a_excluded > 1:
            import logging
            logging.getLogger(__name__).warning(
                "[Gate A] GoalAlignmentConfig: %d task(s) all excluded (score=None). "
                "For non-tool agents, set GoalAlignmentConfig(ignore_no_tool_tasks=False).",
                _goal_a_excluded,
            )

        _plan_a_vals: list[float] = []
        for _t in tasks:
            _pc = ((_t.extra or {}).get("plan_coherence") or {})
            if not _pc:
                continue
            _pc_score_raw = _pc.get("score")
            if _pc_score_raw is None:
                continue
            _pc_score = float(_pc_score_raw)
            # use_llm_scoring=True 이면 기존 LLM judge relevance 점수와 가중 블렌딩
            if _pc.get("use_llm_scoring"):
                _lj_pc = ((_t.extra or {}).get("llm_judge") or {})
                _rel_pc = (_lj_pc.get("scores") or {}).get("relevance")
                if _rel_pc is not None:
                    try:
                        _w_pc = max(0.0, min(1.0, float(_pc.get("llm_blend_weight", 0.5))))
                        _rel_norm_pc = min(1.0, max(0.0, float(_rel_pc) / 5.0))  # 0-5 → 0-1 정규화 + 범위 클램프
                        _pc_score = _pc_score * (1 - _w_pc) + _rel_norm_pc * _w_pc
                    except (TypeError, ValueError):
                        pass
            _plan_a_vals.append(_pc_score)
        avg_plan_a = sum(_plan_a_vals) / len(_plan_a_vals) if _plan_a_vals else None
        _plan_a_n = len(_plan_a_vals)

        _subtask_vals = [
            float(t.extra.get("subtask_completion", {}).get("completion_rate"))
            for t in tasks
            if (t.extra or {}).get("subtask_completion") is not None
            and (t.extra or {}).get("subtask_completion", {}).get("completion_rate") is not None
            # subtask_count=0: expected_subtasks 미설정 → completion_rate=1.0이 의미 없으므로 제외
            and int((t.extra or {}).get("subtask_completion", {}).get("subtask_count", 0)) > 0
        ]
        avg_subtask = sum(_subtask_vals) / len(_subtask_vals) if _subtask_vals else None
        _subtask_n = len(_subtask_vals)

        _cr_vals = [
            float(t.extra.get("context_retention", {}).get("retention_score"))
            for t in tasks
            if (t.extra or {}).get("context_retention") is not None
            and (t.extra or {}).get("context_retention", {}).get("retention_score") is not None
        ]
        avg_context_r = sum(_cr_vals) / len(_cr_vals) if _cr_vals else None
        _cr_n = len(_cr_vals)

        # knowledge_retention → Group A (Phase 5)
        _kr_vals = [
            float(t.extra.get("knowledge_retention", {}).get("retention_score"))
            for t in tasks
            if (t.extra or {}).get("knowledge_retention") is not None
            and t.extra.get("knowledge_retention", {}).get("retention_score") is not None
        ]
        avg_knowledge_ret = sum(_kr_vals) / len(_kr_vals) if _kr_vals else None
        _kr_n = len(_kr_vals)

    # ── A 그룹: insufficient_data 경고 수집 (SPEC-002) ──
    _a_insufficient: list[str] = []
    for _name, _cnt in (
        ("instruction_adherence", _ifr_n),
        ("goal_alignment", _goal_a_n),
        ("plan_coherence", _plan_a_n),
        ("subtask_completion", _subtask_n),
        ("context_retention", _cr_n),
        ("knowledge_retention", _kr_n),
    ):
        _w = _min_sample_warning(_name, _cnt, min_samples_default)
        if _w:
            _a_insufficient.append(_w)

    _a_vals: list[float] = [tcr_pct_a / 100.0]
    if avg_ifr is not None:
        _a_vals.append(avg_ifr)
    if avg_goal_a is not None:
        _a_vals.append(avg_goal_a)
    if avg_plan_a is not None:
        _a_vals.append(avg_plan_a)
    if avg_subtask is not None:
        _a_vals.append(avg_subtask)
    if avg_context_r is not None:
        _a_vals.append(avg_context_r)
    if avg_knowledge_ret is not None:
        _a_vals.append(avg_knowledge_ret)

    # AccuracyEvaluator → TCR 보정 (상관 중복 방지)
    # completion_score(3-버킷)와 accuracy(4-metric 연속)는 같은 ground_truth 신호를 공유
    # → 별도 컴포넌트 추가 대신, AccuracyEvaluator 정밀도로 TCR 컴포넌트를 블렌딩
    _avg_accuracy_a: float | None = None
    try:
        _acc_evals_a = accuracy_evaluator._evaluations
        _acc_measured_a = [e for e in _acc_evals_a if e.get("accuracy") is not None]
        if _acc_measured_a:
            _acc_scores_a = accuracy_evaluator.get_accuracy_scores()
            _avg_accuracy_a = float(_acc_scores_a.get("overall_accuracy", 0.0)) / 100.0
            _a_vals[0] = 0.6 * _a_vals[0] + 0.4 * _avg_accuracy_a
    except Exception:
        pass

    # ResponseQualityEvaluator → Gate A: relevance + completeness 차원 (0-5 → 0-1)
    _rqe_a: float | None = None
    try:
        _dim_avgs_q = quality_evaluator.get_quality_metrics().get("dimension_averages", {})
        _rqe_q_scores = [
            _dim_avgs_q[k] for k in ("relevance", "completeness")
            if _dim_avgs_q.get(k) is not None
        ]
        if _rqe_q_scores:
            _rqe_a = sum(_rqe_q_scores) / len(_rqe_q_scores) / 5.0  # 0-5 → 0-1
    except Exception:
        pass

    if _rqe_a is not None:
        _a_vals.append(_rqe_a)

    # TCR은 Gate A 핵심 지표 — gate_a_tcr_weight(기본 0.4)로 Config 지표와 가중 평균
    _tcr_component = _a_vals[0]
    _config_components = _a_vals[1:]
    if _config_components:
        _config_avg = sum(_config_components) / len(_config_components)
        _a_score = gate_a_tcr_weight * _tcr_component + (1.0 - gate_a_tcr_weight) * _config_avg
    else:
        _a_score = float(_tcr_component)

    _a_s = round(_a_score, 4)

    return _g(_a_s, "Goal Achievement", {
        "tcr_pct": round(tcr_pct_a, 2),
        "avg_accuracy": round(_avg_accuracy_a, 4) if _avg_accuracy_a is not None else None,
        "avg_quality_relevance_completeness": round(_rqe_a, 4) if _rqe_a is not None else None,
        "gate_a_tcr_weight": gate_a_tcr_weight,
        "tasks_with_ifr": _ifr_n,
        "avg_instruction_adherence": round(avg_ifr, 4) if avg_ifr is not None else None,
        "avg_goal_alignment": round(avg_goal_a, 4) if avg_goal_a is not None else None,
        "avg_plan_coherence": round(avg_plan_a, 4) if avg_plan_a is not None else None,
        "avg_subtask_completion": round(avg_subtask, 4) if avg_subtask is not None else None,
        "avg_context_retention": round(avg_context_r, 4) if avg_context_r is not None else None,
        "avg_knowledge_retention": round(avg_knowledge_ret, 4) if avg_knowledge_ret is not None else None,
        "insufficient_data_warnings": _a_insufficient if _a_insufficient else None,
    })
