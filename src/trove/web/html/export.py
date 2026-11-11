from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from trove.web.deps import export_response, runtime

router = APIRouter()


@router.get("/export", include_in_schema=False)
def export_library(
    request: Request, ids: Annotated[list[str] | None, Query()] = None
):
    return export_response(runtime(request), ids)
