"""영문판 EPUB 빌드 — Book_EN/ → output_en/kdp/*.epub

config_en 을 sys.modules['config'] 로 주입해 build_epub.py 를 재사용한다.

Usage:
    python build_epub_en.py                    # KDP EPUB 빌드
    python build_epub_en.py --target kdp       # KDP용만
    python build_epub_en.py --cover cover.jpg  # 표지 이미지 포함
    python build_epub_en.py --check            # pandoc 확인
"""
import sys
import types
from pathlib import Path

# ── config_en 을 'config' 로 주입 ─────────────────────────────────────────────
# build_epub.py 가 `from config import ...` 할 때 config_en 값을 읽도록 한다
import config_en as _cfg_en

_config_shim = types.ModuleType("config")
_config_shim.__dict__.update(_cfg_en.__dict__)
sys.modules["config"] = _config_shim

# ── build_epub 임포트 (shim 적용 후) ─────────────────────────────────────────
import build_epub  # noqa: E402

# pandoc 메타데이터를 영문판으로 교체
build_epub.PANDOC_METADATA = """\
---
title: "{title}"
subtitle: "{subtitle}"
author: "{author}"
language: en
rights: "Copyright © 2026 {author}. All rights reserved."
description: "A practitioner's guide to evaluating AI agents for production using the 7-Gate Harness Engineering framework"
publisher: "Self-Published"
date: "2026"
...
"""

# CSS — 영문 세리프 폰트 우선
build_epub.CSS_KDP = """\
body {
    font-family: 'Georgia', 'Times New Roman', serif;
    line-height: 1.75;
    font-size: 1em;
    margin: 1em;
}
h1, h2, h3 { font-family: 'Arial', 'Helvetica', sans-serif; }
code, pre { font-family: 'Courier New', monospace; font-size: 0.9em; }
pre { background: #f5f5f5; padding: 0.8em; border-radius: 4px; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #ccc; padding: 0.4em 0.7em; }
th { background: #eee; }
"""

if __name__ == "__main__":
    build_epub.main()
