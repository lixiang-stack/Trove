from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from trove.domain.reading import BookLocator
from trove.errors import ValidationError
from trove.web.deps import runtime
from trove.web.schemas import (
    BookChapterResponse,
    ItemCreateRequest,
    ItemCreateResponse,
    ItemListResponse,
    ItemPatchRequest,
    ItemSchema,
    ProgressRequest,
    ProgressResponse,
    ReprocessRequest,
    ReprocessResponse,
    TagListResponse,
    TagRequest,
    TranscriptResponse,
)

router = APIRouter()


@router.get("/items", response_model=ItemListResponse)
def api_list_items(
    request: Request,
    sort: str = "recent_added",
    state: str = "",
    type: str = Query("", alias="type"),
    consumption: str = "",
    tag: str = "",
    source: str = "",
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    app_runtime = runtime(request)
    if sort not in {"recent_added", "recent_consumed"}:
        sort = "recent_added"
    states = {value for value in state.split(",") if value}
    bundles = app_runtime.library.list_items(
        sort=sort,
        states=states or None,
        item_type=type or None,
        consumption=consumption or None,
        platform=source or None,
        tag=tag or None,
    )
    total = len(bundles)
    end = offset + limit if limit is not None else None
    page = bundles[offset:end]
    return {
        "items": [app_runtime.library.payload(bundle) for bundle in page],
        "count": len(page),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/items", response_model=ItemCreateResponse)
def api_create_item(request: Request, payload: ItemCreateRequest):
    app_runtime = runtime(request)
    if payload.kind == "url":
        if not payload.url:
            raise ValidationError("Missing url")
        bundle, duplicated = app_runtime.intake.add_video_url(payload.url)
    elif payload.kind == "path":
        if not payload.path:
            raise ValidationError("Missing path")
        bundle, duplicated = app_runtime.intake.add_host_path(payload.path)
    elif payload.kind == "upload":
        if not payload.upload_id:
            raise ValidationError("Missing upload_id")
        bundle, duplicated = app_runtime.intake.add_upload(payload.upload_id)
    elif payload.kind == "podcast":
        if not payload.feed_url or not (payload.episode_guid or payload.enclosure_url):
            raise ValidationError("Missing feed_url or episode identifier")
        bundle, duplicated = app_runtime.intake.add_podcast_episode(
            payload.feed_url, payload.episode_guid, payload.enclosure_url
        )
    else:
        raise ValidationError("kind must be one of url, path, upload, or podcast")
    return JSONResponse(
        {"item": app_runtime.library.payload(bundle), "deduplicated": duplicated},
        status_code=200 if duplicated else 201,
    )


@router.get("/items/{item_id}", response_model=ItemSchema)
def api_get_item(request: Request, item_id: str):
    app_runtime = runtime(request)
    return app_runtime.library.payload(app_runtime.library.get(item_id))


@router.patch("/items/{item_id}", response_model=ItemSchema)
def api_patch_item(request: Request, item_id: str, payload: ItemPatchRequest):
    app_runtime = runtime(request)
    fields = payload.model_fields_set
    bundle = app_runtime.library.get(item_id)
    if "title" in fields or "author" in fields:
        bundle = app_runtime.library.update_metadata(
            item_id,
            title=payload.title if "title" in fields else None,
            author=payload.author if "author" in fields else None,
        )
    if "tags" in fields:
        bundle = app_runtime.library.replace_tags(item_id, payload.tags or [])
    return app_runtime.library.payload(bundle)


@router.delete("/items/{item_id}", status_code=204)
def api_delete_item(request: Request, item_id: str):
    runtime(request).library.delete(item_id)
    return Response(status_code=204)


@router.post("/items/{item_id}/tags", response_model=ItemSchema)
def api_add_tag(request: Request, item_id: str, payload: TagRequest):
    app_runtime = runtime(request)
    bundle = app_runtime.library.add_tag(item_id, payload.tag)
    return app_runtime.library.payload(bundle)


@router.delete("/items/{item_id}/tags/{tag:path}", response_model=ItemSchema)
def api_delete_tag(request: Request, item_id: str, tag: str):
    app_runtime = runtime(request)
    bundle = app_runtime.library.remove_tag(item_id, tag)
    return app_runtime.library.payload(bundle)


@router.get("/tags", response_model=TagListResponse)
def api_tags(request: Request):
    app_runtime = runtime(request)
    return {
        "tags": [
            {"name": name, "count": count}
            for name, count in app_runtime.library.tag_counts()
        ]
    }


@router.get("/items/{item_id}/transcript", response_model=TranscriptResponse)
def api_transcript(request: Request, item_id: str):
    app_runtime = runtime(request)
    return {
        "item_id": item_id,
        "segments": app_runtime.playback.transcript(item_id),
    }


@router.get(
    "/items/{item_id}/book/chapters/{chapter_index}",
    response_model=BookChapterResponse,
)
def api_book_chapter(request: Request, item_id: str, chapter_index: int):
    view = runtime(request).reading.chapter(item_id, chapter_index)
    return {
        "item_id": item_id,
        "chapter_index": view.chapter.chapter_index,
        "title": view.chapter.title,
        "html": view.chapter.html,
        "text": view.chapter.text,
        "paragraphs": [paragraph.text for paragraph in view.paragraphs],
    }


@router.put("/items/{item_id}/progress", response_model=ProgressResponse)
def api_progress(request: Request, item_id: str, payload: ProgressRequest):
    app_runtime = runtime(request)
    bundle: Any = None
    if payload.book_locator is not None:
        app_runtime.reading.save_progress(
            item_id,
            BookLocator(
                chapter_index=payload.book_locator.chapter_index,
                paragraph_index=payload.book_locator.paragraph_index,
                scroll_ratio=payload.book_locator.scroll_ratio,
            ),
            consumption_state=payload.consumption_state,
        )
        bundle = app_runtime.library.get(item_id)
    if payload.position_sec is not None:
        bundle = app_runtime.playback.update_progress(
            item_id,
            position_sec=payload.position_sec,
            consumption_state=payload.consumption_state,
        )
    if bundle is None:
        raise ValidationError(
            "Missing progress position", details={"code": "progress.missing"}
        )
    return {"ok": True, "item": app_runtime.library.payload(bundle)}


@router.post("/items/{item_id}/retry", response_model=ItemSchema)
def api_retry(request: Request, item_id: str):
    app_runtime = runtime(request)
    app_runtime.processing.retry(item_id)
    bundle = app_runtime.library.get(item_id)
    return app_runtime.library.payload(bundle)


@router.post(
    "/items/{item_id}/reprocess", status_code=202, response_model=ReprocessResponse
)
def api_reprocess(request: Request, item_id: str, payload: ReprocessRequest):
    app_runtime = runtime(request)
    run = app_runtime.processing.reprocess(item_id, payload.from_stage)
    bundle = app_runtime.library.get(item_id)
    return {"run_id": run.id, "item": app_runtime.library.payload(bundle)}


@router.post("/items/{item_id}/cancel", response_model=ItemSchema)
def api_cancel_item(request: Request, item_id: str):
    app_runtime = runtime(request)
    app_runtime.processing.cancel_item(item_id)
    bundle = app_runtime.library.get(item_id)
    return app_runtime.library.payload(bundle)
