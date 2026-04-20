"""멀티턴 대화 평가 API — Phase 1-C.

GET /api/conversation                        — 모든 파일의 대화 세션 요약 목록
GET /api/conversation/{file_id}              — 특정 파일의 세션 집계 통계 + 목록
GET /api/conversation/{file_id}/{session_id} — 특정 세션 turn-by-turn 상세
"""
from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request

from agent_evaluator.serve.routers._utils import _rs

router = APIRouter(prefix="/api/conversation", tags=["conversation"])

@router.get("", summary="대화 세션 목록")
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

@router.get("/{file_id}", summary="파일별 대화 세션")
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


@router.get("/{file_id}/{session_id}", summary="대화 세션 상세")
def get_session_detail(file_id: str, session_id: str, request: Request) -> Dict[str, Any]:
    """특정 세션의 turn-by-turn 상세 + 6개 지표 분석.

    Returns:
        session_id, turn_count, metrics (6개), turns (역할·내용·latency),
        quality_summary (상위/하위 턴 분석)
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    sessions = getattr(rf, "conversation_sessions", [])
    session = next(
        (s for s in sessions if s.get("session_id") == session_id),
        None,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    metrics = session.get("metrics", {})
    turns: List[Dict[str, Any]] = session.get("turns", [])

    # 상위/하위 턴 분석 (latency 기준)
    latencies = [t.get("latency", 0.0) for t in turns if t.get("latency") is not None]
    quality_summary: Dict[str, Any] = {}
    if latencies:
        quality_summary["avg_latency"] = round(sum(latencies) / len(latencies), 3)
        quality_summary["max_latency"] = round(max(latencies), 3)
        quality_summary["min_latency"] = round(min(latencies), 3)
        # 가장 느린/빠른 턴 인덱스
        quality_summary["slowest_turn"] = latencies.index(max(latencies))
        quality_summary["fastest_turn"] = latencies.index(min(latencies))

    return {
        "file_id": file_id,
        "session_id": session_id,
        "turn_count": session.get("turn_count", len(turns)),
        "metrics": {
            "overall_score":       round(metrics.get("overall_score", 0.0), 3),
            "context_retention":   round(metrics.get("context_retention", 0.0), 3),
            "topic_coherence":     round(metrics.get("topic_coherence", 0.0), 3),
            "progressive_depth":   round(metrics.get("progressive_depth", 0.0), 3),
            "session_completion":  round(metrics.get("session_completion", 0.0), 3),
            "avg_response_latency": round(metrics.get("avg_response_latency", 0.0), 3),
        },
        "turns": turns,
        "quality_summary": quality_summary,
    }
