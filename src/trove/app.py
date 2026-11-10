from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles

from trove import __version__
from trove.composition import Ports, build_runtime
from trove.config import Config
from trove.db.engine import fts5_available
from trove.logging_setup import configure_logging
from trove.web.routes import (
    api_router,
    html_router,
    install_exception_handlers,
    install_middleware,
)
from trove.web.security import PUBLIC_PATHS
from trove.web.templating import STATIC_DIR


def create_app(config: Config, ports: Ports | None = None) -> FastAPI:
    config.ensure_layout()
    configure_logging(
        config, console=os.environ.get("TROVE_LOG_CONSOLE", "1") not in {"0", "false"}
    )
    runtime = build_runtime(config, ports)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not fts5_available(runtime.engine):
            raise RuntimeError(
                "This SQLite build lacks FTS5. Use the Python 3.12 managed by uv, "
                "or install SQLite with FTS5."
            )
        yield

    app = FastAPI(
        title="Trove",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
    )
    app.state.runtime = runtime
    app.openapi = lambda: _openapi(app)  # type: ignore[method-assign]
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    install_middleware(app)
    install_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(html_router)
    return app


def _openapi(app: FastAPI) -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    components = schema.setdefault("components", {})
    components.setdefault("securitySchemes", {})["cookieAuth"] = {
        "type": "apiKey",
        "in": "cookie",
        "name": "trove_session",
    }
    for path, operations in schema.get("paths", {}).items():
        if not path.startswith("/api/") or path in PUBLIC_PATHS:
            continue
        for method, operation in operations.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                operation.setdefault("security", [{"cookieAuth": []}])
    app.openapi_schema = schema
    return schema
