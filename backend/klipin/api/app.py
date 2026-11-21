import secrets
from collections.abc import Sequence
from pathlib import Path

import structlog
from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from klipin.api.errors import ApiError, install_error_handlers
from klipin.api.routes import events as events_routes
from klipin.api.routes import jobs as jobs_routes
from klipin.api.routes import secrets as secrets_routes
from klipin.api.routes import settings as settings_routes
from klipin.api.routes import streams as streams_routes
from klipin.api.routes import system as system_routes
from klipin.api.security import LocalOnlyMiddleware
from klipin.config import get_config

DIST_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"
log = structlog.get_logger(__name__)


def create_app(token: str | None = None, dist_dir: Path = DIST_DIR,
               port: int | None = None, routers: Sequence[APIRouter] = ()) -> FastAPI:
    token = token or secrets.token_urlsafe(32)
    port = port or get_config().klipin_port
    app = FastAPI(title="Klipin")
    app.state.token = token
    install_error_handlers(app)
    app.add_middleware(LocalOnlyMiddleware, token=token, port=port)
    # Router API wajib dipasang sebelum mount SPA di "/" yang menangkap semua path.
    for router in (settings_routes.router, secrets_routes.router, jobs_routes.router,
                   events_routes.router, system_routes.router, streams_routes.router,
                   *routers):
        app.include_router(router)

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        page = dist_dir / "index.html"
        if not page.is_file():
            raise ApiError(503, "INTERNAL_ERROR",
                           "Antarmuka belum dibuild. Jalankan `cd frontend && pnpm build`.")
        meta = f'<meta name="klipin-token" content="{token}">'
        html = page.read_text(encoding="utf-8").replace("</head>", meta + "</head>", 1)
        # Token berganti tiap start, jadi halaman tidak boleh di-cache.
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=dist_dir), name="spa")
    else:
        log.warning("frontend/dist tidak ditemukan; jalankan `cd frontend && pnpm build`.")
    return app


app = create_app()
