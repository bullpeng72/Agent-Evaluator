"""
Golden Dataset routes.

GET  /api/golden                 — list golden dataset files
GET  /api/golden/{name}          — get content of a golden dataset
PUT  /api/golden/{name}          — save/update a golden dataset
POST /api/golden                 — create a new golden dataset
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

router = APIRouter(prefix="/api/golden")

_GOLDEN_CANDIDATES = [
    "golden_datasets",
    "data/golden_datasets",
]


def _golden_dir(request: Request) -> Path:
    results_dir: Path = request.app.state.results_dir
    # 1. results_dir 안에 golden_datasets 서브디렉토리
    p = results_dir / "golden_datasets"
    if p.exists():
        return p
    # 2. results_dir 의 형제 디렉토리로 탐색 (project_root/golden_datasets)
    for cand in _GOLDEN_CANDIDATES:
        p = results_dir.parent / cand
        if p.exists():
            return p
    # 3. 폴백: project_root/golden_datasets 생성
    d = results_dir.parent / "golden_datasets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("")
def list_golden(request: Request) -> List[Dict[str, Any]]:
    gdir = _golden_dir(request)
    result = []
    for p in sorted(gdir.glob("*.json")):
        try:
            size = p.stat().st_size
            data = _read_json(p)
            count = len(data) if isinstance(data, list) else len(data.get("items", data.get("questions", [])))
        except Exception:
            size = 0
            count = 0
        result.append({"name": p.name, "stem": p.stem, "size_bytes": size, "count": count})
    return result


@router.get("/{name}")
def get_golden(name: str, request: Request) -> Any:
    gdir = _golden_dir(request)
    for p in [gdir / name, gdir / f"{name}.json"]:
        if p.exists():
            try:
                return _read_json(p)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Golden dataset not found")


@router.put("/{name}")
async def save_golden(name: str, request: Request) -> Dict[str, Any]:
    gdir = _golden_dir(request)
    fname = name if name.endswith(".json") else f"{name}.json"
    path = gdir / fname
    try:
        body = await request.json()
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": str(path), "name": fname}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_golden(request: Request) -> Dict[str, Any]:
    gdir = _golden_dir(request)
    try:
        body = await request.json()
        name = body.get("name", "golden_dataset")
        fname = name if name.endswith(".json") else f"{name}.json"
        items = body.get("items", [])
        path = gdir / fname
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "name": fname, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
