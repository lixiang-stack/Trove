from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
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
    )
    app.state.runtime = runtime
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    install_middleware(app)
    install_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(html_router)
    return app
