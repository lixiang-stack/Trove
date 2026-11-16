from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from trove.web.deps import export_response, runtime

router = APIRouter()


@router.get(
    "/export",
    response_class=FileResponse,
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "ZIP archive of the selected Content Packages",
        }
    },
)
def api_export(request: Request, ids: Annotated[list[str] | None, Query()] = None):
    return export_response(runtime(request), ids)
