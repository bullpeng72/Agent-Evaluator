"""
Golden Dataset routes.

GET  /api/golden                 — list golden dataset files
GET  /api/golden/{name}          — get content of a golden dataset
PUT  /api/golden/{name}          — save/update a golden dataset
POST /api/golden                 — create a new golden dataset
POST /api/golden/pdf             — extract text from PDF and return as golden QA pairs
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

router = APIRouter(prefix="/api/golden")

_GOLDEN_CANDIDATES = [
    "golden_datasets",
    "data/golden_datasets",
]


def _golden_dir(request: Request) -> Path:
    results_dir: Path = request.app.state.results_dir
    # 1. results_dir 안에 golden_datasets 서브디렉토리 (정규 위치)
    p = results_dir / "golden_datasets"
    if p.exists():
        return p
    # 2. results_dir 의 형제 디렉토리로 탐색 (레거시 위치 호환)
    for cand in _GOLDEN_CANDIDATES:
        p = results_dir.parent / cand
        if p.exists():
            return p
    # 3. 폴백: results_dir/golden_datasets 생성 (루트가 아닌 results 아래에)
    d = results_dir / "golden_datasets"
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


@router.post("/pdf")
async def extract_pdf(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Extract text from an uploaded PDF and return paragraph chunks as golden dataset items.

    Uses pdfplumber if available, falls back to PyPDF2, then raw byte extraction.
    Returns a list of {question, context} items suitable for Golden Dataset use.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    content = await file.read()

    # -- Extract text ----------------------------------------------------------
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(
                (page.extract_text() or "") for page in pdf.pages
            )
    except ImportError:
        pass

    if not text.strip():
        try:
            import pypdf as PyPDF2  # pypdf is the maintained successor of PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            text = "\n".join(
                (page.extract_text() or "") for page in reader.pages
            )
        except ImportError:
            pass

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "PDF에서 텍스트를 추출할 수 없습니다. "
                "pip install 'agent-evaluator[datasets]' 로 pdfplumber를 설치하세요."
            ),
        )

    # -- Split into meaningful paragraphs and generate QA pairs ----------------
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if len(p.strip()) > 80]
    items: List[Dict[str, Any]] = []
    for i, para in enumerate(paragraphs[:50], 1):  # cap at 50 items
        # Generate a simple question placeholder from the paragraph
        first_sentence = re.split(r"[.?!。]", para)[0].strip()
        question = f"Q{i}: {first_sentence[:120]}에 대해 설명하세요." if first_sentence else f"단락 {i}의 내용을 설명하세요."
        items.append({
            "id": f"pdf_item_{i:03d}",
            "question": question,
            "context": para,
            "expected_answer": "",
        })

    return {
        "ok": True,
        "filename": file.filename,
        "total_chars": len(text),
        "item_count": len(items),
        "items": items,
    }
