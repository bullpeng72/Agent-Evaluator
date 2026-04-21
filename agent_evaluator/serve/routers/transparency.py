"""
Transparency routes — Traces, Audit Logs, Annotations.

GET  /api/transparency/traces              list of trace files
GET  /api/transparency/traces/{name}       single trace file content
GET  /api/transparency/audit               list of audit log files
GET  /api/transparency/audit/{name}        single audit log content
GET  /api/transparency/annotations         list of annotation files
GET  /api/transparency/annotations/{name}  single annotation content
POST /api/transparency/annotations         create new annotation
POST /api/transparency/annotations/{name}/reply  add reply to annotation
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from agent_evaluator.serve.routers._utils import _read_json

router = APIRouter(prefix="/api/transparency", tags=["transparency"])


class AnnotationCreate(BaseModel):
    title: str
    content: str
    annotation_type: str = "note"   # note | warning | review | improvement | bug | question
    priority: str = "medium"        # low | medium | high | critical
    author: str = "dashboard"
    target_type: str = "evaluation"
    target_id: str = ""
    tags: List[str] = []
    source_file_id: str = ""        # evaluation file ID this annotation belongs to ("" = global)


class ReplyCreate(BaseModel):
    author: str = "dashboard"
    content: str


def _transparency(request: Request):
    return request.app.state.result_set.transparency


def _annotations_dir(request: Request) -> Path:
    """annotations/ 디렉토리 반환 — results_dir 기준 자동 탐지"""
    results_dir: Path = request.app.state.results_dir
    ann_dir = results_dir / "annotations"
    ann_dir.mkdir(parents=True, exist_ok=True)
    return ann_dir


def _reload_transparency(request: Request):
    """annotations 파일 목록 재스캔"""
    from agent_evaluator.serve.loader import _load_transparency
    request.app.state.result_set.transparency = _load_transparency(
        request.app.state.results_dir
    )


def _list_files(paths: List[Path]) -> List[Dict[str, Any]]:
    result = []
    for p in paths:
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        result.append({"name": p.name, "stem": p.stem, "size_bytes": size})
    return result


@router.get("/traces", summary="추적 목록")
def list_traces(request: Request):
    """OTEL 추적 파일 목록을 반환한다.

    ``PerformanceMonitor(enable_transparency=True)``로 평가 실행 시 생성되는
    ``traces/`` 디렉토리의 ``.json`` 파일 목록을 반환한다.
    각 항목은 ``name`` · ``stem`` · ``size_bytes`` 필드를 포함한다.
    """
    return _list_files(_transparency(request).trace_files)


@router.get("/traces/{name}", summary="추적 상세")
def get_trace(name: str, request: Request):
    """단일 추적 파일의 전체 내용을 JSON으로 반환한다.

    Args:
        name: 파일 이름(확장자 포함 또는 생략 가능). ``GET /api/transparency/traces`` 목록의 ``name`` 필드.
    """
    for p in _transparency(request).trace_files:
        if p.name == name or p.stem == name:
            try:
                return _read_json(p)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Trace not found")


@router.get("/audit", summary="감사 로그 목록")
def list_audit(request: Request):
    """감사 로그 파일 목록을 반환한다.

    ``PerformanceMonitor(enable_transparency=True)``로 평가 실행 시 생성되는
    ``audit_logs/`` 디렉토리의 ``.json`` 파일 목록을 반환한다.
    각 항목은 ``name`` · ``stem`` · ``size_bytes`` 필드를 포함한다.
    """
    return _list_files(_transparency(request).audit_files)


@router.get("/audit/{name}", summary="감사 로그 상세")
def get_audit(name: str, request: Request):
    """단일 감사 로그 파일의 전체 내용을 JSON으로 반환한다.

    Args:
        name: 파일 이름(확장자 포함 또는 생략 가능). ``GET /api/transparency/audit`` 목록의 ``name`` 필드.
    """
    for p in _transparency(request).audit_files:
        if p.name == name or p.stem == name:
            try:
                return _read_json(p)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Audit log not found")


@router.get("/annotations", summary="어노테이션 목록")
def list_annotations(request: Request, file_id: str = Query("")):
    """list annotations; if file_id given, only return annotations for that file or global ones."""
    files = _transparency(request).annotation_files
    if not file_id:
        return _list_files(files)
    result = []
    for p in files:
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        try:
            ann = _read_json(p)
            sfid = ann.get("source_file_id", "")
            if sfid and sfid != file_id:
                continue  # tagged to a different file — skip
        except Exception as _e:
            logger.debug("어노테이션 파일 읽기 실패, 포함 처리 (무시): %s", _e)
        result.append({"name": p.name, "stem": p.stem, "size_bytes": size})
    return result


@router.get("/annotations/{name}", summary="어노테이션 상세")
def get_annotation(name: str, request: Request):
    """단일 어노테이션 파일의 전체 내용을 JSON으로 반환한다.

    반환 객체는 ``annotation_id`` · ``title`` · ``content`` · ``annotation_type`` ·
    ``priority`` · ``author`` · ``timestamp`` · ``replies`` · ``tags`` · ``source_file_id`` 필드를 포함한다.

    Args:
        name: 파일 이름(확장자 포함 또는 생략 가능). ``GET /api/transparency/annotations`` 목록의 ``name`` 필드.
    """
    for p in _transparency(request).annotation_files:
        if p.name == name or p.stem == name:
            try:
                return _read_json(p)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Annotation not found")


@router.post("/annotations", summary="어노테이션 생성")
def create_annotation(body: AnnotationCreate, request: Request):
    """대시보드에서 새 어노테이션 직접 작성"""
    annotation_id = f"annotation_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    annotation = {
        "annotation_id":  annotation_id,
        "source_file_id": body.source_file_id,   # "" = global; non-empty = per-file
        "target_type":    body.target_type,
        "target_id":      body.target_id or annotation_id,
        "annotation_type": body.annotation_type,
        "priority":       body.priority,
        "title":          body.title,
        "content":        body.content,
        "author":         body.author,
        "timestamp":      now,
        "created_at":     now,
        "status":         "open",
        "replies":        [],
        "tags":           body.tags,
        "metadata":       {},
    }
    ann_dir = _annotations_dir(request)
    filepath = ann_dir / f"{annotation_id}.json"
    filepath.write_text(
        json.dumps(annotation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _reload_transparency(request)
    return annotation


@router.post("/annotations/{name}/reply", summary="어노테이션 댓글 추가")
def add_reply(name: str, body: ReplyCreate, request: Request):
    """기존 어노테이션에 답글 추가"""
    ann_dir = _annotations_dir(request)
    # 파일 탐색: transparency 목록 + 직접 경로
    candidates = list(_transparency(request).annotation_files) + list(ann_dir.glob("*.json"))
    filepath = None
    for p in candidates:
        if p.stem == name or p.name == name:
            filepath = p
            break
    if filepath is None or not filepath.exists():
        raise HTTPException(status_code=404, detail="Annotation not found")
    try:
        annotation = _read_json(filepath)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    reply = {
        "reply_id":   f"reply_{uuid.uuid4().hex[:8]}",
        "author":     body.author,
        "content":    body.content,
        "timestamp":  datetime.now().isoformat(),
        "created_at": datetime.now().isoformat(),
    }
    annotation.setdefault("replies", []).append(reply)
    filepath.write_text(
        json.dumps(annotation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _reload_transparency(request)
    return annotation
