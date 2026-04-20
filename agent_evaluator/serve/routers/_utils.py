"""Shared helpers for serve router modules."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Request


def _rs(request: Request):
    """Return the shared ResultSet from app state."""
    return request.app.state.result_set


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
