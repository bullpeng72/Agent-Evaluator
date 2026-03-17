"""
SSE stream route.

GET /api/stream  — Server-Sent Events for file change notifications.
"""
from __future__ import annotations

import asyncio
import json as _json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

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
