from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from trove.web.deps import continue_entries, render, run_logs, runtime

router = APIRouter()


@router.get("/continue", include_in_schema=False)
def continue_page(request: Request):
    return render(
        request,
        "continue.html",
        {
            "entries": continue_entries(runtime(request)),
            "active_nav": "continue",
        },
    )


@router.get("/items/{item_id}/read", include_in_schema=False)
def item_read(request: Request, item_id: str, chapter: int | None = None):
    app_runtime = runtime(request)
    bundle = app_runtime.library.get(item_id)
    views = app_runtime.reading.chapters(item_id)
    locator = app_runtime.reading.locator(item_id)
    current = chapter
    if current is None:
        current = locator.chapter_index if locator is not None else 0
    view = next(
        (candidate for candidate in views if candidate.chapter.chapter_index == current),
        views[0] if views else None,
    )
    position = next(
        (index for index, candidate in enumerate(views) if candidate is view), 0
    )
    scroll_ratio = (
        locator.scroll_ratio
        if view is not None
        and locator is not None
        and locator.chapter_index == view.chapter.chapter_index
        else 0.0
    )
    return render(
        request,
        "read.html",
        {
            "bundle": bundle,
            "chapters": views,
            "view": view,
            "scroll_ratio": scroll_ratio,
            "previous_chapter": views[position - 1].chapter.chapter_index
            if position > 0
            else None,
            "next_chapter": (
                views[position + 1].chapter.chapter_index
                if position + 1 < len(views)
                else None
            ),
            "active_nav": "library",
        },
    )


@router.get("/items/{item_id}/listen", include_in_schema=False)
def item_listen(request: Request, item_id: str, replace: int | None = None):
    app_runtime = runtime(request)
    bundle = app_runtime.library.get(item_id)
    transcript = app_runtime.playback.transcript(item_id)
    return render(
        request,
        "listen.html",
        {
            "bundle": bundle,
            "transcript": transcript,
            "replace_count": replace,
            "run_logs": run_logs(app_runtime, bundle),
            "active_nav": "library",
        },
    )


@router.post("/items/{item_id}/transcript/replace", include_in_schema=False)
def replace_transcript(
    request: Request,
    item_id: str,
    old: Annotated[str, Form()] = "",
    new: Annotated[str, Form()] = "",
):
    count, first_seq = runtime(request).playback.replace_transcript_text(
        item_id, old=old, new=new
    )
    target = f"/items/{item_id}/listen?replace={count}"
    if first_seq is not None:
        target += f"#segment-{first_seq}"
    return RedirectResponse(target, status_code=303)
