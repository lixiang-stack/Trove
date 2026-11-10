from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from trove.web.templating import STATIC_DIR

router = APIRouter()


@router.get("/manifest.webmanifest", include_in_schema=False)
def web_app_manifest():
    return FileResponse(
        STATIC_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@router.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="text/javascript",
        headers={
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-store",
        },
    )
