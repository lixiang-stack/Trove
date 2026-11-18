from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from trove.domain.links import LinkKind
from trove.errors import TroveError, ValidationError
from trove.web.deps import add_context, render, runtime

router = APIRouter()


@router.get("/add", include_in_schema=False)
def add_page(request: Request):
    return render(request, "add.html", add_context())


@router.post("/add/link/preview", include_in_schema=False)
def preview_link(request: Request, url: Annotated[str, Form()]):
    app_runtime = runtime(request)
    try:
        inspection = app_runtime.inspect.inspect(url)
    except TroveError as exc:
        if request.headers.get("HX-Request") == "true":
            return render(
                request,
                "link_preview.html",
                {"link_error": exc.message, "url": url},
                status_code=exc.status_code,
            )
        return render(
            request,
            "add.html",
            add_context(link_error=exc.message, link_url=url),
            status_code=exc.status_code,
        )
    if request.headers.get("HX-Request") == "true":
        return render(
            request,
            "link_preview.html",
            {"inspection": inspection, "url": url},
        )
    return render(
        request,
        "add.html",
        add_context(inspection=inspection, link_url=url),
    )


@router.post("/add/link", include_in_schema=False)
def add_link(request: Request, url: Annotated[str, Form()]):
    app_runtime = runtime(request)
    try:
        inspection = app_runtime.inspect.inspect(url)
        if inspection.kind == LinkKind.VIDEO:
            bundle, _ = app_runtime.intake.add_video_url(inspection.canonical_url)
            return RedirectResponse(f"/items/{bundle.item.id}", status_code=303)
        if inspection.kind == LinkKind.EBOOK:
            bundle, _ = app_runtime.intake.add_epub_url(
                url, canonical_url=inspection.canonical_url
            )
            return RedirectResponse(f"/items/{bundle.item.id}", status_code=303)
        if inspection.kind == LinkKind.COLLECTION:
            result = app_runtime.intake.add_collection(inspection)
            return RedirectResponse(
                f"/collections/{result.collection.collection.id}", status_code=303
            )
        if inspection.kind == LinkKind.PODCAST_FEED:
            return render(
                request,
                "add.html",
                add_context(
                    inspection=inspection,
                    link_url=url,
                    link_error="请选择一集播客入库。",
                ),
            )
        raise ValidationError(
            "Please choose one episode from the podcast feed",
            details={"code": "feed.select_episode"},
        )
    except TroveError as exc:
        return render(
            request,
            "add.html",
            add_context(link_error=exc.message, link_url=url),
            status_code=exc.status_code,
        )


@router.post("/add/url", include_in_schema=False)
def add_url(request: Request, url: Annotated[str, Form()]):
    app_runtime = runtime(request)
    try:
        bundle, _ = app_runtime.intake.add_video_url(url)
    except TroveError as exc:
        return render(
            request,
            "add.html",
            add_context(error=exc.message),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/items/{bundle.item.id}", status_code=303)


@router.post("/add/path", include_in_schema=False)
def add_path(request: Request, path: Annotated[str, Form()]):
    app_runtime = runtime(request)
    try:
        bundle, _ = app_runtime.intake.add_host_path(path)
    except TroveError as exc:
        return render(
            request,
            "add.html",
            add_context(error=exc.message),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/items/{bundle.item.id}", status_code=303)


@router.post("/add/upload", include_in_schema=False)
async def add_upload(request: Request, file: Annotated[UploadFile, File()]):
    app_runtime = runtime(request)
    try:
        record = app_runtime.uploads.save_stream(
            file.file, file.filename or "upload", content_type=file.content_type
        )
        bundle, _ = app_runtime.intake.add_upload(record.upload_id)
    except TroveError as exc:
        return render(
            request,
            "add.html",
            add_context(error=exc.message),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/items/{bundle.item.id}", status_code=303)


@router.post("/add/feed/preview", include_in_schema=False)
def preview_feed(request: Request, feed_url: Annotated[str, Form()]):
    app_runtime = runtime(request)
    try:
        feed = app_runtime.intake.preview_feed(feed_url)
    except TroveError as exc:
        if request.headers.get("HX-Request") == "true":
            return render(
                request,
                "feed_preview.html",
                {"feed": None, "feed_error": exc.message, "feed_url": feed_url},
            )
        return render(
            request,
            "add.html",
            add_context(error=exc.message),
            status_code=exc.status_code,
        )
    if request.headers.get("HX-Request") == "true":
        return render(
            request,
            "feed_preview.html",
            {"feed": feed, "feed_url": feed_url, "feed_error": None},
        )
    return render(
        request,
        "add.html",
        add_context(feed=feed, feed_url=feed_url),
    )


@router.post("/add/podcast", include_in_schema=False)
def add_podcast(
    request: Request,
    feed_url: Annotated[str, Form()],
    episode_guid: Annotated[str, Form()] = "",
    enclosure_url: Annotated[str, Form()] = "",
):
    app_runtime = runtime(request)
    try:
        bundle, _ = app_runtime.intake.add_podcast_episode(
            feed_url, episode_guid or None, enclosure_url or None
        )
    except TroveError as exc:
        return render(
            request,
            "add.html",
            add_context(error=exc.message),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/items/{bundle.item.id}", status_code=303)
