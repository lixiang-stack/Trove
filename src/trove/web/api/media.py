from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from trove.web.api.headers import CONTENT_RANGE_HEADER, FILE_RESPONSE_HEADERS
from trove.web.deps import runtime
from trove.web.media import audio_response, cover_response

router = APIRouter()


@router.get(
    "/items/{item_id}/audio",
    response_class=FileResponse,
    responses={
        200: {
            "content": {"audio/*": {}},
            "description": "Audio stream",
            "headers": FILE_RESPONSE_HEADERS,
        },
        206: {
            "content": {"audio/*": {}},
            "description": "Partial audio stream",
            "headers": {
                **FILE_RESPONSE_HEADERS,
                "Content-Range": CONTENT_RANGE_HEADER,
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
            "headers": FILE_RESPONSE_HEADERS,
        },
        404: {"description": "Cover is missing"},
    },
)
def api_cover(request: Request, item_id: str):
    return cover_response(runtime(request), item_id)
