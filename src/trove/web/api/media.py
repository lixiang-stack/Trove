from __future__ import annotations

from fastapi import APIRouter, Request

from trove.web.deps import runtime
from trove.web.media import audio_response, cover_response

router = APIRouter()


@router.get(
    "/items/{item_id}/audio",
    responses={
        200: {"content": {"audio/*": {}}, "description": "Audio stream"},
        206: {"content": {"audio/*": {}}, "description": "Partial audio stream"},
    },
)
def api_audio(request: Request, item_id: str):
    return audio_response(runtime(request), item_id)


@router.get("/items/{item_id}/cover")
def api_cover(request: Request, item_id: str):
    return cover_response(runtime(request), item_id)
