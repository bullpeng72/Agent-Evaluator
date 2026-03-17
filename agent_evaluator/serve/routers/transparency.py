"""
Transparency routes — Traces, Audit Logs, Annotations.

GET /api/transparency/traces            list of trace files
GET /api/transparency/traces/{name}     single trace file content
GET /api/transparency/audit             list of audit log files
GET /api/transparency/audit/{name}      single audit log content
GET /api/transparency/annotations       list of annotation files
GET /api/transparency/annotations/{name} single annotation content
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/transparency")


def _transparency(request: Request):
    return request.app.state.result_set.transparency


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _list_files(paths: List[Path]) -> List[Dict[str, Any]]:
    result = []
    for p in paths:
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        result.append({"name": p.name, "stem": p.stem, "size_bytes": size})
    return result


@router.get("/traces")
def list_traces(request: Request):
    return _list_files(_transparency(request).trace_files)


@router.get("/traces/{name}")
def get_trace(name: str, request: Request):
    for p in _transparency(request).trace_files:
        if p.name == name or p.stem == name:
            try:
                return _read_json(p)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Trace not found")


@router.get("/audit")
def list_audit(request: Request):
    return _list_files(_transparency(request).audit_files)


@router.get("/audit/{name}")
def get_audit(name: str, request: Request):
    for p in _transparency(request).audit_files:
        if p.name == name or p.stem == name:
            try:
                return _read_json(p)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Audit log not found")


@router.get("/annotations")
def list_annotations(request: Request):
    return _list_files(_transparency(request).annotation_files)


@router.get("/annotations/{name}")
def get_annotation(name: str, request: Request):
    for p in _transparency(request).annotation_files:
        if p.name == name or p.stem == name:
            try:
                return _read_json(p)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Annotation not found")
