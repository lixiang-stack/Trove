from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from trove.web import api, html, pwa, shell
from trove.web.errors import install_exception_handlers
from trove.web.schemas import ErrorResponse
from trove.web.security import install_middleware

html_router = APIRouter()
html_router.include_router(pwa.router)
html_router.include_router(html.router)
html_router.include_router(shell.router)

COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication required"},
    403: {"model": ErrorResponse, "description": "Cross-site request rejected"},
    404: {"model": ErrorResponse, "description": "Resource not found"},
    409: {"model": ErrorResponse, "description": "Conflicting state"},
    422: {"model": ErrorResponse, "description": "Validation failed"},
    429: {"model": ErrorResponse, "description": "Rate limited"},
    500: {"model": ErrorResponse, "description": "Internal error"},
}
api_router = APIRouter(prefix="/api", responses=COMMON_ERROR_RESPONSES)
api_router.include_router(api.router)

__all__ = [
    "api_router",
    "html_router",
    "install_exception_handlers",
    "install_middleware",
]
