"""사용자 피드백 API — Phase 2-C."""
from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/feedback")

def _rs(request: Request):
    return request.app.state.result_set

@router.get("")
def list_feedback(request: Request) -> List[Dict[str, Any]]:
    """모든 파일의 피드백 데이터 목록."""
    rs = _rs(request)
    result = []
    for f in rs.files:
        fb_data = getattr(f, "feedback_data", {})
        if fb_data:
            result.append({
                "file_id": f.file_id,
                "file_name": f.name,
                **fb_data,
            })
    return result

@router.get("/{file_id}")
def get_feedback(file_id: str, request: Request) -> Dict[str, Any]:
    """특정 파일의 피드백 상세."""
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")
    fb_data = getattr(rf, "feedback_data", {})
    return {"file_id": file_id, **fb_data}
