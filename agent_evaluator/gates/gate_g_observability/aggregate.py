"""
agent_evaluator.gates.gate_g_observability.aggregate
=======================================================
Gate G(Observability) 집계 로직.

SPEC-000: agent_evaluator/core/trackers/monitor.py의 `_compute_harness_groups` 내부
Gate G 블록에서 그대로 이관(로직 변경 없음). monitor.py는 이 모듈의 `compute()`를
호출해 위임한다.

이 이관으로 SPEC-000의 Gate A-G 전체 이관이 완료된다.

Gate G는 Gate C(Reliability)가 계산한 hall_rate/avg_llm_faithfulness를 파라미터으로
전달받는다 — LLMJudge faithfulness가 Gate C에 귀속될 때 Gate G의 hallucination
fallback을 비활성화해 이중 반영을 방지하는 기존 로직 그대로다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_evaluator.gates.base import _g, _min_sample_warning


def compute(
    tasks: List[Any],
    tool_call_analyzer: Any,
    min_samples_default: int,
    hall_rate: Optional[float],
    avg_llm_faithfulness: Optional[float],
    shared_running: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Gate G(관측 가능성) 점수를 집계한다.

    Args:
        tasks: 기록된 TaskResult 리스트.
        tool_call_analyzer: `ToolCallAnalyzer` 인스턴스.
        min_samples_default: 표본 부족 경고 최소 임계치.
        hall_rate: Gate C(gate_c_reliability.aggregate.compute)가 반환한 shared_raw의
            원본(반올림 없는) hallucination rate — LLMJudge faithfulness 비활성 시에만 사용.
        avg_llm_faithfulness: 위와 동일, LLM Judge faithfulness 평균(0–5 스케일 원본).
        shared_running: (SPEC-018) retention_mode="windowed"일 때
            ``GateGSharedAgg.snapshot()``이 제공하는 전체 이력 기준 태스크-파생
            4개 지표 집계값. ``None``(기본값, "full" 모드)이면 기존과 100% 동일하게
            `tasks`에서 매번 재계산한다. ``hall_rate``/``avg_llm_faithfulness``는
            Gate C(Phase 6)가 끝나기 전까지 이 파라미터와 무관하게 windowed-only다.

    Returns:
        gates/base.py의 `_g()` 형식 Gate 결과 dict.
    """
    _tool_coverage: Optional[float] = None
    _tc_total_calls = 0
    try:
        _tc_stats = tool_call_analyzer.get_efficiency_stats()
        _tc_total_calls = _tc_stats.get("total_calls", 0)
        if _tc_total_calls > 0:
            _tool_coverage = _tc_stats.get("success_rate", 0.0) / 100.0
    except Exception:
        pass

    if shared_running is not None:
        avg_obs_custom = shared_running["observability_avg"]
        _obs_custom_n = shared_running["observability_count"]
        avg_explainability: Optional[float] = shared_running["explainability_avg"]
        _expl_n = shared_running["explainability_count"]
        avg_error_diagnosis: Optional[float] = shared_running["error_diagnosis_avg"]
        _ed_n = shared_running["error_diagnosis_count"]
        _avg_latency_attribution: Optional[float] = shared_running["latency_attribution_avg"]
        _la_n = shared_running["latency_attribution_count"]
    else:
        _obs_custom_scores = [
            s for s in (
                (t.extra or {}).get("observability", {}).get("observability_score")
                for t in tasks
                if (t.extra or {}).get("observability") is not None
            ) if s is not None
        ]
        avg_obs_custom = sum(_obs_custom_scores) / len(_obs_custom_scores) if _obs_custom_scores else None
        _obs_custom_n = len(_obs_custom_scores)

        _expl_vals = [
            s for s in (
                (t.extra or {}).get("explainability", {}).get("score")
                for t in tasks
                if (t.extra or {}).get("explainability") is not None
            ) if s is not None
        ]
        avg_explainability = sum(_expl_vals) / len(_expl_vals) if _expl_vals else None
        _expl_n = len(_expl_vals)

        # error_diagnosis → Group G (Phase 5)
        _ed_scores = [
            s for s in (
                t.extra.get("error_diagnosis", {}).get("diagnosis_score")
                for t in tasks
                if (t.extra or {}).get("error_diagnosis") is not None
            ) if s is not None
        ]
        avg_error_diagnosis = (
            sum(_ed_scores) / len(_ed_scores) if _ed_scores else None
        )
        _ed_n = len(_ed_scores)

        # latency_attribution → Group G (Phase 6)
        _la_scores = [
            s for s in (
                t.extra.get("latency_attribution", {}).get("attribution_score")
                for t in tasks
                if t.extra and t.extra.get("latency_attribution")
            ) if s is not None
        ]
        _avg_latency_attribution = (
            sum(_la_scores) / len(_la_scores) if _la_scores else None
        )
        _la_n = len(_la_scores)

    _obs_vals: List[float] = []
    if _tool_coverage is not None:
        _obs_vals.append(_tool_coverage)
    # hall_rate → Gate G: LLMJudge faithfulness 비활성 시에만 사용
    # (LLMJudge 활성 시 faithfulness가 Gate C에 귀속되므로 Gate G 이중 반영 방지)
    if hall_rate is not None and avg_llm_faithfulness is None:
        _obs_vals.append(max(0.0, 1.0 - float(hall_rate)))
    if avg_obs_custom is not None:
        _obs_vals.append(avg_obs_custom)
    if avg_explainability is not None:
        _obs_vals.append(avg_explainability)
    if avg_error_diagnosis is not None:
        _obs_vals.append(avg_error_diagnosis)
    if _avg_latency_attribution is not None:
        _obs_vals.append(_avg_latency_attribution)
    _obs_score: Optional[float] = sum(_obs_vals) / len(_obs_vals) if _obs_vals else None

    # ── G 그룹: insufficient_data 경고 수집 (SPEC-002, task 기반 4개 지표) ──
    _g_insufficient: List[str] = []
    for _name, _cnt in (
        ("observability", _obs_custom_n),
        ("explainability", _expl_n),
        ("error_diagnosis", _ed_n),
        ("latency_attribution", _la_n),
    ):
        _w = _min_sample_warning(_name, _cnt, min_samples_default)
        if _w:
            _g_insufficient.append(_w)

    # SPEC-012: tool_coverage — 분모가 task 수가 아니라 도구 호출 수(total_calls)이므로
    # unit을 명시해 task 기반 경고와 혼동되지 않게 한다.
    _w_tc = _min_sample_warning(
        "tool_coverage", _tc_total_calls, min_samples_default, unit="calls"
    )
    if _w_tc:
        _g_insufficient.append(_w_tc)

    # _obs_score=None이면 Gate G 데이터 없음 → 호출자(monitor.py)의 _scored에서 제외
    _g_s = round(float(_obs_score), 4) if _obs_score is not None else None

    return _g(_g_s, "Observability", {
        "tool_coverage": round(_tool_coverage, 4) if _tool_coverage is not None else None,
        "hallucination_rate": round(hall_rate, 4) if hall_rate is not None else None,
        "avg_observability_score": round(avg_obs_custom, 4) if avg_obs_custom is not None else None,
        "avg_explainability": round(avg_explainability, 4) if avg_explainability is not None else None,
        "avg_error_diagnosis": round(avg_error_diagnosis, 4) if avg_error_diagnosis is not None else None,
        "avg_latency_attribution": round(_avg_latency_attribution, 4) if _avg_latency_attribution is not None else None,
        "insufficient_data_warnings": _g_insufficient if _g_insufficient else None,
    })
