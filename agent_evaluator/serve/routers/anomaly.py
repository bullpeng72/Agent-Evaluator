"""이상 탐지 API — Phase 3-B."""
from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request

from agent_evaluator.serve.routers._utils import _rs

router = APIRouter(prefix="/api/anomalies", tags=["anomaly"])

@router.get("", summary="Anomaly detection results list")
def list_anomalies(request: Request) -> List[Dict[str, Any]]:
    """List anomaly detection results across all files."""
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

@router.get("/{file_id}", summary="Anomaly detection results for a file")
def get_anomalies(file_id: str, request: Request) -> Dict[str, Any]:
    """Anomaly detection results for a specific file."""
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
