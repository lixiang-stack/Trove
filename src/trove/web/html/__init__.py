from __future__ import annotations

from fastapi import APIRouter

from trove.web.html import add, auth, export, items, library

router = APIRouter()
router.include_router(auth.router)
router.include_router(library.router)
router.include_router(items.router)
router.include_router(add.router)
router.include_router(export.router)
