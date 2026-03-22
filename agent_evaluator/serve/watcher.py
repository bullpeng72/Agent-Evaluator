"""
File watcher — monitors results_dir for changes and notifies SSE clients.

Uses watchdog if available; falls back to polling.
"""
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class FileWatcher:
    """
    Watches a directory for JSON file changes.
    Broadcasts an event to all registered async queues on change.
    """

    def __init__(self, watch_dir: Path, poll_interval: float = 2.0):
        self._dir = watch_dir
        self._poll_interval = poll_interval
        # Store (loop, queue) pairs so _broadcast can use call_soon_threadsafe
        self._subscribers: List[Tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_snapshot: Dict[str, float] = {}

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
        """Register caller's asyncio queue. Must be called from an asyncio context."""
        loop = asyncio.get_event_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=32)
        with self._lock:
            self._subscribers.append((loop, q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [(l, s) for l, s in self._subscribers if s is not q]

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _snapshot(self) -> Dict[str, float]:
        result: Dict[str, float] = {}
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
        """Thread-safe broadcast using call_soon_threadsafe to put into asyncio queues."""
        with self._lock:
            dead = []
            for loop, q in self._subscribers:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, event)
                except RuntimeError:
                    # Loop is closed — mark subscriber for removal
                    dead.append(q)
            if dead:
                self._subscribers = [(l, s) for l, s in self._subscribers if s not in dead]
