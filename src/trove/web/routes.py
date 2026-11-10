from __future__ import annotations

from fastapi import APIRouter

from trove.web import api, html, shell
from trove.web.errors import install_exception_handlers
from trove.web.security import install_middleware

html_router = APIRouter()
html_router.include_router(html.router)
html_router.include_router(shell.router)

api_router = APIRouter(prefix="/api")
api_router.include_router(api.router)

__all__ = [
    "api_router",
    "html_router",
    "install_exception_handlers",
    "install_middleware",
]
