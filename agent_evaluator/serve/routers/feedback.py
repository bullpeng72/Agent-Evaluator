"""User feedback API — Phase 2-C."""
from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request

from agent_evaluator.serve.routers._utils import _rs

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

@router.get("", summary="Feedback list")
def list_feedback(request: Request) -> List[Dict[str, Any]]:
    """Feedback data list across all files."""
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

@router.get("/{file_id}", summary="Feedback for a file")
def get_feedback(file_id: str, request: Request) -> Dict[str, Any]:
    """Feedback detail for a specific file."""
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")
    fb_data = getattr(rf, "feedback_data", {})
    return {"file_id": file_id, **fb_data}
