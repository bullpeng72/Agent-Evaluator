"""
File watcher — monitors results_dir for changes and notifies SSE clients.

Uses watchdog if available; falls back to polling.
"""
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import List


class FileWatcher:
    """
    Watches a directory for JSON file changes.
    Broadcasts an event to all registered async queues on change.
    """

    def __init__(self, watch_dir: Path, poll_interval: float = 2.0):
        self._dir = watch_dir
        self._poll_interval = poll_interval
        self._subscribers: List[asyncio.Queue] = []
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_snapshot: dict[str, float] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._running = True
        self._last_snapshot = self._snapshot()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=32)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [s for s in self._subscribers if s is not q]

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _snapshot(self) -> dict[str, float]:
        result: dict[str, float] = {}
        if not self._dir.exists():
            return result
        for p in self._dir.rglob("*.json"):
            try:
                result[str(p)] = p.stat().st_mtime
            except OSError:
                pass
        return result

    def _loop(self) -> None:
        while self._running:
            time.sleep(self._poll_interval)
            current = self._snapshot()
            if current != self._last_snapshot:
                self._last_snapshot = current
                self._broadcast("update")

    def _broadcast(self, event: str) -> None:
        with self._lock:
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)
