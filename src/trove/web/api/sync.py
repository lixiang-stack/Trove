from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from trove.web.deps import runtime
from trove.web.schemas import ManifestResponse, SyncStateResponse

router = APIRouter()


@router.get("/sync/manifest", response_model=ManifestResponse)
def sync_manifest(
    request: Request,
    cursor: str = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    return runtime(request).sync.manifest(cursor=cursor or None, limit=limit)


@router.get("/sync/state", response_model=SyncStateResponse)
def sync_state(
    request: Request,
    cursor: str = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    return runtime(request).sync.state(cursor=cursor or None, limit=limit)
