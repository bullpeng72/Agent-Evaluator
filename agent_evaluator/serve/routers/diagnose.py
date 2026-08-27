"""
agent_evaluator.serve.routers.diagnose
==========================================
대시보드 "Improve" 탭 백엔드 — Phase 8(개선 엔진 UI). 새 판정 로직은 없다: 이미 존재하는
``agent_evaluator.rca.diagnose()``/``load_recommendation_outcomes()``/
``summarize_recommendation_outcomes()``를 HTTP로 얇게 감쌀 뿐이다(``agent-eval diagnose``
CLI가 같은 함수를 감싸는 것과 동일한 관계).

HOTL 원칙(Chapter 2): 이 라우터도 후보 원인과 근거만 반환한다 — "이게 원인이다"를
단정하지 않는다.
"""
from __future__ import annotations

from typing import Any, Dict, Optional  # noqa: UP035

from fastapi import APIRouter, HTTPException, Query, Request

from agent_evaluator.rca import diagnose
from agent_evaluator.rca.recommendation_tracking import (
    load_recommendation_outcomes,
    summarize_recommendation_outcomes,
)
from agent_evaluator.serve.routers._utils import _rs

router = APIRouter(prefix="/api/diagnose", tags=["diagnose"])

# results_dir 아래 고정 파일명 — agent-eval CLI의 rca.record_recommendation_outcome()
# 호출자가 이 경로에 기록하면 대시보드가 그대로 읽는다(별도 설정 없이 바로 연동).
_RECOMMENDATIONS_FILENAME = "recommendation_outcomes.jsonl"


@router.get("/{file_id}", summary="Gate RCA diagnosis for a result file")
def get_diagnosis(
    file_id: str,
    request: Request,
    baseline_id: Optional[str] = Query(  # noqa: UP045
        None, description="Baseline result file id for regression detection",
    ),
    regression_threshold: float = Query(0.1, description="Allowed regression vs baseline (0-1)"),
    show_diff: bool = Query(False, description="Resolve git commit range via lineage.git_commit"),
) -> Dict[str, Any]:  # noqa: UP006
    """``agent-eval diagnose``와 동일한 판정을 대시보드용 JSON으로 반환한다.

    Args:
        file_id: 진단할(현재) 결과 파일 id.
        baseline_id: 비교 기준 파일 id(선택) — 주어지면 회귀 기반 감지,
            없으면 현재 fail/warn 상태 기반 감지로 폴백한다(``diagnose()``와 동일).
        regression_threshold: baseline 대비 허용 회귀 비율(%가 아니라 0-1 소수).
        show_diff: ``True``면 두 파일의 ``lineage.git_commit`` 사이 실제 git diff를
            함께 조회한다(``agent-eval diagnose --show-diff``와 동일).
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")

    baseline_raw: Optional[Dict[str, Any]] = None  # noqa: UP006,UP045
    if baseline_id:
        baseline_rf = rs.by_id(baseline_id)
        if baseline_rf is None:
            raise HTTPException(status_code=404, detail=f"Baseline file not found: {baseline_id}")
        baseline_raw = baseline_rf.raw

    result = diagnose(
        rf.raw, baseline_raw,
        regression_threshold=regression_threshold,
        with_experiment_metadata=show_diff,
        repo_path=str(getattr(request.app.state, "results_dir", ".")),
    )
    result["file_id"] = file_id
    result["baseline_id"] = baseline_id
    return result


@router.get("/", summary="Recommendation outcome history")
def get_recommendation_outcomes(
    request: Request,
    gate: Optional[str] = Query(None, description="Filter by target_gate"),  # noqa: UP045
) -> Dict[str, Any]:  # noqa: UP006
    """추천 적용 이력(``rca.record_recommendation_outcome()``이 기록한 JSONL)을
    읽어 원본 이력 + 개수 집계를 반환한다. 파일이 없으면 빈 이력(정상 — 아직 아무
    추천도 기록되지 않았다는 뜻, 에러 아님).
    """
    results_dir = getattr(request.app.state, "results_dir", None)
    if results_dir is None:
        return {"outcomes": [], "summary": summarize_recommendation_outcomes([])}
    from pathlib import Path

    log_path = Path(results_dir) / _RECOMMENDATIONS_FILENAME  # str app.state에도 안전
    outcomes = load_recommendation_outcomes(log_path, target_gate=gate)
    return {"outcomes": outcomes, "summary": summarize_recommendation_outcomes(outcomes)}
