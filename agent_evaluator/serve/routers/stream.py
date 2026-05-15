"""
SSE stream route.

GET /api/stream                      — Server-Sent Events for file change notifications.
GET /api/stream/live-stats           — Current StreamingEvaluator window stats (JSON).
GET /api/stream/tasks/{file_id}      — SSE: real-time task_added events for a result file.
"""
from __future__ import annotations

import asyncio
import json as _json
from typing import Any, Dict, Set, Optional

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/api", tags=["streaming"])

# WebSocket 연결 관리
_WS_CONNECTIONS: Set[WebSocket] = set()
_ws_lock = asyncio.Lock()


@router.get("/stream", summary="Evaluation event stream (SSE)")
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


@router.get("/stream/live-stats", summary="Live aggregate stats snapshot")
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


@router.get("/stream/snapshot/{file_id}", summary="File snapshot")
async def file_snapshot(request: Request, file_id: str, window: str = "5m") -> JSONResponse:
    """
    Return saved streaming snapshot from a result file (offline fallback).

    Returns the ``streaming_data`` snapshot stored in the file.
    Used as history data for the dashboard live tab when no real-time StreamingEvaluator is running.

    Query params:
        window: "1m" | "5m" | "1h"  (default "5m")
    """
    rs = getattr(request.app.state, "result_set", None)
    if rs is None:
        return JSONResponse({"window": window, "available": False, "source": "none"})

    rf = rs.by_id(file_id)
    if rf is None:
        return JSONResponse({"window": window, "available": False, "source": "not_found"})

    sd = getattr(rf, "streaming_data", {})
    if not sd:
        return JSONResponse({"window": window, "available": False, "source": "no_snapshot"})

    allowed = {"1m", "5m", "1h"}
    if window not in allowed:
        window = "5m"

    window_data = sd.get(window, {})
    if not window_data:
        # 요청한 윈도우 없으면 첫 번째 사용 가능한 윈도우 반환
        for w in ("1h", "5m", "1m"):
            if sd.get(w):
                window_data = sd[w]
                window = w
                break

    return JSONResponse({
        **window_data,
        "window": window,
        "available": True,
        "source": "file_snapshot",
        "all_windows": sd,
    })


@router.get("/stream/tasks/{file_id}", summary="Real-time task stream (SSE)")
async def task_stream(request: Request, file_id: str, poll_interval: float = 1.0):
    """
    Server-Sent Events: real-time task_added stream for a result file.

    Emits:
        data: {"type": "init",      "tasks": [...], "count": N}   — initial snapshot on connect
        data: {"type": "task_added","tasks": [...], "count": N}   — newly added tasks
        data: {"type": "ping"}                                     — keep-alive every 15 s

    Query params:
        poll_interval: polling interval in seconds (default 1.0, min 0.5, max 10.0)

    Client example (JavaScript)::

        const es = new EventSource('/api/stream/tasks/my_file_id');
        es.onmessage = e => {
            const { type, tasks } = JSON.parse(e.data);
            if (type === 'task_added') renderNewTasks(tasks);
        };
    """
    rs = getattr(request.app.state, "result_set", None)
    poll_interval = max(0.5, min(10.0, poll_interval))

    def _get_tasks(rf) -> list:
        return [
            {
                "task_id":          t.task_id,
                "task_type":        t.task_type,
                "success":          t.success,
                "accuracy_score":   round(t.accuracy_score, 4),
                "execution_time":   t.execution_time,
                "tokens_used":      t.tokens_used,
                "timestamp":        t.timestamp,
                "framework":        t.framework,
                "question":         (t.raw or {}).get("question") or (t.raw or {}).get("input"),
                "response":         (t.raw or {}).get("response") or (t.raw or {}).get("output"),
            }
            for t in rf.tasks
        ]

    async def _generator():
        seen_ids: Set[str] = set()

        # Initial snapshot
        if rs is not None:
            rf = rs.by_id(file_id)
            if rf is not None:
                tasks = _get_tasks(rf)
                seen_ids = {t["task_id"] for t in tasks}
                payload = _json.dumps({"type": "init", "tasks": tasks, "count": len(tasks)})
                yield f"data: {payload}\n\n"
            else:
                yield f"data: {_json.dumps({'type': 'init', 'tasks': [], 'count': 0})}\n\n"
        else:
            yield f"data: {_json.dumps({'type': 'disabled'})}\n\n"
            return

        last_ping = asyncio.get_event_loop().time()

        while True:
            if await request.is_disconnected():
                break

            await asyncio.sleep(poll_interval)

            # Check for new tasks
            try:
                # Re-read result set — reload if possible
                _rs = getattr(request.app.state, "result_set", None)
                if _rs is not None:
                    rf = _rs.by_id(file_id)
                    if rf is not None:
                        new_tasks = [t for t in _get_tasks(rf) if t["task_id"] not in seen_ids]
                        if new_tasks:
                            seen_ids.update(t["task_id"] for t in new_tasks)
                            payload = _json.dumps({
                                "type": "task_added",
                                "tasks": new_tasks,
                                "count": len(seen_ids),
                            })
                            yield f"data: {payload}\n\n"
            except Exception:
                pass

            # Keep-alive ping every 15s
            now = asyncio.get_event_loop().time()
            if now - last_ping >= 15.0:
                yield "data: {\"type\":\"ping\"}\n\n"
                last_ping = now

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/stream/filtered/{file_id}", summary="Filtered task stream (SSE)")
async def stream_filtered_tasks(
    file_id: str,
    request: Request,
    query: str = Query(default="", description="Filter expression (e.g. accuracy_score<0.5, task_type=qa)"),
    poll_interval: float = Query(default=2.0, ge=0.5, le=30.0),
):
    """Stream only newly-added tasks that match the filter condition via SSE.

    Query format: ``field<value`` / ``field>value`` / ``field=value`` / ``field<=value`` / ``field>=value``

    Emits::

        data: {"type": "init",       "tasks": [...], "count": N}
        data: {"type": "task_added", "task_id": ..., "accuracy_score": ..., "task_type": ...}
        data: {"type": "ping"}
    """
    import re as _re

    # --- 쿼리 파싱 ---
    _COND_RE = _re.compile(r"^([a-z_]+)\s*(<=|>=|<|>|=)\s*(.+)$")

    def _parse_query(q: str):
        m = _COND_RE.match(q.strip())
        if not m:
            return None
        field, op, raw_val = m.group(1), m.group(2), m.group(3).strip()
        if op == "=":
            op = "eq"
        elif op == "<":
            op = "lt"
        elif op == ">":
            op = "gt"
        elif op == "<=":
            op = "lte"
        elif op == ">=":
            op = "gte"
        try:
            val: Any = float(raw_val)
        except ValueError:
            val = raw_val
        return field, op, val

    condition = _parse_query(query) if query.strip() else None

    def _task_matches(t) -> bool:
        if condition is None:
            return True
        field, op, val = condition
        tv = getattr(t, field, None)
        if tv is None:
            return False
        try:
            if op == "eq":
                return str(tv).lower() == str(val).lower() if isinstance(val, str) else float(tv) == float(val)
            elif op == "lt":
                return float(tv) < float(val)
            elif op == "gt":
                return float(tv) > float(val)
            elif op == "lte":
                return float(tv) <= float(val)
            elif op == "gte":
                return float(tv) >= float(val)
        except (TypeError, ValueError):
            pass
        return False

    def _task_to_dict(t) -> Dict[str, Any]:
        return {
            "task_id":        t.task_id,
            "task_type":      t.task_type,
            "accuracy_score": round(t.accuracy_score, 4),
            "execution_time": t.execution_time,
            "success":        t.success,
            "timestamp":      t.timestamp,
            "framework":      t.framework,
        }

    rs = getattr(request.app.state, "result_set", None)

    async def _generator():
        seen_ids: Set[str] = set()

        # Initial snapshot
        if rs is not None:
            rf = rs.by_id(file_id)
            if rf is not None:
                matched = [_task_to_dict(t) for t in rf.tasks if _task_matches(t)]
                seen_ids = {t.task_id for t in rf.tasks}  # track all, emit only matching
                payload = _json.dumps({"type": "init", "tasks": matched, "count": len(matched)})
                yield f"data: {payload}\n\n"
            else:
                yield f"data: {_json.dumps({'type': 'init', 'tasks': [], 'count': 0})}\n\n"
        else:
            yield f"data: {_json.dumps({'type': 'disabled'})}\n\n"
            return

        last_ping = asyncio.get_event_loop().time()

        while True:
            if await request.is_disconnected():
                break

            await asyncio.sleep(poll_interval)

            try:
                _rs = getattr(request.app.state, "result_set", None)
                if _rs is not None:
                    rf = _rs.by_id(file_id)
                    if rf is not None:
                        for t in rf.tasks:
                            if t.task_id not in seen_ids:
                                seen_ids.add(t.task_id)
                                if _task_matches(t):
                                    payload = _json.dumps({
                                        "type": "task_added",
                                        **_task_to_dict(t),
                                    })
                                    yield f"data: {payload}\n\n"
            except Exception:
                pass

            now = asyncio.get_event_loop().time()
            if now - last_ping >= 15.0:
                yield "data: {\"type\":\"ping\"}\n\n"
                last_ping = now

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ws/events", name="WebSocket real-time event stream")
async def websocket_events(websocket: WebSocket):
    """WebSocket real-time event stream.

    Sends the current file list immediately upon connection,
    then pushes task_added events in real time.

    Message types::

        {"type": "init",         "files": [...], "count": N}   — initial snapshot on connect
        {"type": "task_added",   "file_id": ..., "task": {...}} — new task added
        {"type": "ping"}                                        — keep-alive (15s)

    Client example (JavaScript)::

        const ws = new WebSocket('ws://localhost:8765/api/ws/events');
        ws.onmessage = e => {
            const msg = JSON.parse(e.data);
            if (msg.type === 'task_added') renderTask(msg.task);
        };
    """
    await websocket.accept()
    async with _ws_lock:
        _WS_CONNECTIONS.add(websocket)

    try:
        rs = getattr(websocket.app.state, "result_set", None)
        # Initial snapshot
        files_meta = []
        seen_tasks: Dict[str, Set[str]] = {}
        if rs is not None:
            for f in rs.files:
                files_meta.append({"file_id": f.file_id, "name": f.name,
                                    "total_tasks": f.total_tasks, "tcr": round(f.tcr, 2)})
                seen_tasks[f.file_id] = {t.task_id for t in f.tasks}
        await websocket.send_json({"type": "init", "files": files_meta, "count": len(files_meta)})

        last_ping = asyncio.get_event_loop().time()

        while True:
            # poll for incoming messages with short timeout
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                if msg == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

            # Poll for new tasks
            if rs is not None:
                for f in rs.files:
                    current_ids = {t.task_id for t in f.tasks}
                    prev_ids = seen_tasks.get(f.file_id, set())
                    new_ids = current_ids - prev_ids
                    if new_ids:
                        seen_tasks[f.file_id] = current_ids
                        for t in f.tasks:
                            if t.task_id in new_ids:
                                try:
                                    await websocket.send_json({
                                        "type": "task_added",
                                        "file_id": f.file_id,
                                        "task": {
                                            "task_id":      t.task_id,
                                            "task_type":    t.task_type,
                                            "success":      t.success,
                                            "accuracy_score": round(t.accuracy_score, 4),
                                            "execution_time": t.execution_time,
                                            "timestamp":    t.timestamp,
                                        },
                                    })
                                except Exception:
                                    break

            # Keep-alive ping
            now = asyncio.get_event_loop().time()
            if now - last_ping >= 15.0:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                last_ping = now

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with _ws_lock:
            _WS_CONNECTIONS.discard(websocket)
