"""
Configuration API — threshold settings persistence + env model config.

GET  /api/thresholds   — load saved thresholds (returns defaults if not saved)
POST /api/thresholds   — persist threshold settings to .thresholds.json
GET  /api/config       — return configured model names from environment (.env)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

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
    # Phase 2: Harness 그룹별 임계값 (0.0~1.0, 그룹 A~G + overall)
    harness_A: Optional[float] = None
    harness_B: Optional[float] = None
    harness_C: Optional[float] = None
    harness_D: Optional[float] = None
    harness_E: Optional[float] = None
    harness_F: Optional[float] = None
    harness_G: Optional[float] = None
    harness_overall: Optional[float] = None

_DEFAULTS: Dict[str, float] = {
    "tcr": 90.0,
    "acc": 70.0,
    "hall": 5.0,
    "p95": 2.0,
    "p99": 5.0,
    "cost": 0.01,
    # Phase 2: harness gates (0.0~1.0 범위, 이하면 warn/fail)
    "harness_A": 0.70,
    "harness_B": 0.70,
    "harness_C": 0.70,
    "harness_D": 0.70,
    "harness_E": 0.70,
    "harness_F": 0.70,
    "harness_G": 0.70,
    "harness_overall": 0.70,
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
        except Exception as _e:
            logger.debug("임계값 설정 파일 로드 실패, 기본값 사용 (무시): %s", _e)
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
