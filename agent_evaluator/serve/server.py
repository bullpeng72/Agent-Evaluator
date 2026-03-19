"""
FastAPI application factory for agent-eval serve.
"""
from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path
from typing import Optional

try:
    from importlib.metadata import version as _pkg_version, PackageNotFoundError
    _VERSION = _pkg_version("agent-evaluator")
except Exception:
    _VERSION = "0.5.3"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

from .loader import ResultSet, load_results
from .routers import data as data_router
from .routers import export as export_router
from .routers import stream as stream_router
from .routers import transparency as transparency_router
from .routers import golden as golden_router
from .routers import config as config_router
from .routers import webhook as webhook_router

_TEMPLATES_DIR = Path(__file__).parent / "templates"
# CDN 에셋 캐시는 사용자 홈 디렉토리에 저장 — pip 설치 경로(site-packages)는 읽기 전용일 수 있음
_STATIC_DIR = Path(
    os.environ.get("AGENT_EVALUATOR_CACHE_DIR",
                   str(Path.home() / ".cache" / "agent-evaluator" / "static"))
)

# CDN assets to cache for --offline mode
_OFFLINE_ASSETS = {
    "alpine.min.js":    "https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js",
    "plotly.min.js":    "https://cdn.jsdelivr.net/npm/plotly.js-dist@2.35.2/plotly.min.js",
    "tabulator.min.js": "https://cdn.jsdelivr.net/npm/tabulator-tables@6.3.0/dist/js/tabulator.min.js",
    "tabulator.min.css":"https://cdn.jsdelivr.net/npm/tabulator-tables@6.3.0/dist/css/tabulator_midnight.min.css",
    "tabulator_simple.min.css": "https://cdn.jsdelivr.net/npm/tabulator-tables@6.3.0/dist/css/tabulator_simple.min.css",
    "chart.min.js":     "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js",
    "reveal.js":        "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.js",
    "reveal.css":       "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.css",
    "reveal-reset.css": "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reset.css",
    "reveal-night.css": "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/theme/night.css",
    "reveal-white.css": "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/theme/white.css",
    "qrcode.min.js":    "https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js",
}


def _setup_offline_assets(app: FastAPI) -> None:
    """Download CDN assets once and mount them at /static."""
    _STATIC_DIR.mkdir(exist_ok=True)
    missing = [name for name in _OFFLINE_ASSETS if not (_STATIC_DIR / name).exists()]
    if missing:
        print(f"[offline] {len(missing)}개 CDN 에셋 다운로드 중...")
        for name in missing:
            url = _OFFLINE_ASSETS[name]
            dest = _STATIC_DIR / name
            try:
                urllib.request.urlretrieve(url, dest)
                print(f"  ✅  {name}")
            except Exception as e:
                print(f"  ❌  {name}: {e}")
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def reload_results(app: FastAPI) -> None:
    """Re-scan the results directory and update app state."""
    app.state.result_set = load_results(app.state.results_dir)


def create_app(
    results_dir: Path,
    title: str = "Agent Evaluator Dashboard",
    watch: bool = False,
    version: str = _VERSION,
    offline: bool = False,
) -> FastAPI:
    app = FastAPI(title=title, version=version, docs_url="/api/docs",
                  redoc_url="/api/redoc", openapi_version="3.1.0")

    # CORS — allow same-origin + localhost dev access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # State
    app.state.results_dir = results_dir
    app.state.title = title
    app.state.version = version
    app.state.result_set = load_results(results_dir)
    app.state.watcher = None
    app.state.offline = offline

    # Offline static assets
    if offline:
        _setup_offline_assets(app)

    # Routers
    app.include_router(data_router.router)
    app.include_router(export_router.router)
    app.include_router(stream_router.router)
    app.include_router(transparency_router.router)
    app.include_router(golden_router.router)
    app.include_router(config_router.router)
    app.include_router(webhook_router.router)

    # Templates
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    # ------------------------------------------------------------------ #
    # File watcher (optional)
    # ------------------------------------------------------------------ #
    if watch:
        from .watcher import FileWatcher
        watcher = FileWatcher(results_dir)

        @app.on_event("startup")
        def start_watcher() -> None:
            watcher.start()
            app.state.watcher = watcher

            # Hook: reload result_set on every file change
            original_broadcast = watcher._broadcast

            def _reload_and_broadcast(event: str) -> None:
                reload_results(app)
                original_broadcast(event)

            watcher._broadcast = _reload_and_broadcast

        @app.on_event("shutdown")
        def stop_watcher() -> None:
            watcher.stop()

    # ------------------------------------------------------------------ #
    # HTML routes
    # ------------------------------------------------------------------ #

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return templates.TemplateResponse(
            "dashboard.html.j2",
            {
                "request": request,
                "title":   app.state.title,
                "version": app.state.version,
                "watch":   watch,
            },
        )

    @app.get("/slides", response_class=HTMLResponse)
    async def slides(request: Request):
        return templates.TemplateResponse(
            "slides.html.j2",
            {
                "request": request,
                "title":   app.state.title,
                "version": app.state.version,
            },
        )

    @app.get("/sdk-docs", response_class=HTMLResponse)
    async def sdk_docs(request: Request):
        return templates.TemplateResponse(
            "sdk_docs.html.j2",
            {
                "request": request,
                "title":   app.state.title,
                "version": app.state.version,
            },
        )

    return app
