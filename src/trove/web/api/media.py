from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from trove.web.deps import runtime
from trove.web.media import audio_response, cover_response

router = APIRouter()

_MEDIA_HEADERS = {
    "ETag": {"description": "Quoted SHA-256", "schema": {"type": "string"}},
    "Accept-Ranges": {"description": "Always `bytes`", "schema": {"type": "string"}},
    "Cache-Control": {"description": "Always `private`", "schema": {"type": "string"}},
    "X-Content-Type-Options": {"description": "Always `nosniff`", "schema": {"type": "string"}},
}


@router.get(
    "/items/{item_id}/audio",
    response_class=FileResponse,
    responses={
        200: {
            "content": {"audio/*": {}},
            "description": "Audio stream",
            "headers": _MEDIA_HEADERS,
        },
        206: {
            "content": {"audio/*": {}},
            "description": "Partial audio stream",
            "headers": {
                **_MEDIA_HEADERS,
                "Content-Range": {
                    "description": "Inclusive byte range and total size",
                    "schema": {"type": "string"},
                },
            },
        },
        416: {"description": "Requested range is not satisfiable"},
    },
)
def api_audio(request: Request, item_id: str):
    return audio_response(runtime(request), item_id)


@router.get(
    "/items/{item_id}/cover",
    response_class=FileResponse,
    responses={
        200: {
            "content": {"image/*": {}},
            "description": "Cover image",
            "headers": _MEDIA_HEADERS,
        },
        404: {"description": "Cover is missing"},
    },
)
def api_cover(request: Request, item_id: str):
    return cover_response(runtime(request), item_id)
