"""
FastAPI application factory for agent-eval serve.
"""
from __future__ import annotations

import os
import secrets
import urllib.request
from contextlib import asynccontextmanager
from html import escape as _html_escape
from pathlib import Path
from typing import Optional
from urllib.parse import quote as _urlquote

try:
    from importlib.metadata import version as _pkg_version
    _VERSION = _pkg_version("agent-evaluator")
except Exception:
    _VERSION = "0.6.0"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# SPEC-005: 대시보드 옵트인 인증 — 쿠키 이름
_AUTH_COOKIE_NAME = "ae_auth"


def _login_page_html(next_path: str = "/", error: bool = False) -> str:
    """자체 완결형 로그인 페이지 — 외부 static 에셋/Jinja 템플릿에 의존하지 않는다."""
    next_escaped = _html_escape(next_path, quote=True)
    error_html = (
        '<p style="color:#f87171;margin:0 0 12px;font-size:13px">Invalid token.</p>'
        if error else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Agent Evaluator — Login</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0f1117;color:#e2e4f0;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
.box{{background:#1a1d27;border:1px solid #2d3148;border-radius:10px;padding:32px;width:320px}}
h1{{font-size:16px;margin:0 0 16px}}
input{{width:100%;padding:8px;margin-bottom:12px;background:#22263a;border:1px solid #2d3148;
color:#e2e4f0;border-radius:6px;box-sizing:border-box;font-size:14px}}
button{{width:100%;padding:8px;background:#6c8ef5;border:none;border-radius:6px;color:#fff;
font-weight:600;cursor:pointer;font-size:14px}}
</style></head><body>
<div class="box">
<h1>🔒 Agent Evaluator Dashboard</h1>
{error_html}
<form method="post" action="/login">
<input type="hidden" name="next" value="{next_escaped}">
<input type="password" name="token" placeholder="Access token" autofocus required>
<button type="submit">Sign in</button>
</form>
</div>
</body></html>"""


class BearerOrCookieAuthMiddleware(BaseHTTPMiddleware):
    """SPEC-005: 옵트인 대시보드 인증.

    Authorization: Bearer <token> 헤더(API/curl 용) 또는 로그인 후 발급되는
    HttpOnly 쿠키(브라우저 페이지 탐색 용) 둘 중 하나가 일치하면 통과시킨다.
    /login 자체와 CORS preflight(OPTIONS)는 예외 — 그 외 모든 라우트(정적 파일 포함)에
    동일하게 적용된다.
    """

    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path == "/login":
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        bearer_ok = auth_header.startswith("Bearer ") and secrets.compare_digest(
            auth_header[len("Bearer "):], self._token
        )
        cookie_val = request.cookies.get(_AUTH_COOKIE_NAME, "")
        cookie_ok = bool(cookie_val) and secrets.compare_digest(cookie_val, self._token)

        if bearer_ok or cookie_ok:
            return await call_next(request)

        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            next_path = request.url.path
            if request.url.query:
                next_path += f"?{request.url.query}"
            return RedirectResponse(
                url=f"/login?next={_urlquote(next_path, safe='')}", status_code=302
            )
        # REQ-4: 토큰 값/힌트를 응답 바디에 노출하지 않는다.
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

from .loader import load_results
from .routers import data as data_router
from .routers import export as export_router
from .routers import stream as stream_router
from .routers import transparency as transparency_router
from .routers import golden as golden_router
from .routers import config as config_router
from .routers import webhook as webhook_router
from .routers import conversation as conversation_router
from .routers import alerts as alerts_router
from .routers import feedback as feedback_router
from .routers import anomaly as anomaly_router
from .routers import cost as cost_router

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
    "qrcode.min.js":    "https://cdn.jsdelivr.net/npm/qrcode@1.5.1/build/qrcode.min.js",
}


def _setup_offline_assets(app: FastAPI) -> None:
    """Download CDN assets once and mount them at /static."""
    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    missing = [name for name in _OFFLINE_ASSETS if not (_STATIC_DIR / name).exists()]
    if missing:
        print(f"[offline] Downloading {len(missing)} CDN assets...")
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
    auth_token: Optional[str] = None,
) -> FastAPI:
    # ------------------------------------------------------------------ #
    # Lifespan: file watcher startup / shutdown
    # ------------------------------------------------------------------ #
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if watch:
            from .watcher import FileWatcher
            watcher = FileWatcher(results_dir)
            watcher.start()
            app.state.watcher = watcher

            # Hook: reload result_set on every file change
            original_broadcast = watcher._broadcast

            def _reload_and_broadcast(event: str) -> None:
                reload_results(app)
                original_broadcast(event)

            watcher._broadcast = _reload_and_broadcast

        yield

        if watch and app.state.watcher:
            app.state.watcher.stop()

    app = FastAPI(title=title, version=version, docs_url="/api/docs",
                  redoc_url="/api/redoc", openapi_version="3.1.0",
                  lifespan=lifespan)

    # CORS — localhost-only (dashboard is never exposed to the public internet)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8765", "http://127.0.0.1:8765",
                       "http://localhost:*", "http://127.0.0.1:*"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # HTML 응답 캐시 완전 차단 (브라우저 캐시로 인한 구버전 HTML 서빙 방지)
    class NoCacheHTMLMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            ct = response.headers.get("content-type", "")
            if "text/html" in ct:
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            return response

    app.add_middleware(NoCacheHTMLMiddleware)

    # SPEC-005: 옵트인 대시보드 인증 — auth_token 미지정 시 기존 동작(무인증) 그대로 유지
    if auth_token:
        app.add_middleware(BearerOrCookieAuthMiddleware, token=auth_token)

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
    app.include_router(conversation_router.router)
    app.include_router(alerts_router.router)
    app.include_router(feedback_router.router)
    app.include_router(anomaly_router.router)
    app.include_router(cost_router.router)

    # Templates
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    # ------------------------------------------------------------------ #
    # HTML routes
    # ------------------------------------------------------------------ #
    # serve 명령어 삭제 시 마이그레이션 가이드:
    #   1. dashboard.html.j2 파일 삭제
    #   2. 아래 "/" 라우트를 RedirectResponse("/dashboard") 로 교체
    #   3. /slides, /sdk-docs, /api/* 라우트는 그대로 유지 (독립적)
    # ------------------------------------------------------------------ #

    # SPEC-005: 로그인 라우트 — auth_token 미설정 시에도 등록되지만, 그 경우 middleware가
    # 없어 어차피 도달 전에 통과되므로 무해하다.
    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page(request: Request):
        next_path = request.query_params.get("next", "/")
        error = request.query_params.get("error") == "1"
        return HTMLResponse(_login_page_html(next_path, error))

    @app.post("/login", include_in_schema=False)
    async def login_submit(request: Request):
        form = await request.form()
        token = str(form.get("token", ""))
        next_path = str(form.get("next", "") or "/")
        if auth_token and secrets.compare_digest(token, auth_token):
            resp = RedirectResponse(url=next_path, status_code=303)
            resp.set_cookie(
                _AUTH_COOKIE_NAME, auth_token,
                httponly=True, samesite="lax", max_age=86400 * 7,
            )
            return resp
        return RedirectResponse(
            url=f"/login?error=1&next={_urlquote(next_path, safe='')}", status_code=303
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard(request: Request):
        resp = templates.TemplateResponse(
            request,
            "dashboard.html.j2",
            {
                "title":   app.state.title,
                "version": app.state.version,
                "watch":   watch,
                "offline": app.state.offline,
            },
        )
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp

    @app.get("/slides", response_class=HTMLResponse, include_in_schema=False)
    async def slides(request: Request):
        return templates.TemplateResponse(
            request,
            "slides.html.j2",
            {
                "title":   app.state.title,
                "version": app.state.version,
                "offline": app.state.offline,
            },
        )

    @app.get("/sdk-docs", response_class=HTMLResponse, include_in_schema=False)
    async def sdk_docs(request: Request):
        return templates.TemplateResponse(
            request,
            "sdk_docs.html.j2",
            {
                "title":   app.state.title,
                "version": app.state.version,
                "offline": app.state.offline,
            },
        )

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard2(request: Request):
        resp = templates.TemplateResponse(
            request,
            "dashboard2.html.j2",
            {
                "title":   app.state.title,
                "version": app.state.version,
                "watch":   watch,
                "offline": app.state.offline,
            },
        )
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp

    return app
