from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from trove.web.deps import runtime
from trove.web.schemas import FeedPreviewRequest

router = APIRouter()


@router.post("/uploads")
async def api_upload(
    request: Request,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str | None, Form()] = None,
):
    record = runtime(request).uploads.save_stream(
        file.file,
        file.filename or "upload",
        kind=kind,
        content_type=file.content_type,
    )
    return {
        "upload_id": record.upload_id,
        "filename": record.filename,
        "sha256": record.sha256,
        "size": record.size,
        "kind": record.kind,
    }


@router.post("/feeds/preview")
def api_feed_preview(request: Request, payload: FeedPreviewRequest):
    feed = runtime(request).intake.preview_feed(payload.url)
    return {
        "title": feed.title,
        "author": feed.author,
        "link": feed.link,
        "episodes": [
            {
                "guid": episode.guid,
                "title": episode.title,
                "author": episode.author,
                "published_at": episode.published_at,
                "duration_sec": episode.duration_sec,
                "enclosure_url": episode.enclosure_url,
                "enclosure_type": episode.enclosure_type,
                "enclosure_size": episode.enclosure_size,
            }
            for episode in feed.episodes
        ],
    }
