#!/usr/bin/env python3
"""
Book markdown → 개별 PDF 변환기  (Playwright/Chromium 기반)

각 .md 파일을 독립 PDF로 변환해 pdf/ 디렉토리에 저장한다.
디렉토리 구조를 그대로 유지한다:
  Media/Book/Part_I_기초/Chapter_01_*.md
  → Media/Book/pdf/Part_I_기초/Chapter_01_*.pdf

의존성 설치:
  pip install playwright markdown
  python -m playwright install chromium

특징:
- Mermaid 다이어그램을 Chromium 렌더링 후 PDF로 저장 (JS 실행 완료 후 캡처)
- 한국어 폰트: Google Fonts (Noto Sans/Serif KR) CDN 사용
- A4 · 여백 20mm · 짝수/홀수 머릿글 · 쪽 번호 자동
- build_book.py 의 inject_mermaid / md_to_html 함수 자동 재사용
"""

from __future__ import annotations

import asyncio
import importlib.util
import platform
import re
import sys
import time
import unicodedata
from pathlib import Path

# ── 의존성 확인 ────────────────────────────────────────────────────────────────

def _require(module: str, install: str) -> None:
    if importlib.util.find_spec(module) is None:
        os_name = platform.system()
        print(f"❌ '{module}' 패키지 없음. 설치: pip install {install}")

        if module == "playwright":
            print("\n브라우저 엔진 설치 필수:")
            print("  python -m playwright install chromium")
            if os_name == "Linux":
                print("  sudo python -m playwright install-deps chromium")
        
        if os_name == "Darwin":
            print("  brew install pandoc pango")
        elif os_name == "Linux":
            print("  sudo apt install pandoc libpango-1.0-0")

        sys.exit(1)

_require("playwright", "playwright")
_require("markdown", "markdown")

import markdown as md_lib
from playwright.async_api import async_playwright

# ── 경로 ────────────────────────────────────────────────────────────────────────

BOOK_DIR = Path(__file__).parent
PDF_DIR  = BOOK_DIR / "pdf"


def robust_path(fpath: Path) -> Path:
    """NFC/NFD 정규화 차이로 인한 파일 미인식 문제 해결."""
    if fpath.exists():
        return fpath
    try:
        rel_parts = fpath.relative_to(BOOK_DIR).parts
    except ValueError:
        return fpath
    current = BOOK_DIR
    for part in rel_parts:
        nfc_part = unicodedata.normalize("NFC", part)
        found = False
        if not current.exists(): break
        for entry in current.iterdir():
            if unicodedata.normalize("NFC", entry.name) == nfc_part:
                current = entry
                found = True
                break
        if not found: current = current / part
    return current


EXCLUDE_STEMS = {"README", "IMAGES"}  # 빌드 보조 파일 — PDF 변환 대상 제외

# ── 책 순서 정렬 ──────────────────────────────────────────────────────────────────

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
          "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}


def _book_sort_key(path: Path) -> tuple:
    """서문 → Part_I … Part_VI → Appendix 순으로 정렬하는 키.

    디렉토리 구조:
      00_서문.md              → (0, '00_서문.md')
      Part_I_기초/…          → (1, …)
      Part_VI_실전이식가이드/… → (6, …)
      Appendix/…             → (100, …)
      기타                    → (50, …)
    """
    rel_parts = path.relative_to(BOOK_DIR).parts
    top = rel_parts[0]

    if len(rel_parts) == 1:
        return (0, top)

    m = re.match(r"Part_([IVX]+)_", top)
    if m:
        part_num = _ROMAN.get(m.group(1), 99)
        return (part_num, *rel_parts[1:])

    if top.lower().startswith("appendix"):
        return (100, *rel_parts[1:])

    return (50, top, *rel_parts[1:])

# ── build_book.py 에서 inject_mermaid / MERMAID_INJECTIONS 재사용 ────────────────

def _load_build_book() -> tuple[dict, object]:
    """build_book.py 모듈을 동적으로 로드하여 MERMAID_INJECTIONS 와 md_to_html 반환."""
    spec = importlib.util.spec_from_file_location("build_book", BOOK_DIR / "build_book.py")
    if spec is None or spec.loader is None:
        return {}, None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return getattr(mod, "MERMAID_INJECTIONS", {}), mod
    except Exception as e:
        print(f"  ⚠️  build_book.py 로드 실패 ({e}), 내장 변환기 사용")
        return {}, None


MERMAID_INJECTIONS, _BUILD_MOD = _load_build_book()

# ── build_book.py HTML_HEAD 에서 CSS 추출 ─────────────────────────────────────
def _extract_book_css(mod) -> str:
    """HTML_HEAD 안의 <style>...</style> 블록을 추출해 반환."""
    if mod is None:
        return ""
    html_head = getattr(mod, "HTML_HEAD", "")
    m = re.search(r"<style>(.*?)</style>", html_head, re.DOTALL)
    return m.group(1) if m else ""

BOOK_CSS = _extract_book_css(_BUILD_MOD)


def inject_mermaid(stem: str, text: str) -> str:
    stem = unicodedata.normalize("NFC", stem)
    if _BUILD_MOD and hasattr(_BUILD_MOD, "inject_mermaid"):
        return _BUILD_MOD.inject_mermaid(stem, text)
    # fallback: 직접 구현
    items = MERMAID_INJECTIONS.get(stem, [])
    for anchor, block in items:
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + block, 1)
    return text


def md_to_html(text: str) -> str:
    if _BUILD_MOD and hasattr(_BUILD_MOD, "md_to_html"):
        return _BUILD_MOD.md_to_html(text)
    # fallback: 단순 변환 (mermaid는 div.mermaid 로 래핑)
    saved: list[tuple[str, str]] = []

    def ext_html(m: re.Match) -> str:
        saved.append(("html", m.group(1).strip()))
        return f"@@B{len(saved)-1}@@"

    text = re.sub(r"@@HTML_START@@\s*\n(.*?)@@HTML_END@@", ext_html, text, flags=re.DOTALL)

    def ext_mermaid(m: re.Match) -> str:
        saved.append(("mermaid", m.group(1)))
        return f"@@B{len(saved)-1}@@"

    text = re.sub(r"```mermaid\s*\n(.*?)```", ext_mermaid, text, flags=re.DOTALL)

    conv = md_lib.Markdown(
        extensions=["fenced_code", "tables", "toc", "attr_list", "def_list", "nl2br", "sane_lists"],
        extension_configs={"toc": {"permalink": False}},
    )
    html = conv.convert(text)

    def restore(m: re.Match) -> str:
        idx = int(m.group(1))
        kind, content = saved[idx]
        return f'<div class="mermaid">{content}</div>' if kind == "mermaid" else content

    return re.sub(r"@@B(\d+)@@", restore, html)


# ── HTML 래퍼 ────────────────────────────────────────────────────────────────────

# PDF 레이아웃 오버라이드 CSS (사이드바 제거 + 본문 너비 조정 + overflow 처리)
_PDF_OVERRIDE_CSS = """
/* ── PDF 레이아웃 오버라이드 ── */
#sidebar { display: none !important; }
#main {
  margin-left: 0 !important;
  width: 100% !important;
  padding: 0 24px 0 !important;
}
body {
  display: block !important;
  max-width: 100% !important;
  margin: 0 !important;
  width: 100% !important;
}

/* ── 테이블: 셀 줄바꿈 허용 + 기본 축소 방어 ── */
table {
  width: 100% !important;
  table-layout: auto !important;
  font-size: 8.5pt !important;
  word-break: break-word !important;
}
th, td {
  word-break: break-word !important;
  overflow-wrap: break-word !important;
  white-space: normal !important;
  hyphens: auto;
}
/* JS 스케일러가 .table-scale-wrap 으로 감싼 경우 */
.table-scale-wrap {
  overflow: hidden;
  width: 100%;
}
.table-scale-wrap table {
  transform-origin: top left;
  /* JS 에서 transform: scale(N) 주입 */
}

/* ── pre / code: dark theme + 강제 줄바꿈 ── */
pre {
  background: #282c34 !important;
  color: #abb2bf !important;
  border-radius: 8px !important;
  padding: 14px 18px !important;
  margin: 12px 0 !important;
  border: none !important;
  box-shadow: none !important;
  white-space: pre-wrap !important;
  word-break: break-all !important;
  overflow: visible !important;
  max-width: 100% !important;
  font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace !important;
  font-size: 8.5pt !important;
  line-height: 1.65 !important;
}
pre code {
  background: transparent !important;
  color: inherit !important;
  padding: 0 !important;
  border: none !important;
  font-size: inherit !important;
  border-radius: 0 !important;
}
/* 언어 미지정 plain-code 블록 */
pre code.plain-code {
  color: #abb2bf !important;
}

/* ── hljs atom-one-dark 토큰 컬러 강제 적용 ── */
.hljs                            { background: #282c34 !important; color: #abb2bf !important; }
.hljs-comment, .hljs-quote       { color: #7f848e !important; font-style: italic; }
.hljs-keyword, .hljs-selector-tag,
.hljs-addition                   { color: #c678dd !important; }
.hljs-string, .hljs-meta .hljs-meta-string,
.hljs-doctag, .hljs-regexp       { color: #98c379 !important; }
.hljs-number, .hljs-literal      { color: #d19a66 !important; }
.hljs-title, .hljs-section       { color: #61afef !important; }
.hljs-class .hljs-title,
.hljs-type                       { color: #e5c07b !important; }
.hljs-attr, .hljs-variable,
.hljs-template-variable          { color: #e06c75 !important; }
.hljs-built_in, .hljs-deletion   { color: #56b6c2 !important; }
.hljs-params                     { color: #abb2bf !important; }
.hljs-meta, .hljs-meta .hljs-keyword { color: #e06c75 !important; }
.hljs-name, .hljs-selector-id,
.hljs-selector-class             { color: #e06c75 !important; }
.hljs-symbol, .hljs-bullet,
.hljs-link                       { color: #56b6c2 !important; }

/* ── inline code (pre 밖) ── */
:not(pre) > code {
  background: #f0f2f5 !important;
  color: #e45649 !important;
  padding: 2px 6px !important;
  border-radius: 4px !important;
  font-size: 0.87em !important;
  font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace !important;
  border: 1px solid #dde0e5 !important;
}

/* ── Mermaid 컨테이너 ── */
.mermaid {
  text-align: center;
  margin: 14px 0;
  background: #fafafa;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  overflow: visible;  /* Chrome PDF: overflow:hidden 은 다중 페이지 요소에서 콘텐츠를 클리핑함 */
  break-before: avoid-page;  /* Chrome PDF: 다이어그램 앞에 강제 쪽 나눔 방지 */
  break-inside: auto;        /* 매우 긴 다이어그램은 쪽 나눔 허용 */
}
/* max-width: 100%!important 로 Mermaid 가 주입하는 inline max-width 를 무력화.
   height 는 의도적으로 CSS 에서 선언하지 않음 — SVG 프레젠테이션 속성 height="N" 이
   CSS 초기값(auto)보다 우선순위가 높기 때문. JS 가 setAttribute('height', N) 으로
   결정한 픽셀 값이 Chrome PDF 레이아웃에 그대로 사용된다. */
.mermaid svg {
  max-width: 100% !important;
  display: block !important;
  margin: 0 auto;
}

/* ── 커스텀 HTML 다이어그램: overflow 보정 ── */
.he-flow, .gs-wrap, .gate-map-grid, .book-map,
.layer-arch, .gs-col, .bm-arrow-row {
  overflow: visible;
}

/* gate-grid: 800px 고정 폭으로 4등분 컬럼 보장 → JS가 576/800=0.72 로 축소
   min-width !important 은 JS el.style.minWidth='0' (inline normal) 보다 강해
   applyDiagramScale 이 measuredW=800 을 감지하고 scale 적용 */
.gate-grid {
  overflow: visible !important;
  min-width: 800px !important;
}
.gate-card {
  overflow: visible !important;
}

/* chip / gate-title: word-break 허용 → 긴 이름(PrivilegeEscalationDetector 등)이
   컬럼을 강제 확장하지 않도록 함. scale ≈ 0.85 수준으로 개선. */
.chip {
  word-break: break-all !important;
  overflow-wrap: break-word !important;
  white-space: normal !important;
}
.gate-title, .gate-sub, .section-label {
  word-break: break-word !important;
  overflow-wrap: break-word !important;
}

/* summary-card: flex-shrink:0 강제 — 기본 flex-shrink:1이 숫자 항목을 수축시켜
   getBoundingClientRect overflow를 숨기는 문제 방지 → JS가 overflow 감지 → scale ≈ 0.95 */
.summary-card, .summary-card * {
  flex-shrink: 0 !important;
  overflow: visible !important;
}

@media print {
  body { height: auto !important; overflow: visible !important; }
  img { break-inside: avoid !important; page-break-inside: avoid !important; }
  .mermaid-chunk { break-inside: avoid !important; page-break-inside: avoid !important; }
  figure { break-inside: avoid !important; page-break-inside: avoid !important; }
}

/* ── 외부 이미지 (터미널·대시보드 스크린샷 등) ── */
img:not(.mermaid-chunk img) {
  max-width: 100% !important;
  height: auto !important;
  display: block !important;
  margin: 12px auto !important;
}
figure {
  margin: 20px 0 !important;
  text-align: center !important;
  break-inside: avoid !important;
  page-break-inside: avoid !important;
}
figcaption {
  font-size: 8.5pt !important;
  color: #555 !important;
  margin-top: 8px !important;
  font-style: italic !important;
  text-align: center !important;
  line-height: 1.5 !important;
}
"""

def build_page_html(body_html: str, title: str) -> str:
    book_css = BOOK_CSS  # build_book.py 에서 추출한 전체 CSS
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&family=Noto+Serif+KR:wght@400;700&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/python.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/bash.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
{book_css}
{_PDF_OVERRIDE_CSS}
</style>
</head>
<body>
<main id="main">
{body_html}
</main>
<script>
(async () => {{
  // highlight.js — 언어 지정 블록만 처리
  const ALLOWED = new Set(['python','bash','shell','sh','yaml','json','javascript','js','html','css','sql','dockerfile']);
  document.querySelectorAll('pre code').forEach(block => {{
    const cls = block.className || '';
    const m = cls.match(/language-([a-z0-9_+-]+)/);
    if (m && ALLOWED.has(m[1])) hljs.highlightElement(block);
    else block.classList.add('plain-code');
  }});

  // ── Mermaid 전처리: 노드 라벨 내 리터럴 개행 → <br/> ────────────────────────
  // Mermaid 파서는 "" 내부의 실제 줄바꿈을 허용하지 않음. <br/> 로 치환.
  document.querySelectorAll('.mermaid').forEach(el => {{
    let src = el.textContent;
    let out = '';
    let inQuote = false;
    for (let i = 0; i < src.length; i++) {{
      const ch = src[i];
      if (ch === '"') {{ inQuote = !inQuote; out += ch; }}
      else if (ch === '\\' && src[i+1] === 'n' && inQuote) {{ 
        out += '<br/>'; 
        i++; 
      }}
      else {{ out += ch; }}
    }}
    if (out !== src) el.textContent = out;
  }});

  // Mermaid v10 — run() 은 Promise 반환.
  // 복잡한 flowchart TD(15+ 노드)에서 promise 가 hang 하는 경우 대비해
  // Promise.race 로 8초 타임아웃을 걸고, SVG 가 이미 렌더됐으면 계속 진행.
  mermaid.initialize({{
    startOnLoad: false,
    theme: 'default',
    securityLevel: 'loose',
    fontFamily: 'Noto Sans KR, sans-serif',
  }});
  try {{
    await Promise.race([
      mermaid.run({{ querySelector: '.mermaid' }}),
      new Promise(resolve => setTimeout(resolve, 15000)),
    ]);
  }} catch (e) {{ console.warn('mermaid.run error:', e); }}

  // ── 테이블 자동 스케일링 ──────────────────────────────────────────────────
  // PDF 에서는 overflow-x:auto 가 동작하지 않아 넓은 테이블이 잘림.
  // 테이블 실제 너비 > 컨테이너 너비일 때 transform:scale() 로 축소.
  const main = document.getElementById('main') || document.body;
  const availW = main.clientWidth - 48; // 좌우 패딩 24px×2 제외

  document.querySelectorAll('table').forEach(table => {{
    // 이미 .table-scale-wrap 에 감싸진 경우 스킵
    if (table.parentElement.classList.contains('table-scale-wrap')) return;

    const tableW = table.scrollWidth;
    if (tableW <= availW + 2) return; // 넉넉하게 맞으면 스킵

    const scale = availW / tableW;
    const origH = table.offsetHeight;

    // 래퍼 div 생성 — 스케일 축소 후 빈 공간을 없애기 위해 높이 조정
    const wrap = document.createElement('div');
    wrap.className = 'table-scale-wrap';
    wrap.style.height = `${{Math.ceil(origH * scale)}}px`;

    table.parentNode.insertBefore(wrap, table);
    wrap.appendChild(table);
    table.style.transformOrigin = 'top left';
    table.style.transform = `scale(${{scale}})`;
  }});

  // ── Mermaid SVG 크기 보정 ──────────────────────────────────────────────────
  // 원인: Mermaid v10 은 SVG 에 width="100%" + height 속성 없음 으로 렌더링.
  //        Chrome PDF 엔진은 intrinsic height 를 viewBox 비율로 계산 → 3079px → 빈 페이지 2장.
  //        inline style / CSS height !important / transform+wrapper 모두 PDF 레이아웃에 무효.
  // 해결: getBoundingClientRect() 로 실제 화면 크기를 측정한 뒤
  //        svg.setAttribute('width'/'height') 로 픽셀 값을 직접 지정.
  //        Chrome PDF 는 SVG attribute 의 픽셀 값을 intrinsic size 로 사용하므로
  //        viewBox 비율 계산을 건너뛰고 우리가 지정한 크기로 레이아웃된다.
  //        viewBox 자체는 수정 불필요 — content→targetSize 매핑을 이미 담당함.
  document.querySelectorAll('.mermaid svg').forEach(svg => {{
    svg.style.cssText = '';   // Mermaid 가 주입한 inline max-width 초기화
    const r = svg.getBoundingClientRect();
    const w = r.width, h = r.height;
    if (w <= 0 || h <= 0) return;

    const scale = w > availW ? availW / w : 1;
    const targetW = Math.ceil(w * scale);
    const targetH = Math.ceil(h * scale);

    // PDF intrinsic size = targetW × targetH (viewBox 비율 계산을 우회)
    svg.setAttribute('width', targetW);
    svg.setAttribute('height', targetH);
    svg.removeAttribute('style');   // Mermaid inline max-width 완전 제거
    svg.style.cssText = 'display:block !important; margin:0 auto !important;';
  }});

  // ── HTML 다이어그램 컨테이너 자동 스케일링 ────────────────────────────────────
  // gate-grid, he-flow, gs-wrap 등 커스텀 HTML 도표가 페이지 폭을 초과할 때 축소.
  const DIAGRAM_SELECTORS = [
    '.gate-grid', '.he-flow', '.gs-wrap', '.pip-wrap', '.te-outer',
    '.book-map', '.layer-arch', '.gate-map-grid',
  ];

  function applyDiagramScale(el, measuredW) {{
    el.style.width = measuredW + 'px';
    el.style.minWidth = '0';
    const origH = el.offsetHeight;
    const scale = availW / measuredW;
    const wrap = document.createElement('div');
    wrap.className = 'diagram-scale-wrap';
    wrap.style.cssText = `width:100%;height:${{Math.ceil(origH * scale)}}px;`;
    el.parentNode.insertBefore(wrap, el);
    wrap.appendChild(el);
    el.style.transformOrigin = 'top left';
    el.style.transform = `scale(${{scale}})`;
  }}

  for (const sel of DIAGRAM_SELECTORS) {{
    document.querySelectorAll(sel).forEach(el => {{
      if (el.closest('.diagram-scale-wrap')) return;

      // .gate-grid 는 1fr 컬럼으로 인해 scrollWidth = clientWidth.
      // 자식 요소의 실제 right 경계를 직접 측정해 오버플로 감지.
      if (el.classList.contains('gate-grid')) {{
        const gridLeft = el.getBoundingClientRect().left;
        let maxRight = el.getBoundingClientRect().right;
        el.querySelectorAll('*').forEach(child => {{
          const r = child.getBoundingClientRect().right;
          if (r > maxRight) maxRight = r;
        }});
        const naturalW = Math.round(maxRight - gridLeft);
        if (naturalW > availW + 4) applyDiagramScale(el, naturalW);
        return;
      }}

      const elW = el.scrollWidth;
      if (elW <= availW + 4) return;
      applyDiagramScale(el, elW);
    }});
  }}

  // ── 이미지 자동 크기 조정 ────────────────────────────────────────────────────
  // Chrome PDF 엔진은 img 의 width/height attribute 를 intrinsic size 로 사용하므로
  // naturalWidth > 본문 폭인 경우 attribute 를 직접 재지정해 레이아웃 오버플로를 막는다.
  document.querySelectorAll('img').forEach(img => {{
    if (img.closest('.mermaid-chunk')) return;
    const iw = img.naturalWidth;
    const ih = img.naturalHeight;
    if (iw > 0 && iw > availW) {{
      img.setAttribute('width',  Math.round(availW));
      img.setAttribute('height', Math.round(ih * availW / iw));
    }}
  }});

  // 렌더·레이아웃 완료 신호 — Playwright 가 이 값을 폴링
  window.__mermaidDone = true;
}})();
</script>
</body>
</html>"""


def _rewrite_img_paths(html_str: str, base_dir: Path) -> str:
    """img src 의 상대 경로를 file:// 절대 경로로 치환한다.

    build_pdf_chapters.py 는 임시 디렉토리에 HTML 을 저장 후 file:// 로 로드하므로
    원본 md 파일 기준 상대 경로는 반드시 절대 URI 로 변환해야 이미지가 표시된다.
    http(s)://, data:, file:// 로 시작하는 src 는 그대로 유지한다.
    """
    def _to_abs(m: re.Match) -> str:
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:", "file://")):
            return m.group(0)
        abs_path = (base_dir / src).resolve()
        return f'src="file://{abs_path}"'
    return re.sub(r'src="([^"]+)"', _to_abs, html_str)


# ── Playwright 변환 ───────────────────────────────────────────────────────────

async def convert_one(md_path: Path, browser, *, verbose: bool = True) -> Path:
    """md 파일 하나를 PDF로 변환하고 출력 경로를 반환한다."""
    rel = md_path.relative_to(BOOK_DIR)
    out = PDF_DIR / rel.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    raw  = md_path.read_text(encoding="utf-8")
    raw  = inject_mermaid(md_path.stem, raw)
    body = md_to_html(raw)
    html = _rewrite_img_paths(build_page_html(body, md_path.stem), md_path.parent)

    import math, shutil, tempfile

    # A4 PDF 내용 폭 = 210 - 25(left) - 20(right) = 165mm ≈ 624px (at 96dpi)
    _PDF_CONTENT_W = 624
    _AVAIL_W       = _PDF_CONTENT_W - 32   # 좌우 패딩 16px×2

    # ── 핵심 해결책: 청크 분할 캡처 ──────────────────────────────────────────────
    # 근본 원인: Chrome PDF 엔진은 A4 페이지 높이(~944px)를 초과하는 단일 img/SVG 를
    #   올바르게 레이아웃하지 못한다. 1700px 다이어그램은 1.8배 높이라서 어떤 방식
    #   (data:URL, inline SVG, file:// URL) 으로 넣어도 빈 공간이 삽입된다.
    #
    # 해결: 모든 Mermaid 다이어그램을 ≤350px 청크로 분할 캡처한다.
    #   • 350px < 나머지 페이지 공간(~790px) → 앞 요소 직후 첫 청크가 같은 페이지에 배치
    #   • 앞 요소 뒤 남은 공간이 820px 청크를 수용 못해 발생하던 빈 공간이 제거됨
    #   • 820px 청크는 블록쿼트 이후 남은 공간(~790px) < 820px → 페이지 강제 전환
    #     → 790px 빈 공간. 350px 청크는 790px에 수용 → 빈 공간 없음.
    #
    # 추가 조치:
    #   • device_scale_factor=1 → CSS px = 물리 px (DPR 배율 배제)
    #   • page.screenshot(clip=...) → 페이지 전체를 렌더 후 정확한 좌표로 크롭
    #   • page.goto("file://") → Chrome 이 이미지를 레이아웃 전 동기 로딩
    _CHUNK_H = 300   # 청크당 최대 높이 — 작을수록 앞 요소 직후 배치 가능성 높아짐

    temp_dir = Path(tempfile.mkdtemp(prefix="mermaid_pdf_"))
    try:
        # ── Phase 1: DPR=1, 뷰포트 확장 → 청크별 PNG 캡처 ─────────────────────
        ctx1 = await browser.new_context(device_scale_factor=1)
        render_page = await ctx1.new_page()
        # 큰 초기 뷰포트 → 렌더 후 전체 높이로 확장
        await render_page.set_content(html, wait_until="networkidle")
        try:
            await render_page.wait_for_function(
                "() => window.__mermaidDone === true", timeout=20000)
        except Exception:
            pass
        # 전체 콘텐츠 높이로 뷰포트 확장 (Mermaid 렌더링 후 실제 높이 측정)
        full_h = await render_page.evaluate(
            "() => Math.max(document.body.scrollHeight, 6000)")
        await render_page.set_viewport_size({"width": _PDF_CONTENT_W, "height": full_h})

        # (다이어그램 인덱스) → [(file_url, w, h), ...]  청크 리스트
        mermaid_diagrams: list[list[tuple[str, int, int]]] = []
        n_containers = await render_page.locator(".mermaid").count()

        for idx in range(n_containers):
            try:
                info = await render_page.evaluate(f"""() => {{
                    const container = document.querySelectorAll('.mermaid')[{idx}];
                    const svg = container.querySelector('svg');
                    if (!svg) return null;
                    const r = svg.getBoundingClientRect();
                    if (r.width <= 0 || r.height <= 0) return null;
                    // 폭만 기준으로 스케일 (높이는 종횡비 유지)
                    const scW = r.width > {_AVAIL_W} ? {_AVAIL_W} / r.width : 1;
                    const tw = Math.ceil(r.width  * scW);
                    const th = Math.ceil(r.height * scW);
                    svg.setAttribute('width',  tw);
                    svg.setAttribute('height', th);
                    svg.style.cssText = 'display:block;margin:0 auto;';
                    const b = svg.getBoundingClientRect();
                    return {{x: b.x, y: b.y, w: Math.round(b.width), h: Math.round(b.height)}};
                }}""")
                if not info:
                    mermaid_diagrams.append([])
                    continue

                sx, sy, tw, th = info['x'], info['y'], info['w'], info['h']
                n_chunks = max(1, math.ceil(th / _CHUNK_H))
                chunks: list[tuple[str, int, int]] = []

                for ci in range(n_chunks):
                    ry     = round(sy + ci * _CHUNK_H)
                    ch     = min(_CHUNK_H, round(sy + th) - ry)
                    if ch <= 0:
                        break
                    png = await render_page.screenshot(
                        type="png",
                        clip={"x": round(sx), "y": ry, "width": tw, "height": ch},
                    )
                    chunk_path = temp_dir / f"mermaid_{idx:04d}_{ci:02d}.png"
                    chunk_path.write_bytes(png)
                    chunks.append((f"file://{chunk_path}", tw, ch))

                mermaid_diagrams.append(chunks)
            except Exception:
                mermaid_diagrams.append([])  # 실패 시 빈 목록 → 원본 유지
                continue
        await render_page.close()
        await ctx1.close()

        # ── Phase 2: HTML 수정 → <img> 청크 삽입 ────────────────────────────────
        p2_html = html

        if any(mermaid_diagrams):
            diag_iter = iter(mermaid_diagrams)

            def _replace_mermaid(m: re.Match) -> str:
                try:
                    chunks = next(diag_iter)
                except StopIteration:
                    return m.group(0)
                if not chunks:
                    return m.group(0)

                n = len(chunks)
                parts = []
                for ci2, (fu, w, h) in enumerate(chunks):
                    mt = "14px" if ci2 == 0 else "0"
                    mb = "14px" if ci2 == n - 1 else "0"
                    # display:table + width:100% 는 Chromium PDF 엔진에서 break-inside:avoid 를 가장 잘 준수함
                    parts.append(
                        f'<div class="mermaid-chunk" style="margin:{mt} 0 {mb};'
                        f'display:table;width:100%;break-inside:avoid;page-break-inside:avoid;">'
                        f'<img src="{fu}" width="{w}" height="{h}" '
                        f'style="display:block;margin:0 auto;width:{w}px;height:{h}px;max-width:none;border:none;">'
                        f'</div>'
                    )
                return "".join(parts)

            p2_html = re.sub(
                r'<div\s+class="mermaid"[^>]*>.*?</div>',
                _replace_mermaid,
                p2_html,
                flags=re.DOTALL,
            )

        html_file = temp_dir / "chapter.html"
        html_file.write_text(p2_html, encoding="utf-8")

        # ── Phase 2: file:// 로 로드 → PDF 생성 ──────────────────────────────────
        ctx2 = await browser.new_context(device_scale_factor=1)
        page = await ctx2.new_page()
        # 뷰포트 너비는 고정, 높이는 렌더링 후 실제 콘텐츠 높이로 확장하여 clipping 방지
        await page.set_viewport_size({"width": _PDF_CONTENT_W, "height": 6000})
        await page.goto(f"file://{html_file}", wait_until="networkidle")
        await page.wait_for_load_state("load")
        try:
            await page.wait_for_function(
                "() => window.__mermaidDone === true", timeout=10000)
        except Exception:
            pass

        # 실제 콘텐츠 높이 측정 후 뷰포트 업데이트
        real_h = await page.evaluate("document.body.scrollHeight")
        await page.set_viewport_size({"width": _PDF_CONTENT_W, "height": max(real_h, 6000)})

        await page.pdf(
            path=str(out),
            format="A4",
            margin={"top": "22mm", "right": "20mm", "bottom": "25mm", "left": "25mm"},
            print_background=True,
        )
        await page.close()
        await ctx2.close()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if verbose:
        size_kb = out.stat().st_size // 1024
        print(f"  ✅ {rel}  ({size_kb} KB)")

    return out


async def run_all(files: list[Path]) -> tuple[int, int]:
    ok = fail = 0
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch()
        except Exception as e:
            if "Executable doesn't exist" in str(e):
                print("\n❌ Playwright 브라우저 엔진이 설치되지 않았습니다.")
                print("   아래 명령어를 실행하여 브라우저를 설치해 주세요:")
                print("   python -m playwright install chromium")
                if platform.system() == "Linux":
                    print("   sudo python -m playwright install-deps chromium")
                return 0, len(files)
            raise e

        for md_path in files:
            try:
                await convert_one(md_path, browser)
                ok += 1
            except Exception as exc:
                print(f"  ❌ {md_path.relative_to(BOOK_DIR)}: {exc}")
                fail += 1
        await browser.close()
    return ok, fail


# ── 파일 검색 헬퍼 ────────────────────────────────────────────────────────────────

def _find_md_files(arg: str) -> list[Path]:
    """단일 검색 인수 → 매칭되는 .md 파일 목록 반환 (정렬됨).

    우선순위:
      1. 절대 경로 또는 cwd 기준 상대 경로 (파일 또는 디렉토리)
      2. BOOK_DIR 기준 상대 경로 (파일 또는 디렉토리, NFC/NFD 정규화)
      3. 파일명 부분 일치 (*인수*.md)

    디렉토리가 매칭되면 하위 .md 파일 전체를 반환한다.
    EXCLUDE_STEMS 제외는 rglob 검색(3단계)에만 적용된다:
    명시적 경로(1·2단계)는 README.md 등도 그대로 포함한다.
    """
    def _dir_files(d: Path) -> list[Path]:
        return sorted(f for f in d.rglob("*.md") if f.stem not in EXCLUDE_STEMS)

    # 1. 절대 경로 / cwd 기준 상대 경로
    p = Path(arg).absolute()
    if p.exists():
        if p.is_file() and p.suffix == ".md":
            return [p]
        if p.is_dir():
            return _dir_files(p)

    # 2. BOOK_DIR 기준 상대 경로 (Unicode 정규화 대응)
    p = robust_path(BOOK_DIR / arg)
    if p.exists():
        if p.is_file() and p.suffix == ".md":
            return [p]
        if p.is_dir():
            return _dir_files(p)

    # 3. 파일명(stem) 부분 일치 검색
    # macOS APFS는 파일명을 NFD로 저장하므로 패턴도 NFD로 정규화한다.
    nfd_arg = unicodedata.normalize("NFD", arg)
    found = sorted(f for f in BOOK_DIR.rglob(f"*{nfd_arg}*.md") if f.stem not in EXCLUDE_STEMS)
    if not found:
        print(f"  ⚠️  대상을 찾을 수 없음: {arg}")
    return found


# ── 병합 변환 ─────────────────────────────────────────────────────────────────────

async def convert_merged(
    md_paths: list[Path], out_path: Path, browser, *, verbose: bool = True
) -> Path:
    """여러 .md 파일을 지정 순서대로 하나의 PDF로 병합한다.

    파일 사이에 강제 페이지 나눔을 삽입하고, 이미지 경로는 각 파일 기준으로
    절대화한다. Mermaid 다이어그램은 convert_one 과 동일한 청크 분할 방식으로 처리한다.
    """
    import math, shutil, tempfile

    out_path.parent.mkdir(parents=True, exist_ok=True)

    _PAGE_BREAK    = '<div style="break-before:page;page-break-before:always;margin:0;padding:0;"></div>\n'
    _PDF_CONTENT_W = 624
    _AVAIL_W       = _PDF_CONTENT_W - 32
    _CHUNK_H       = 300

    # 파일별 HTML body 생성 — 이미지 경로를 각 파일의 디렉토리 기준으로 절대화
    bodies: list[str] = []
    for md_path in md_paths:
        raw  = md_path.read_text(encoding="utf-8")
        raw  = inject_mermaid(md_path.stem, raw)
        body = md_to_html(raw)
        body = _rewrite_img_paths(body, md_path.parent)
        bodies.append(body)

    combined_body = _PAGE_BREAK.join(bodies)
    title = (
        f"{md_paths[0].stem} … {md_paths[-1].stem}"
        if len(md_paths) > 1
        else md_paths[0].stem
    )
    html = build_page_html(combined_body, title)

    temp_dir = Path(tempfile.mkdtemp(prefix="mermaid_merge_"))
    try:
        # ── Phase 1: DPR=1 렌더 → Mermaid 청크 PNG 캡처 ─────────────────────
        ctx1 = await browser.new_context(device_scale_factor=1)
        render_page = await ctx1.new_page()
        await render_page.set_content(html, wait_until="networkidle")
        try:
            await render_page.wait_for_function(
                "() => window.__mermaidDone === true", timeout=20000)
        except Exception:
            pass
        full_h = await render_page.evaluate(
            "() => Math.max(document.body.scrollHeight, 6000)")
        await render_page.set_viewport_size({"width": _PDF_CONTENT_W, "height": full_h})

        mermaid_diagrams: list[list[tuple[str, int, int]]] = []
        n_containers = await render_page.locator(".mermaid").count()
        for idx in range(n_containers):
            try:
                info = await render_page.evaluate(f"""() => {{
                    const c = document.querySelectorAll('.mermaid')[{idx}];
                    const s = c.querySelector('svg');
                    if (!s) return null;
                    const r = s.getBoundingClientRect();
                    if (r.width <= 0 || r.height <= 0) return null;
                    const sc = r.width > {_AVAIL_W} ? {_AVAIL_W} / r.width : 1;
                    const tw = Math.ceil(r.width * sc), th = Math.ceil(r.height * sc);
                    s.setAttribute('width', tw); s.setAttribute('height', th);
                    s.style.cssText = 'display:block;margin:0 auto;';
                    const b = s.getBoundingClientRect();
                    return {{x: b.x, y: b.y, w: Math.round(b.width), h: Math.round(b.height)}};
                }}""")
                if not info:
                    mermaid_diagrams.append([])
                    continue
                sx, sy, tw, th = info['x'], info['y'], info['w'], info['h']
                chunks: list[tuple[str, int, int]] = []
                for ci in range(max(1, math.ceil(th / _CHUNK_H))):
                    ry = round(sy + ci * _CHUNK_H)
                    ch = min(_CHUNK_H, round(sy + th) - ry)
                    if ch <= 0:
                        break
                    png = await render_page.screenshot(
                        type="png",
                        clip={"x": round(sx), "y": ry, "width": tw, "height": ch},
                    )
                    chunk_path = temp_dir / f"m_{idx:04d}_{ci:02d}.png"
                    chunk_path.write_bytes(png)
                    chunks.append((f"file://{chunk_path}", tw, ch))
                mermaid_diagrams.append(chunks)
            except Exception:
                mermaid_diagrams.append([])
        await render_page.close()
        await ctx1.close()

        # ── Phase 2: Mermaid div → img 청크 치환 ────────────────────────────
        p2_html = html
        if any(mermaid_diagrams):
            diag_iter = iter(mermaid_diagrams)

            def _replace_mermaid(m: re.Match) -> str:
                try:
                    chunks = next(diag_iter)
                except StopIteration:
                    return m.group(0)
                if not chunks:
                    return m.group(0)
                n = len(chunks)
                parts = []
                for ci2, (fu, w, h) in enumerate(chunks):
                    mt = "14px" if ci2 == 0 else "0"
                    mb = "14px" if ci2 == n - 1 else "0"
                    parts.append(
                        f'<div class="mermaid-chunk" style="margin:{mt} 0 {mb};'
                        f'display:table;width:100%;break-inside:avoid;page-break-inside:avoid;">'
                        f'<img src="{fu}" width="{w}" height="{h}" '
                        f'style="display:block;margin:0 auto;width:{w}px;height:{h}px;max-width:none;border:none;">'
                        f'</div>'
                    )
                return "".join(parts)

            p2_html = re.sub(
                r'<div\s+class="mermaid"[^>]*>.*?</div>',
                _replace_mermaid,
                p2_html,
                flags=re.DOTALL,
            )

        html_file = temp_dir / "merged.html"
        html_file.write_text(p2_html, encoding="utf-8")

        # ── Phase 3: file:// 로드 → PDF 생성 ────────────────────────────────
        ctx2 = await browser.new_context(device_scale_factor=1)
        page = await ctx2.new_page()
        await page.set_viewport_size({"width": _PDF_CONTENT_W, "height": 6000})
        await page.goto(f"file://{html_file}", wait_until="networkidle")
        await page.wait_for_load_state("load")
        try:
            await page.wait_for_function(
                "() => window.__mermaidDone === true", timeout=10000)
        except Exception:
            pass
        real_h = await page.evaluate("document.body.scrollHeight")
        await page.set_viewport_size({"width": _PDF_CONTENT_W, "height": max(real_h, 6000)})
        await page.pdf(
            path=str(out_path),
            format="A4",
            margin={"top": "22mm", "right": "20mm", "bottom": "25mm", "left": "25mm"},
            print_background=True,
        )
        await page.close()
        await ctx2.close()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if verbose:
        size_kb = out_path.stat().st_size // 1024
        print(f"  ✅ {out_path.name}  ({len(md_paths)}개 파일 병합, {size_kb} KB)")

    return out_path


async def run_merged(files: list[Path], out_path: Path) -> bool:
    """convert_merged 를 Playwright 컨텍스트에서 실행한다."""
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch()
        except Exception as e:
            if "Executable doesn't exist" in str(e):
                print("\n❌ Playwright 브라우저 엔진이 설치되지 않았습니다.")
                print("   python -m playwright install chromium")
                if platform.system() == "Linux":
                    print("   sudo python -m playwright install-deps chromium")
                return False
            raise e
        try:
            await convert_merged(files, out_path, browser)
            ok = True
        except Exception as exc:
            print(f"  ❌ 병합 실패: {exc}")
            ok = False
        await browser.close()
    return ok


# ── 도움말 ───────────────────────────────────────────────────────────────────────

def _print_help() -> None:
    """--help 출력."""
    print("""
사용법
──────
  python build_pdf_chapters.py [--help] [--merge [OUTPUT]] [파일/패턴 ...]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
모드 1 — 인수 없음: 전체 일괄 변환
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python build_pdf_chapters.py

  Media/Book/ 하위 모든 .md 파일을 파일명 순으로 개별 변환한다.
  기본 제외: README.md, IMAGES.md

  출력: Media/Book/pdf/ (디렉토리 구조 그대로 유지)
    Part_I_기초/Chapter_01_*.pdf
    Part_II_지표시스템/Chapter_03_*.pdf
    Appendix/A_58개지표_레퍼런스.pdf  ← Appendix 포함
    00_서문.pdf                        ← 서문 포함

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
모드 2 — 파일/패턴 지정: 개별 변환
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python build_pdf_chapters.py 파일/패턴 [...]

  지정한 파일들을 각각 별도 PDF로 변환한다.

  예)
    python build_pdf_chapters.py Chapter_02
    python build_pdf_chapters.py Chapter_01 Chapter_02 Chapter_03
    python build_pdf_chapters.py Part_II_지표시스템
    python build_pdf_chapters.py Appendix

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
모드 3 — --merge: 여러 파일을 하나의 PDF로 병합
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python build_pdf_chapters.py --merge [OUTPUT] [파일/패턴 ...]

  OUTPUT   : 출력 파일명 (확장자 제외). 생략 시 "full_book" 사용.
             Media/Book/pdf/OUTPUT.pdf 에 저장.
  파일/패턴: 인수 지정 순서가 PDF 내 챕터 순서가 된다.
             생략 시 전체 파일을 책 순서(서문 → Part_I … Part_VI → Appendix)로 병합한다.

  예)
    python build_pdf_chapters.py --merge                          ← 전체 → full_book.pdf
    python build_pdf_chapters.py --merge full_book                ← 전체 → full_book.pdf (동일)
    python build_pdf_chapters.py --merge preview_part1 서문 Part_I_기초
    python build_pdf_chapters.py --merge appendix_only Appendix
    python build_pdf_chapters.py --merge ch03-ch05 Chapter_03 Chapter_04 Chapter_05

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파일 검색 우선순위 (각 인수에 대해 순서대로 시도)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. 절대 경로 또는 현재 디렉토리(cwd) 기준 상대 경로
  2. Media/Book/ 기준 상대 경로 (Unicode NFC/NFD 정규화 자동 처리)
  3. 위 두 경우에서 디렉토리가 매칭되면 하위 .md 전체 반환
  4. 파일명 부분 일치 검색 (*인수*.md, EXCLUDE_STEMS 제외)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
특수 파일 적용 방안
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  00_서문.md
    자동 포함: 인수 없음 실행 시 전체 변환에 포함됨 (EXCLUDE_STEMS 비대상)
    단독 변환: python build_pdf_chapters.py 서문
    병합 포함: python build_pdf_chapters.py --merge preview 서문 Chapter_01 Chapter_02

  README.md
    기본 제외: README는 GitHub 열람용이므로 자동 변환 대상에서 제외됨
    강제 포함: 절대 경로 또는 Media/Book/ 기준 명시 경로로 지정 시 포함 가능
      python build_pdf_chapters.py README.md
      python build_pdf_chapters.py --merge with_readme README.md 서문 Chapter_01

  Appendix (A~M, 13개 파일)
    전체 개별 변환: python build_pdf_chapters.py Appendix
    전체 병합:      python build_pdf_chapters.py --merge appendix_all Appendix
    특정 파일만:    python build_pdf_chapters.py A_58개지표
                    python build_pdf_chapters.py B_CLI C_환경변수

  IMAGES.md
    기본 제외: 이미지 목록 관리 파일이므로 자동 변환 대상에서 제외됨

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
의존성 설치
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  pip install playwright markdown
  python -m playwright install chromium
  # Linux 추가:
  sudo python -m playwright install-deps chromium
""")


# ── 메인 ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    # ── --help ────────────────────────────────────────────────────────────────
    if "--help" in args or "-h" in args:
        _print_help()
        sys.exit(0)

    # ── --merge [OUTPUT_STEM] [파일/패턴 ...] 감지 ───────────────────────────
    # OUTPUT_STEM 생략 시 "full_book" 으로 전체 파일 병합.
    # 사용법:
    #   python build_pdf_chapters.py --merge                          ← 전체 병합 → full_book.pdf
    #   python build_pdf_chapters.py --merge OUTPUT_STEM              ← 전체 병합 → OUTPUT_STEM.pdf
    #   python build_pdf_chapters.py --merge OUTPUT_STEM 파일/패턴…   ← 지정 파일 병합
    merge_out: str | None = None
    if "--merge" in args:
        idx = args.index("--merge")
        rest = args[idx + 1:]  # --merge 이후 인자들
        # 다음 인자가 없거나 다른 플래그이면 기본 출력명 사용
        if not rest or rest[0].startswith("-"):
            merge_out = "full_book"
            args = [a for i, a in enumerate(args) if i != idx]
        else:
            merge_out = rest[0]
            args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    # ── 파일 수집 ──────────────────────────────────────────────────────────────
    if args:
        seen: set[Path] = set()
        ordered: list[Path] = []
        for arg in args:
            for f in _find_md_files(arg):
                if f not in seen:
                    seen.add(f)
                    ordered.append(f)
        # 병합 모드 → 지정 순서 유지 / 개별 변환 모드 → 파일명 정렬
        files = ordered if merge_out else sorted(ordered)
    else:
        # 인수 없음: 서문 → Part_I … Part_VI → Appendix 순 (책 순서)
        all_md = (f for f in BOOK_DIR.rglob("*.md") if f.stem not in EXCLUDE_STEMS)
        if merge_out is not None:
            files = sorted(all_md, key=_book_sort_key)
        else:
            files = sorted(all_md)

    if not files:
        print("❌ 변환할 마크다운 파일이 없습니다.")
        sys.exit(0)

    t0 = time.time()

    if merge_out is not None:
        # ── 병합 모드 ──────────────────────────────────────────────────────────
        out_path = PDF_DIR / f"{merge_out}.pdf"
        print(f"📄 병합 대상: {len(files)}개 파일")
        for f in files:
            print(f"   {f.relative_to(BOOK_DIR)}")
        print(f"📂 출력: {out_path}\n")
        ok = asyncio.run(run_merged(files, out_path))
        elapsed = time.time() - t0
        print(f"\n{'─'*60}")
        print(f"{'완료' if ok else '실패'}: {len(files)}개 → {out_path.name}  ({elapsed:.1f}s)")
        if not ok:
            sys.exit(1)
    else:
        # ── 개별 변환 모드 ─────────────────────────────────────────────────────
        print(f"📄 변환 대상: {len(files)}개 파일")
        print(f"📂 출력 디렉토리: {PDF_DIR}\n")
        ok_n, fail_n = asyncio.run(run_all(files))
        elapsed = time.time() - t0
        print(f"\n{'─'*60}")
        print(f"완료: {ok_n}개 성공 / {fail_n}개 실패  ({elapsed:.1f}s)")
        if fail_n:
            sys.exit(1)


if __name__ == "__main__":
    main()
