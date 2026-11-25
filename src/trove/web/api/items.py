from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, Response

from trove.composition import Runtime
from trove.domain.links import LinkKind
from trove.domain.reading import BookLocator
from trove.errors import ValidationError
from trove.services.idempotency import (
    BeginState,
    normalize_key,
    request_fingerprint,
)
from trove.services.library import ItemBundle
from trove.web.deps import runtime
from trove.web.schemas import (
    BookChapterResponse,
    ItemCreateRequest,
    ItemCreateResponse,
    ItemListResponse,
    ItemPatchRequest,
    ItemSchema,
    MutationResponse,
    ProgressRequest,
    ReprocessRequest,
    ReprocessResponse,
    TagListResponse,
    TagRequest,
    TagsRequest,
    TranscriptResponse,
)

router = APIRouter()
logger = logging.getLogger("trove.idempotency")


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


@router.post(
    "/items",
    response_model=ItemCreateResponse,
    responses={201: {"model": ItemCreateResponse, "description": "Item created"}},
)
def api_create_item(
    request: Request,
    payload: ItemCreateRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    app_runtime = runtime(request)
    key = normalize_key(idempotency_key)
    started_token: int | None = None
    if key is not None:
        result = app_runtime.idempotency.begin(
            key,
            method="POST",
            path=request.url.path,
            request_hash=request_fingerprint(
                "POST", request.url.path, payload.model_dump(mode="json")
            ),
        )
        if result.state is BeginState.REPLAY:
            return JSONResponse(
                result.payload or {},
                status_code=result.status_code or 200,
                headers={"Idempotency-Replayed": "true"},
            )
        started_token = result.token
    try:
        bundle, duplicated = _create_item(app_runtime, payload)
        body = {
            "item": app_runtime.library.payload(bundle),
            "deduplicated": duplicated,
        }
        status_code = 200 if duplicated else 201
        if key is not None and started_token is not None:
            try:
                app_runtime.idempotency.complete(
                    key,
                    token=started_token,
                    status_code=status_code,
                    payload=body,
                )
            except Exception:  # noqa: BLE001 - response is already committed
                logger.exception(
                    "failed to store idempotent response",
                    extra={"request_id": getattr(request.state, "request_id", None)},
                )
        return JSONResponse(body, status_code=status_code)
    except Exception:
        if key is not None and started_token is not None:
            try:
                app_runtime.idempotency.abort(key, token=started_token)
            except Exception:  # noqa: BLE001 - preserve the original error
                logger.exception(
                    "failed to abort idempotent request",
                    extra={"request_id": getattr(request.state, "request_id", None)},
                )
        raise


def _create_item(app_runtime: Runtime, payload: ItemCreateRequest) -> tuple[ItemBundle, bool]:
    if payload.kind == "url":
        if not payload.url:
            raise ValidationError("Missing url")
        return app_runtime.intake.add_video_url(payload.url)
    if payload.kind == "path":
        if not payload.path:
            raise ValidationError("Missing path")
        return app_runtime.intake.add_host_path(payload.path)
    if payload.kind == "upload":
        if not payload.upload_id:
            raise ValidationError("Missing upload_id")
        return app_runtime.intake.add_upload(payload.upload_id)
    if payload.kind == "podcast":
        if not payload.feed_url or not (payload.episode_guid or payload.enclosure_url):
            raise ValidationError("Missing feed_url or episode identifier")
        return app_runtime.intake.add_podcast_episode(
            payload.feed_url, payload.episode_guid, payload.enclosure_url
        )
    if payload.kind == "ebook_url":
        if not payload.url:
            raise ValidationError("Missing url")
        inspection = app_runtime.inspect.inspect(payload.url)
        if inspection.kind != LinkKind.EBOOK:
            raise ValidationError(
                "Link is not an EPUB file", details={"code": "ebook.invalid_type"}
            )
        return app_runtime.intake.add_epub_url(
            payload.url, canonical_url=inspection.canonical_url
        )
    raise ValidationError(
        "kind must be one of url, path, upload, podcast, or ebook_url"
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
        app_runtime.sync.replace_tags(
            item_id,
            tags=payload.tags or [],
            device_id=request.state.device_id,
        )
        bundle = app_runtime.library.get(item_id)
    return app_runtime.library.payload(bundle)


@router.delete("/items/{item_id}", status_code=204)
def api_delete_item(request: Request, item_id: str):
    runtime(request).library.delete(item_id)
    return Response(status_code=204)


@router.post("/items/{item_id}/tags", response_model=ItemSchema)
def api_add_tag(request: Request, item_id: str, payload: TagRequest):
    result = runtime(request).sync.add_tag(
        item_id,
        payload.tag,
        device_id=request.state.device_id,
    )
    return result["item"]


@router.put("/items/{item_id}/tags", response_model=MutationResponse)
def api_replace_tags(
    request: Request,
    item_id: str,
    payload: TagsRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    return runtime(request).sync.replace_tags(
        item_id,
        tags=payload.tags,
        client_updated_at=payload.client_updated_at,
        device_id=request.state.device_id,
        idempotency_key=idempotency_key,
    )


@router.delete("/items/{item_id}/tags/{tag:path}", response_model=ItemSchema)
def api_delete_tag(request: Request, item_id: str, tag: str):
    result = runtime(request).sync.remove_tag(
        item_id,
        tag,
        device_id=request.state.device_id,
    )
    return result["item"]


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


@router.put("/items/{item_id}/progress", response_model=MutationResponse)
def api_progress(
    request: Request,
    item_id: str,
    payload: ProgressRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    app_runtime = runtime(request)
    if payload.book_locator is not None and payload.book_locator.schema_version != 2:
        raise ValidationError(
            "Unsupported book locator schema",
            details={"code": "book.locator_schema"},
        )
    locator = (
        BookLocator(
            chapter_index=payload.book_locator.chapter_index,
            paragraph_index=payload.book_locator.paragraph_index,
            scroll_ratio=payload.book_locator.scroll_ratio,
            epub_href=payload.book_locator.epub_href,
            epub_progression=payload.book_locator.epub_progression,
            epub_total_progression=payload.book_locator.epub_total_progression,
        )
        if payload.book_locator is not None
        else None
    )
    state_only = (
        payload.position_sec is None
        and payload.book_locator is None
        and payload.consumption_state is not None
    )
    return app_runtime.sync.apply_progress(
        item_id,
        position_sec=payload.position_sec,
        book_locator=locator,
        consumption_state=payload.consumption_state,
        client_updated_at=payload.client_updated_at,
        device_id=request.state.device_id,
        idempotency_key=idempotency_key,
        require_progress=not state_only,
    )


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
