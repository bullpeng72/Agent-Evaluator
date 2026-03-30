"""이상 탐지 API — Phase 3-B."""
from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/anomalies")

def _rs(request: Request):
    return request.app.state.result_set

@router.get("")
def list_anomalies(request: Request) -> List[Dict[str, Any]]:
    """모든 파일의 이상 탐지 결과 목록."""
    rs = _rs(request)
    result = []
    for f in rs.files:
        anomalies = getattr(f, "anomaly_data", [])
        if anomalies:
            result.append({
                "file_id": f.file_id,
                "file_name": f.name,
                "count": len(anomalies),
                "critical": sum(1 for a in anomalies if a.get("severity") == "critical"),
                "warning": sum(1 for a in anomalies if a.get("severity") == "warning"),
                "anomalies": anomalies,
            })
    return result

@router.get("/{file_id}")
def get_anomalies(file_id: str, request: Request) -> Dict[str, Any]:
    """특정 파일의 이상 탐지 결과."""
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")
    anomalies = getattr(rf, "anomaly_data", [])

    return {
        "file_id": file_id,
        "count": len(anomalies),
        "critical": sum(1 for a in anomalies if a.get("severity") == "critical"),
        "warning": sum(1 for a in anomalies if a.get("severity") == "warning"),
        "anomalies": anomalies,
    }
