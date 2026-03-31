"""
Golden Dataset routes.

GET  /api/golden                 — list golden dataset files
GET  /api/golden/{name}          — get content of a golden dataset
PUT  /api/golden/{name}          — save/update a golden dataset
POST /api/golden                 — create a new golden dataset
POST /api/golden/pdf             — extract text from PDF and return as golden QA pairs (simple)
POST /api/golden/pdf-advanced    — generate high-quality QA pairs via OpenAI LLM
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

router = APIRouter(prefix="/api/golden", tags=["golden datasets"])


class GoldenCreateBody(BaseModel):
    name: str = "golden_dataset"
    items: List[Any] = []

# ---------------------------------------------------------------------------
# PDF helpers (used by both /pdf and /pdf-advanced)
# ---------------------------------------------------------------------------

_BOILERPLATE_LINE_RE = re.compile(
    r"ISBN|copyright|all\s+rights\s+reserved|저작권|출판사|전자책\s*제작|"
    r"초판|쇄\s*발행|인쇄|판권|지은이|옮긴이|펴낸이|펴낸곳|발행인|편집인|"
    r"http[s]?://|www\.\S+|@\w+|"
    r"^\s*\d{1,4}\s*$",          # lone page numbers
    re.IGNORECASE,
)

# Tokens that are clearly not nouns — skip as question topics
_NON_NOUN_TOKENS = frozenset({
    # 접속부사
    "특히", "또한", "그러나", "하지만", "그래서", "따라서", "그리고", "그런데",
    "그러므로", "먼저", "우선", "마침내", "결국", "아직", "이미", "바로",
    "갑자기", "천천히", "다시", "그때", "이때", "모두", "항상",
    "반면", "한편", "이처럼", "이렇게", "어떻게", "왜냐하면",
    "하여", "또는", "혹은", "심지어", "오히려", "더욱", "더욱이",
    "결국에는", "마지막으로", "처음에는", "나중에는", "한편으로는",
    # 지시대명사/지시어 — 전 문장 없이 쓰면 의미 불완전
    "이를", "이것을", "이것은", "이것이", "이는", "이에", "이런", "이러한",
    "이와", "이로", "이로써", "이에따라", "이에따른", "이후", "이전",
    "그것을", "그것은", "그것이", "그런", "그러한", "그와", "그에따라",
    "해당", "본",  # "해당 내용은" / "본 문서는" → 의미없는 주어
    # 부사어/목적구 — 명사 아님
    "결과적으로", "위해서는", "위해서", "위하여", "통해서는", "통해서",
    "통하여", "따라서는", "관해서는", "관해서", "대해서는", "대해서",
    "위주로", "기반으로", "중심으로", "관련하여", "비교하여",
})


def _clean_text(raw: str) -> str:
    """Remove boilerplate lines, then normalise PDF line-break artifacts."""
    # 1. Drop boilerplate lines (publisher info, URLs, ISBN, page numbers)
    clean_lines = [
        ln for ln in raw.split("\n")
        if ln.strip() and not _BOILERPLATE_LINE_RE.search(ln.strip())
    ]
    text = "\n".join(clean_lines)

    # 2. Re-join lines broken mid-sentence (no Korean sentence-ending char before \n)
    text = re.sub(r"(?<![다요까냐지군\.!?])\n(?=[가-힣a-zA-Z(「『\"])", " ", text)

    # 3. Collapse excess whitespace / blank lines
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_passages(text: str, target_len: int = 400) -> List[str]:
    """Split cleaned text into word-based fixed-size passages of ~target_len chars.

    Uses word-boundary splitting instead of sentence-boundary regex, which is
    more robust for Korean ebooks where sentence-ending patterns may vary.
    """
    words = text.split()
    passages: List[str] = []
    i = 0
    while i < len(words):
        chunk_words: List[str] = []
        chunk_len = 0
        while i < len(words) and chunk_len < target_len:
            chunk_words.append(words[i])
            chunk_len += len(words[i]) + 1
            i += 1
        chunk = " ".join(chunk_words)
        if len(chunk) >= 100:
            passages.append(chunk)
    return passages


_DIALOGUE_START_RE = re.compile(r'^[\""「『\']')


def _extract_answer(passage: str) -> str:
    """Return the best sentence in the passage as the extractive answer.

    Prefers declarative sentences over dialogue lines.  Falls back to the
    longest available sentence, then to a passage substring.
    """
    sents = re.split(r"(?<=[다요까냐지군요\.!?])\s+", passage)
    sents = [s.strip() for s in sents if len(s.strip()) > 15]
    if not sents:
        return passage[:200]
    # Prefer non-dialogue sentences (don't start with a quotation mark)
    declarative = [s for s in sents if not _DIALOGUE_START_RE.match(s)]
    pool = declarative if declarative else sents
    return max(pool, key=len)


def _make_question(answer: str) -> str:
    """Generate a natural wh-question from an extractive answer sentence.

    Avoids cloze-style leakage: the answer text is never embedded in the
    question.  The leading topic is extracted via token-based particle stripping
    (more robust than regex character-class matching for Korean) and paired with
    an appropriate wh-frame.
    """

    def _iran(noun: str) -> str:
        """Return 이란 or 란 per Korean batchim rule."""
        if not noun:
            return "이란"
        last = noun[-1]
        if "가" <= last <= "힣":
            return "이란" if (ord(last) - ord("가")) % 28 != 0 else "란"
        return "이란"

    def _eun(noun: str) -> str:
        """Return 은 or 는 per Korean batchim rule (or English vowel-ending heuristic)."""
        if not noun:
            return "은"
        last = noun[-1]
        if "가" <= last <= "힣":
            return "은" if (ord(last) - ord("가")) % 28 != 0 else "는"
        # ASCII: letters that end with a vowel sound → 는
        if last in "AaEeIiOoUuYyWw":
            return "는"
        return "은"

    # Subject/topic-marking particles, longest first so compound particles match before singles
    _SUBJ_PARTICLES = (
        "에서는", "에게는", "으로는", "에서도", "에게도",  # locative compounds
        "이란", "란",                                       # definition markers
        "에서", "에게",                                     # locatives
        "의",                                              # possessive ("직장인의" → "직장인")
        "을", "를",                                        # accusative ("표현을" → "표현")
        "은", "는", "이", "가",                             # plain subject/topic
    )

    # Punctuation to strip from token edges before particle removal
    _PUNCT = str.maketrans("", "", '.,!?…·—–:;()[]「」『』""\'*·※')

    def _topic(text: str) -> str:
        """Extract leading noun phrase (1-2 words) by stripping subject particles.

        Works at token level so Korean particles attached to the noun are
        reliably removed without confusion with other syllables in the range.
        Skips leading adverbs/conjunctions and strips punctuation from tokens.
        """
        tokens = text.split()
        if not tokens:
            return text[:20]

        def _clean(token: str) -> str:
            return token.translate(_PUNCT).strip()

        def _strip(token: str):
            t = _clean(token)
            for p in _SUBJ_PARTICLES:
                if t.endswith(p) and len(t) > len(p) + 1:
                    return t[: -len(p)]
            return None  # no subject particle found

        # Suffixes that mark adjectives / verb-connective forms (not nouns)
        _BAD_SUFFIXES = (
            "한", "적인", "스러운", "다운", "같은", "로운", "스런",  # adjective forms
            "하거나", "거나", "하여", "하며", "하고", "되어", "되며",  # verb connectives
        )

        def _is_bad_token(token: str) -> bool:
            """True when token cannot serve as a meaningful question topic."""
            if len(token) <= 1:
                return True
            # Pure adjective / verb-connective suffix
            if any(token.endswith(s) and len(token) > len(s) + 1 for s in _BAD_SUFFIXES):
                return True
            # 2-char token ending in "은"/"는" → adjective/verb adnominal ("좋은", "하는")
            # NOTE: do NOT apply to "이"/"가" — they appear in valid nouns ("평가", "의미")
            if len(token) == 2 and token[-1] in ("은", "는"):
                return True
            return False

        # Skip leading adverbs / conjunctions / adjective-only tokens (up to first 4 tokens)
        start = 0
        for i, tok in enumerate(tokens[:4]):
            cleaned = _clean(tok)
            # A good starting token: not a known non-noun, not adjective/adverb form,
            # and at least 2 chars after cleaning
            if (cleaned
                    and cleaned not in _NON_NOUN_TOKENS
                    and not _is_bad_token(cleaned)
                    and len(cleaned) >= 2):
                start = i
                break
        else:
            # All first 4 tokens were bad — scan rest of passage for first noun-like token
            for i, tok in enumerate(tokens[4:], 4):
                cleaned = _clean(tok)
                stem = _strip(tok)
                candidate = stem if (stem and len(stem) >= 2) else cleaned
                if (candidate
                        and candidate not in _NON_NOUN_TOKENS
                        and not _is_bad_token(candidate)
                        and len(candidate) >= 2):
                    start = i
                    break

        tokens = tokens[start:]
        if not tokens:
            return text[:20]

        t0 = tokens[0]
        stem0 = _strip(t0)
        if stem0 and len(stem0) >= 2:
            return stem0  # "에이전트란" → "에이전트", "CrewAI는" → "CrewAI"

        # First token has no subject particle — second token may carry it
        # ("RAG 시스템은" → "RAG 시스템", "평가 지표는" → "평가 지표")
        if len(tokens) >= 2:
            stem1 = _strip(tokens[1])
            if stem1 and len(stem1) >= 2:
                return _clean(t0) + " " + stem1

        return _clean(t0) or text[:20]  # fallback: cleaned first token

    # ------------------------------------------------------------------
    # 1. Explicit definition marker "X이란/란 ..." — skip leading adverbs
    # ------------------------------------------------------------------
    for tok in (answer.split() or [""])[:4]:
        cleaned_tok = tok.translate(_PUNCT).strip()
        if cleaned_tok in _NON_NOUN_TOKENS or len(cleaned_tok) < 2:
            continue
        for suf in ("이란", "란"):
            if cleaned_tok.endswith(suf) and len(cleaned_tok) > len(suf) + 1:
                stem = cleaned_tok[: -len(suf)]
                return f"{stem}{_iran(stem)} 무엇인가요?"
        break  # first meaningful non-adverb token has no 이란/란 → stop

    # ------------------------------------------------------------------
    # 2. Cause / reason: "이유는", "원인은", "때문에", "왜냐하면"
    # ------------------------------------------------------------------
    if re.search(r"이유는|원인은|왜냐하면|때문이다|때문에", answer):
        subj = _topic(answer)
        if len(subj) >= 2:
            return f"{subj}의 원인은 무엇인가요?"

    # ------------------------------------------------------------------
    # 3a. Process with explicit object: "X을/를 Y하기 위해" / "X를 Y하는 방법"
    # ------------------------------------------------------------------
    m = re.search(
        r"([가-힣A-Za-z0-9]+)[을를]\s*([가-힣A-Za-z0-9]+)"
        r"하(?:려면|기\s*위해|는\s*(?:방법|과정|절차|단계))",
        answer,
    )
    if m:
        return f"{m.group(1)} {m.group(2)} 방법은 무엇인가요?"

    # ------------------------------------------------------------------
    # 3b. Process verb-only: "~하려면", "~하기 위해", "~하는 방법"
    # ------------------------------------------------------------------
    m = re.search(
        r"([가-힣A-Za-z0-9]+)하(?:려면|기\s*위해서?|는\s*(?:방법|과정|절차|단계))",
        answer,
    )
    if m:
        return f"{m.group(1)} 방법은 무엇인가요?"

    # ------------------------------------------------------------------
    # 4. Subject + predicate-type dispatch
    # ------------------------------------------------------------------
    subj = _topic(answer)
    if len(subj) >= 2:
        eun = _eun(subj)
        if re.search(r"증가|감소|변화|성장|발전|향상|저하", answer):
            return f"{subj}{eun} 어떻게 변화하고 있나요?"
        if re.search(r"사용|활용|적용|이용", answer):
            return f"{subj}{eun} 어떻게 활용되나요?"
        if re.search(r"구성|포함|이루어|구조", answer):
            return f"{subj}의 구성은 어떻게 되나요?"
        if re.search(r"중요|핵심|필요|역할|목적", answer):
            return f"{subj}의 역할은 무엇인가요?"
        if re.search(r"차이|비교|반면|구별", answer):
            return f"{subj}와 관련된 항목들의 차이점은 무엇인가요?"
        if re.search(r"이다|입니다|가리킨다|말한다", answer):
            return f"{subj}{_iran(subj)} 무엇인가요?"
        return f"{subj}에 대해 설명하시오."

    # ------------------------------------------------------------------
    # 5. English / mixed-content — leading capitalised term
    # ------------------------------------------------------------------
    m_en = re.search(r"\b([A-Z][a-zA-Z]{2,25}(?:\s[A-Z][a-zA-Z]{2,20})?)\b", answer)
    if m_en:
        term = m_en.group(1)
        iran = "란" if term[-1] in "AaEeIiOoUuYyWw" else "이란"
        return f"{term}{iran} 무엇인가요?"

    # ------------------------------------------------------------------
    # 6. Fallback
    # ------------------------------------------------------------------
    words = [w for w in answer.split() if len(w) >= 2]
    key = " ".join(words[:2]) if len(words) >= 2 else answer[:20]
    return f"'{key}'와 관련된 핵심 내용은 무엇인가요?"

def _golden_dir(request: Request) -> Path:
    results_dir: Path = request.app.state.results_dir
    # 1. 정규 위치: {project_root}/data/golden_datasets/
    p = results_dir.parent / "data" / "golden_datasets"
    if p.exists():
        return p
    # 2. 레거시 위치: results_dir 안의 golden_datasets 서브디렉토리
    p = results_dir / "golden_datasets"
    if p.exists():
        return p
    # 3. 폴백: data/golden_datasets 신규 생성
    d = results_dir.parent / "data" / "golden_datasets"
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


# ---------------------------------------------------------------------------
# 케이스 검토 API — GoldenSetBuilder 후보 파일 관리
# NOTE: /{name} 파라미터 라우트보다 반드시 먼저 등록해야 함 (FastAPI 순서 매칭)
# ---------------------------------------------------------------------------

@router.get("/candidates")
def list_candidates(request: Request) -> List[Dict[str, Any]]:
    """*candidates*.json 파일 목록 반환 (prefix 무관하게 탐색)."""
    gdir = _golden_dir(request)
    result = []
    for p in sorted(gdir.glob("*candidates*.json"), reverse=True):
        try:
            data = _read_json(p)
            cases = data if isinstance(data, list) else []
            pending = sum(1 for c in cases if c.get("_requires_review") and not c.get("_approved") and not c.get("_rejected"))
            approved = sum(1 for c in cases if c.get("_approved"))
            rejected = sum(1 for c in cases if c.get("_rejected"))
        except Exception:
            cases = []
            pending = approved = rejected = 0
        result.append({
            "name": p.name,
            "stem": p.stem,
            "total": len(cases),
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "mtime": p.stat().st_mtime,
        })
    return result


@router.get("/candidates/{name}")
def get_candidate_file(name: str, request: Request) -> List[Dict[str, Any]]:
    """후보 파일의 케이스 목록 반환 (인덱스 포함)."""
    gdir = _golden_dir(request)
    for p in [gdir / name, gdir / f"{name}.json"]:
        if p.exists():
            try:
                data = _read_json(p)
                cases = data if isinstance(data, list) else []
                return [{"_idx": i, **c} for i, c in enumerate(cases)]
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Candidate file not found")


@router.post("/candidates/{name}/approve/{idx}")
def approve_case(name: str, idx: int, request: Request) -> Dict[str, Any]:
    """단일 케이스 승인 — _approved=True 플래그 설정."""
    gdir = _golden_dir(request)
    for p in [gdir / name, gdir / f"{name}.json"]:
        if p.exists():
            try:
                data = _read_json(p)
                cases = data if isinstance(data, list) else []
                if idx < 0 or idx >= len(cases):
                    raise HTTPException(status_code=400, detail=f"Index {idx} out of range")
                cases[idx]["_approved"] = True
                cases[idx]["_rejected"] = False
                p.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
                return {"ok": True, "idx": idx, "action": "approved"}
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Candidate file not found")


@router.post("/candidates/{name}/reject/{idx}")
def reject_case(name: str, idx: int, request: Request) -> Dict[str, Any]:
    """단일 케이스 거부 — _rejected=True 플래그 설정."""
    gdir = _golden_dir(request)
    for p in [gdir / name, gdir / f"{name}.json"]:
        if p.exists():
            try:
                data = _read_json(p)
                cases = data if isinstance(data, list) else []
                if idx < 0 or idx >= len(cases):
                    raise HTTPException(status_code=400, detail=f"Index {idx} out of range")
                cases[idx]["_rejected"] = True
                cases[idx]["_approved"] = False
                p.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
                return {"ok": True, "idx": idx, "action": "rejected"}
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Candidate file not found")


@router.post("/candidates/{name}/merge")
def merge_approved(name: str, request: Request) -> Dict[str, Any]:
    """승인된 케이스를 골든셋에 병합 — 새 golden_*.json 파일 생성."""
    gdir = _golden_dir(request)
    for p in [gdir / name, gdir / f"{name}.json"]:
        if p.exists():
            try:
                data = _read_json(p)
                cases = data if isinstance(data, list) else []
                approved = [c for c in cases if c.get("_approved")]
                if not approved:
                    raise HTTPException(status_code=400, detail="No approved cases to merge")
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_name = f"golden_{ts}.json"
                out_path = gdir / out_name
                # 내부 메타 플래그 제거 후 저장
                clean = [{k: v for k, v in c.items() if not k.startswith("_")} for c in approved]
                out_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
                return {"ok": True, "merged": len(clean), "filename": out_name}
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Candidate file not found")


# ---------------------------------------------------------------------------
# 골든 데이터셋 CRUD — /{name} 파라미터 라우트는 고정 경로보다 반드시 뒤에 등록
# ---------------------------------------------------------------------------

@router.get("/versions")
def list_versions(request: Request) -> List[Dict[str, Any]]:
    """golden_*.json 파일 버전 목록 (candidates 제외)."""
    gdir = _golden_dir(request)
    result = []
    for p in sorted(gdir.glob("golden_*.json"), reverse=True):
        try:
            data = _read_json(p)
            count = len(data) if isinstance(data, list) else 0
        except Exception:
            count = 0
        result.append({
            "name": p.name,
            "stem": p.stem,
            "count": count,
            "mtime": p.stat().st_mtime,
            "size_bytes": p.stat().st_size,
        })
    return result


@router.post("")
async def create_golden(request: Request, body: GoldenCreateBody) -> Dict[str, Any]:
    gdir = _golden_dir(request)
    try:
        fname = body.name if body.name.endswith(".json") else f"{body.name}.json"
        path = gdir / fname
        path.write_text(json.dumps(body.items, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "name": fname, "count": len(body.items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
async def save_golden(
    name: str,
    request: Request,
    body: Any = Body(..., description="골든 데이터셋 전체 내용 (list 또는 dict)"),
) -> Dict[str, Any]:
    gdir = _golden_dir(request)
    fname = name if name.endswith(".json") else f"{name}.json"
    path = gdir / fname
    try:
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": str(path), "name": fname}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{name}")
def delete_golden(name: str, request: Request) -> Dict[str, Any]:
    gdir = _golden_dir(request)
    for p in [gdir / name, gdir / f"{name}.json"]:
        if p.exists():
            p.unlink()
            return {"ok": True, "name": name}
    raise HTTPException(status_code=404, detail="Golden dataset not found")


@router.post("/pdf")
async def extract_pdf(
    file: UploadFile = File(...),
    num_items: int = Form(default=10),
) -> Dict[str, Any]:
    """Extract text from a PDF and return evenly-sampled QA pairs.

    Improvements over the naive paragraph split:
    - Normalises PDF line-break artifacts before splitting
    - Splits on sentence boundaries (works with e-books that use single newlines)
    - Filters out boilerplate (copyright, ISBN, URLs, lone page numbers)
    - Samples passages uniformly across the **whole** document
    - Auto-extracts ground-truth answers (longest sentence per passage)
    - Accepts num_items to control how many QA pairs are returned
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    content = await file.read()

    text = ""
    try:
        import pdfplumber
        # pdfminer (pdfplumber 내부)의 폰트 디스크립터 경고는 무해하지만 터미널을 오염시키므로 억제
        _pdfminer_loggers = [
            logging.getLogger(n) for n in ("pdfminer", "pdfminer.pdffont", "pdfminer.pdfpage",
                                           "pdfminer.converter", "pdfminer.cmapdb")
        ]
        _prev_levels = [lg.level for lg in _pdfminer_loggers]
        for lg in _pdfminer_loggers:
            lg.setLevel(logging.ERROR)
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        finally:
            for lg, lv in zip(_pdfminer_loggers, _prev_levels):
                lg.setLevel(lv)
    except ImportError:
        pass

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "PDF에서 텍스트를 추출할 수 없습니다. "
                "pip install 'agent-evaluator[all]' 로 pdfplumber를 설치하세요."
            ),
        )

    text = _clean_text(text)

    def _is_factual(passage: str) -> bool:
        """Return True when the passage is likely factual rather than noise/boilerplate.

        Filters:
        - Passages dominated by quoted speech (literary dialogue)
        - TOC pages: many leader-dot sequences (……… or ........)
        - Passages with no Korean sentence-ending verb
        - Passages with no Korean characters at all (pure ASCII/numbers)
        """
        plen = max(len(passage), 1)

        # 1. Too many quotation marks → dialogue-heavy
        quote_chars = sum(1 for c in passage if c in '""「」『』\'"')
        if quote_chars / plen > 0.30:
            return False

        # 2. TOC / table of contents: dot-leader sequences (e.g. "목차....4")
        dot_count = len(re.findall(r'\.{3,}|…{2,}', passage))
        if dot_count >= 2:
            return False

        # 3. Must contain Korean characters
        if not re.search(r'[가-힣]', passage):
            return False

        # 4. Must contain at least one declarative sentence ending
        if not re.search(r'[다요까냐지군요]', passage):
            return False

        return True

    # Build fixed-size word-based passages (boilerplate already stripped by _clean_text)
    all_passages = [p for p in _split_passages(text) if len(p) >= 100 and _is_factual(p)]

    if not all_passages:
        raise HTTPException(
            status_code=422,
            detail="PDF에서 유효한 텍스트 단락을 추출할 수 없습니다. 텍스트 기반 PDF인지 확인하세요.",
        )

    # Uniform sampling across the entire document
    n = min(max(num_items, 1), len(all_passages))
    if len(all_passages) <= n:
        selected = all_passages
    else:
        step = len(all_passages) / n
        selected = [all_passages[int(i * step)] for i in range(n)]

    items: List[Dict[str, Any]] = []
    for i, passage in enumerate(selected, 1):
        answer = _extract_answer(passage)
        items.append({
            "id": f"pdf_item_{i:03d}",
            "question": _make_question(answer),
            "context": passage,
            "expected_answer": answer,
            "ground_truth": answer,
        })

    return {
        "ok": True,
        "filename": file.filename,
        "total_chars": len(text),
        "item_count": len(items),
        "items": items,
    }


@router.post("/pdf-advanced")
async def generate_pdf_qa_advanced(
    file: UploadFile = File(...),
    openai_api_key: str = Form(default=""),
    model: str = Form(default="gpt-4o-mini"),
    num_questions: int = Form(default=3),
    max_chunks: int = Form(default=10),
    question_types: str = Form(default="factual,reasoning,summary"),
) -> Dict[str, Any]:
    """Generate high-quality Korean QA pairs from a PDF using OpenAI LLM.

    Uses KoreanRAGDatasetGenerator: PDF → text chunking → GPT QA generation.
    Returns items in the same format as /api/golden/pdf so the UI can reuse
    the same save flow.

    Args:
        file: PDF file upload
        openai_api_key: OpenAI API key (falls back to OPENAI_API_KEY env var)
        model: OpenAI model name (gpt-4o-mini, gpt-4o, etc.)
        num_questions: questions to generate per text chunk (1–5)
        max_chunks: maximum number of chunks to process (limits runtime)
        question_types: comma-separated types — factual, reasoning, summary
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    api_key = openai_api_key.strip() or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=422,
            detail=(
                "OpenAI API 키가 필요합니다. "
                "폼에 직접 입력하거나 OPENAI_API_KEY 환경변수를 설정하세요."
            ),
        )

    content = await file.read()
    original_name = file.filename
    qtypes: Optional[List[str]] = [q.strip() for q in question_types.split(",") if q.strip()] or None

    def _generate():
        try:
            from agent_evaluator.datasets.korean_rag_dataset_generator import (
                KoreanRAGDatasetGenerator,
            )
        except ImportError as exc:
            raise RuntimeError(f"datasets 모듈을 불러올 수 없습니다: {exc}")

        tmp_dir = tempfile.mkdtemp(prefix="agent_eval_pdf_")
        try:
            pdf_path = os.path.join(tmp_dir, "input.pdf")
            with open(pdf_path, "wb") as fh:
                fh.write(content)

            generator = KoreanRAGDatasetGenerator(
                api_key=api_key,
                model=model,
                output_dir=tmp_dir,
            )
            return generator.generate_from_pdf(
                pdf_path=pdf_path,
                num_questions_per_chunk=num_questions,
                question_types=qtypes,
                max_chunks=max_chunks,
                save_format="json",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    try:
        dataset = await run_in_threadpool(_generate)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"QA 생성 실패: {exc}")

    items = [
        {
            "id": qa.qa_id,
            "question": qa.question,
            "context": qa.context,
            "expected_answer": qa.ground_truth,
            "ground_truth": qa.ground_truth,
        }
        for qa in dataset.qa_pairs
    ]

    return {
        "ok": True,
        "filename": original_name,
        "total_chars": sum(len(qa.context) for qa in dataset.qa_pairs),
        "item_count": len(items),
        "items": items,
        "model": model,
        "dataset_id": dataset.dataset_id,
    }
