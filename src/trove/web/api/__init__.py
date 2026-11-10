from __future__ import annotations

from fastapi import APIRouter

from trove.web.api import (
    auth,
    continue_routes,
    export,
    health,
    items,
    media,
    runs,
    search,
    uploads,
)

router = APIRouter()
router.include_router(auth.router)
router.include_router(continue_routes.router)
router.include_router(health.router)
router.include_router(export.router)
router.include_router(items.router)
router.include_router(media.router)
router.include_router(runs.router)
router.include_router(search.router)
router.include_router(uploads.router)
