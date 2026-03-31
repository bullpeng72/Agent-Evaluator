"""멀티턴 대화 평가 API — Phase 1-C."""
from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/conversation", tags=["conversation"])

def _rs(request: Request):
    return request.app.state.result_set

@router.get("")
def list_conversations(request: Request) -> List[Dict[str, Any]]:
    """모든 파일의 대화 세션 요약 목록."""
    rs = _rs(request)
    result = []
    for f in rs.files:
        sessions = getattr(f, "conversation_sessions", [])
        if sessions:
            result.append({
                "file_id": f.file_id,
                "file_name": f.name,
                "session_count": len(sessions),
                "sessions": sessions,
            })
    return result

@router.get("/{file_id}")
def get_conversations(file_id: str, request: Request) -> Dict[str, Any]:
    """특정 파일의 대화 세션 상세."""
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")
    sessions = getattr(rf, "conversation_sessions", [])

    # 집계 통계
    if sessions:
        n = len(sessions)
        avg_overall = sum(s.get("metrics", {}).get("overall_score", 0) for s in sessions) / n
        avg_turns = sum(s.get("turn_count", 0) for s in sessions) / n
        avg_context = sum(s.get("metrics", {}).get("context_retention", 0) for s in sessions) / n
        avg_coherence = sum(s.get("metrics", {}).get("topic_coherence", 0) for s in sessions) / n
        avg_depth = sum(s.get("metrics", {}).get("progressive_depth", 0) for s in sessions) / n
        avg_completion = sum(s.get("metrics", {}).get("session_completion", 0) for s in sessions) / n
        avg_latency = sum(s.get("metrics", {}).get("avg_response_latency", 0) for s in sessions) / n
    else:
        avg_overall = avg_turns = avg_context = avg_coherence = avg_depth = avg_completion = avg_latency = 0.0

    return {
        "file_id": file_id,
        "session_count": len(sessions),
        "summary": {
            "avg_overall_score": round(avg_overall, 3),
            "avg_turns": round(avg_turns, 1),
            "avg_context_retention": round(avg_context, 3),
            "avg_topic_coherence": round(avg_coherence, 3),
            "avg_progressive_depth": round(avg_depth, 3),
            "avg_session_completion": round(avg_completion, 3),
            "avg_response_latency": round(avg_latency, 3),
        },
        "sessions": sessions,
    }
