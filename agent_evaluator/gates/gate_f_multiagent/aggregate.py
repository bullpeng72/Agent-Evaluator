"""
agent_evaluator.gates.gate_f_multiagent.aggregate
====================================================
Gate F(Multi-Agent Coordination) 집계 로직.

SPEC-000 Commit 1: agent_evaluator/core/trackers/monitor.py의 `_compute_harness_groups`
Gate F 블록에서 이관. Gate F는 다른 Gate의 변수를 참조하지 않는 완전 독립 슬라이스임을
확인했으므로(2026-07-02 조사), `tasks` + 트래커 2개 + `min_samples_default`만 받는
순수 함수로 분리했다.

SPEC-000 REQ-2 일부 흡수: 태스크 기반 4개 지표(consensus/propagation/agent_role/
conflict_resolution)는 서로 독립적인 필터 조건이므로 단일 `for t in tasks:` 패스로
병합했다(원래는 4개 리스트 컴프리헨션). coordination/tool_selection은 tasks를 순회하지
않고 트래커 자체 메서드를 호출하므로 병합 대상이 아니다(원래 로직 그대로 유지).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_evaluator.gates.base import _g, _min_sample_warning


def compute(
    tasks: list,
    agent_coordination_tracker: Any,
    tool_selection_tracker: Any,
    min_samples_default: int,
) -> Dict[str, Any]:
    """Gate F(Multi-Agent Coordination) 그룹 딕셔너리를 계산한다.

    Args:
        tasks: TaskResult 리스트.
        agent_coordination_tracker: PerformanceMonitor.agent_coordination_tracker.
        tool_selection_tracker: PerformanceMonitor.tool_selection_tracker.
        min_samples_default: SPEC-002 최소 표본 가드 기본값.

    Returns:
        {name, score, status, gate, details} — monitor.py의 groups["F"]와 동일한 형태.
    """
    # Fix1+2: self.coordination_tracker(없는 속성) + get_coordination_stats()(없는 메서드) 수정
    # calculate_coordination_score()의 overall_score(0-10)를 /10으로 정규화
    _coord_data: Optional[float] = None
    _coord_total_interactions = 0
    try:
        _coord_score_data = agent_coordination_tracker.calculate_coordination_score()
        _coord_total_interactions = _coord_score_data.get("total_interactions", 0)
        if _coord_total_interactions > 0:
            _coord_data = float(min(1.0, max(0.0,
                _coord_score_data.get("overall_score", 0.0) / 10.0
            )))
    except Exception:
        pass

    # Fix7: ToolSelectionTracker → Gate F (avg_f1_score 0-100 → /100 정규화)
    _ts_data: Optional[float] = None
    _ts_total_evaluations = 0
    try:
        _ts_stats = tool_selection_tracker.get_accuracy_stats()
        _ts_total_evaluations = _ts_stats.get("total_evaluations", 0)
        if _ts_total_evaluations > 0:
            _ts_f1 = _ts_stats.get("avg_f1_score")
            if _ts_f1 is not None:
                _ts_data = float(min(1.0, max(0.0, _ts_f1 / 100.0)))
    except Exception:
        pass

    # 단일 패스 병합(SPEC-000 REQ-2) — 4개 지표 모두 서로 독립적인 필터 조건(t.extra의
    # "consensus"/"propagation"/"agent_role"/"conflict_resolution" 키, consensus는 추가로
    # method != "single")이므로 하나의 for 루프에서 동시에 축적 가능.
    _consensus_scores: List[float] = []
    _prop_vals: List[float] = []
    _role_scores: List[float] = []
    _conflict_scores: List[float] = []
    for t in tasks:
        extra = t.extra or {}

        _consensus = extra.get("consensus")
        if _consensus is not None:
            _cs = _consensus.get("consensus_score")
            # method="single": 단일 에이전트 → 합의 측정 불가 → Gate F 집계에서 제외
            if _cs is not None and _consensus.get("method") != "single":
                _consensus_scores.append(float(_cs))

        _prop = extra.get("propagation")
        if _prop is not None:
            _fs = _prop.get("fidelity_score")
            if _fs is not None:
                _prop_vals.append(float(_fs))

        _role = extra.get("agent_role")
        if _role is not None:
            _rc = _role.get("role_compliance_score")
            if _rc is not None:
                _role_scores.append(float(_rc))

        _conflict = extra.get("conflict_resolution")
        if _conflict is not None:
            _rs = _conflict.get("resolution_score")
            if _rs is not None:
                _conflict_scores.append(float(_rs))

    avg_consensus: Optional[float] = (
        sum(_consensus_scores) / len(_consensus_scores) if _consensus_scores else None
    )
    avg_propagation: Optional[float] = (
        sum(_prop_vals) / len(_prop_vals) if _prop_vals else None
    )
    _avg_role: Optional[float] = (
        sum(_role_scores) / len(_role_scores) if _role_scores else None
    )
    _avg_conflict_res: Optional[float] = (
        sum(_conflict_scores) / len(_conflict_scores) if _conflict_scores else None
    )

    _f_vals: List[float] = []
    if _coord_data is not None:
        _f_vals.append(_coord_data)
    if _ts_data is not None:
        _f_vals.append(_ts_data)
    if avg_consensus is not None:
        _f_vals.append(avg_consensus)
    if avg_propagation is not None:
        _f_vals.append(avg_propagation)
    if _avg_role is not None:
        _f_vals.append(_avg_role)
    if _avg_conflict_res is not None:
        _f_vals.append(_avg_conflict_res)
    _f_score: Optional[float] = float(sum(_f_vals) / len(_f_vals)) if _f_vals else None

    # SPEC-002: insufficient_data 경고 (task 기반 4개 지표)
    _f_insufficient: List[str] = []
    for _name, _cnt in (
        ("consensus", len(_consensus_scores)),
        ("propagation", len(_prop_vals)),
        ("agent_role", len(_role_scores)),
        ("conflict_resolution", len(_conflict_scores)),
    ):
        _w = _min_sample_warning(_name, _cnt, min_samples_default)
        if _w:
            _f_insufficient.append(_w)

    # SPEC-012: 이벤트 기반 2개 지표 — 분모가 task 수가 아니라 이벤트 수이므로 unit을
    # 명시해 task 기반 경고와 혼동되지 않게 한다.
    _w_coord = _min_sample_warning(
        "coordination_score", _coord_total_interactions, min_samples_default, unit="interactions"
    )
    if _w_coord:
        _f_insufficient.append(_w_coord)
    _w_ts = _min_sample_warning(
        "tool_selection_f1", _ts_total_evaluations, min_samples_default, unit="evaluations"
    )
    if _w_ts:
        _f_insufficient.append(_w_ts)

    _f_s = round(_f_score, 4) if _f_score is not None else None

    return _g(_f_s, "Multi-Agent Coordination", {
        "coordination_score": round(_coord_data, 4) if _coord_data is not None else None,
        "avg_tool_selection_f1": round(_ts_data, 4) if _ts_data is not None else None,
        "avg_consensus": round(avg_consensus, 4) if avg_consensus is not None else None,
        "avg_propagation": round(avg_propagation, 4) if avg_propagation is not None else None,
        "avg_role_compliance": round(_avg_role, 4) if _avg_role is not None else None,
        "avg_conflict_resolution": round(_avg_conflict_res, 4) if _avg_conflict_res is not None else None,
        "insufficient_data_warnings": _f_insufficient if _f_insufficient else None,
    }, f_score=True)
