"""
FastAPI application factory for agent-eval serve.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

from .loader import ResultSet, load_results
from .routers import data as data_router
from .routers import export as export_router
from .routers import stream as stream_router
from .routers import transparency as transparency_router
from .routers import golden as golden_router

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def reload_results(app: FastAPI) -> None:
    """Re-scan the results directory and update app state."""
    app.state.result_set = load_results(app.state.results_dir)


def create_app(
    results_dir: Path,
    title: str = "Agent Evaluator Dashboard",
    watch: bool = False,
    version: str = "0.5.1",
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

    # Routers
    app.include_router(data_router.router)
    app.include_router(export_router.router)
    app.include_router(stream_router.router)
    app.include_router(transparency_router.router)
    app.include_router(golden_router.router)

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
