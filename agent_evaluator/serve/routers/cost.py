"""평가 비용 API — Phase 3-C."""
from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/cost", tags=["cost"])

def _rs(request: Request):
    return request.app.state.result_set

@router.get("/summary")
def cost_summary(request: Request) -> Dict[str, Any]:
    """전체 평가 비용 요약."""
    rs = _rs(request)
    total_usd = 0.0
    by_file: List[Dict[str, Any]] = []

    for f in rs.files:
        cost_data = getattr(f, "cost_data", {})
        file_total = cost_data.get("total_usd", 0.0)
        total_usd += file_total
        if cost_data:
            by_file.append({
                "file_id": f.file_id,
                "file_name": f.name,
                "total_usd": round(file_total, 6),
                **{k: v for k, v in cost_data.items() if k != "total_usd"},
            })

    return {
        "total_usd": round(total_usd, 6),
        "file_count": len(rs.files),
        "by_file": by_file,
    }

@router.get("/{file_id}")
def get_file_cost(file_id: str, request: Request) -> Dict[str, Any]:
    """특정 파일의 비용 상세."""
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")
    cost_data = getattr(rf, "cost_data", {})
    return {"file_id": file_id, **cost_data}
