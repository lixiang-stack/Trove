from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from trove.web.deps import render, run_logs, runtime

router = APIRouter()


@router.get("/items/{item_id}", include_in_schema=False)
def item_detail(request: Request, item_id: str):
    app_runtime = runtime(request)
    bundle = app_runtime.library.get(item_id)
    return render(
        request,
        "item_detail.html",
        {
            "bundle": bundle,
            "run_logs": run_logs(app_runtime, bundle),
            "active_nav": "library",
        },
    )


@router.get("/items/{item_id}/status", include_in_schema=False)
def item_status(request: Request, item_id: str, context: str = "row"):
    app_runtime = runtime(request)
    bundle = app_runtime.library.get(item_id)
    if context in {"panel", "detail", "listen"}:
        return render(
            request,
            "status.html",
            {
                "bundle": bundle,
                "context": "panel",
                "run_logs": run_logs(app_runtime, bundle),
            },
        )
    return render(
        request,
        "status.html",
        {"bundle": bundle, "context": "row"},
    )


@router.post("/items/{item_id}/edit", include_in_schema=False)
def edit_item(
    request: Request,
    item_id: str,
    title: Annotated[str, Form()] = "",
    author: Annotated[str, Form()] = "",
):
    runtime(request).library.update_metadata(item_id, title=title, author=author)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.post("/items/{item_id}/tags/add", include_in_schema=False)
def add_tag(request: Request, item_id: str, tag: Annotated[str, Form()]):
    runtime(request).library.add_tag(item_id, tag)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.post("/items/{item_id}/tags/delete", include_in_schema=False)
def delete_tag(request: Request, item_id: str, tag: Annotated[str, Form()]):
    runtime(request).library.remove_tag(item_id, tag)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.post("/items/{item_id}/delete", include_in_schema=False)
def delete_item(request: Request, item_id: str):
    runtime(request).library.delete(item_id)
    return RedirectResponse("/library", status_code=303)


@router.post("/items/{item_id}/state", include_in_schema=False)
def set_item_state(request: Request, item_id: str, state: Annotated[str, Form()]):
    runtime(request).playback.set_consumption_state(item_id, state)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.post("/items/{item_id}/retry", include_in_schema=False)
def retry_item(request: Request, item_id: str):
    runtime(request).processing.retry(item_id)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.post("/items/{item_id}/reprocess", include_in_schema=False)
def reprocess_item(
    request: Request,
    item_id: str,
    from_stage: Annotated[str, Form()] = "organizing",
):
    runtime(request).processing.reprocess(item_id, from_stage)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.post("/items/{item_id}/cancel", include_in_schema=False)
def cancel_item(request: Request, item_id: str):
    runtime(request).processing.cancel_item(item_id)
    return RedirectResponse(f"/items/{item_id}", status_code=303)
