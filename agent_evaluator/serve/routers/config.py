"""
Configuration API — threshold settings persistence + env model config.

GET  /api/thresholds   — load saved thresholds (returns defaults if not saved)
POST /api/thresholds   — persist threshold settings to .thresholds.json
GET  /api/config       — return configured model names from environment (.env)
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["config"])


class ThresholdBody(BaseModel):
    tcr: Optional[float] = None
    acc: Optional[float] = None
    hall: Optional[float] = None
    p95: Optional[float] = None
    p99: Optional[float] = None
    cost: Optional[float] = None

_DEFAULTS: Dict[str, float] = {
    "tcr": 90.0,
    "acc": 70.0,
    "hall": 5.0,
    "p95": 2.0,
    "p99": 5.0,
    "cost": 0.01,
}


def _threshold_path(request: Request):
    return request.app.state.results_dir / ".thresholds.json"


@router.get("/thresholds")
def get_thresholds(request: Request) -> Dict[str, Any]:
    """Load persisted thresholds; return defaults when no file exists."""
    p = _threshold_path(request)
    if p.exists():
        try:
            saved = json.loads(p.read_text(encoding="utf-8"))
            merged = _DEFAULTS.copy()
            merged.update({k: float(v) for k, v in saved.items() if k in _DEFAULTS})
            return merged
        except Exception:
            pass
    return _DEFAULTS.copy()


@router.get("/config")
def get_config() -> Dict[str, Any]:
    """Return configured model names from environment (.env)."""
    return {
        "openai_model": os.getenv("OPENAI_MODEL", ""),
        "anthropic_model": os.getenv("ANTHROPIC_MODEL", ""),
    }


@router.post("/thresholds")
async def save_thresholds(request: Request, body: ThresholdBody) -> Dict[str, Any]:
    """Persist threshold settings; unset fields keep their default values."""
    merged = _DEFAULTS.copy()
    for k in _DEFAULTS:
        v = getattr(body, k, None)
        if v is not None:
            try:
                merged[k] = float(v)
            except (TypeError, ValueError):
                pass
    p = _threshold_path(request)
    p.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged
