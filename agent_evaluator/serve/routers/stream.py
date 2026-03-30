"""
SSE stream route.

GET /api/stream          — Server-Sent Events for file change notifications.
GET /api/stream/live-stats — Current StreamingEvaluator window stats (JSON).
"""
from __future__ import annotations

import asyncio
import json as _json
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/api")


@router.get("/stream")
async def sse_stream(request: Request):
    """
    Server-Sent Events endpoint.

    Emits:
        data: {"type": "update"}   — when results directory changes
        data: {"type": "ping"}     — keep-alive every 15 s
    """
    watcher = getattr(request.app.state, "watcher", None)
    if watcher is None:
        # Watch mode disabled — return a single ping and close
        async def _disabled():
            yield "data: {\"type\":\"disabled\"}\n\n"
        return StreamingResponse(_disabled(), media_type="text/event-stream")

    queue = watcher.subscribe()

    async def _generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    payload = _json.dumps({"type": event})
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive ping
                    yield "data: {\"type\":\"ping\"}\n\n"
        finally:
            watcher.unsubscribe(queue)

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/stream/live-stats")
async def live_stats(request: Request, window: str = "5m") -> JSONResponse:
    """
    Return current sliding-window metrics from StreamingEvaluator (if running).

    Query params:
        window: "1m" | "5m" | "1h"  (default "5m")

    Returns JSON with keys: window, count, tcr, avg_latency, p95_latency,
    error_rate, avg_tokens.  Returns empty dict when no evaluator is attached.
    """
    evaluator = getattr(request.app.state, "streaming_evaluator", None)
    if evaluator is None:
        return JSONResponse({"window": window, "available": False})

    allowed = {"1m", "5m", "1h"}
    if window not in allowed:
        window = "5m"

    try:
        stats: Dict[str, Any] = evaluator.get_stats(window)
        stats["window"] = window
        stats["available"] = True
        return JSONResponse(stats)
    except Exception:
        return JSONResponse({"window": window, "available": False})
