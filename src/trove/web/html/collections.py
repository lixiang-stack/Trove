from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from trove.errors import ValidationError
from trove.web.deps import render, runtime

router = APIRouter()


@router.get("/collections", include_in_schema=False)
def collections_page(request: Request):
    app_runtime = runtime(request)
    bundles = app_runtime.collections.list_collections()
    payloads = [app_runtime.collections.payload(bundle) for bundle in bundles]
    return render(
        request,
        "collections.html",
        {
            "collections": payloads,
            "collection_count": len(payloads),
            "episode_count": sum(
                payload["episode_count"] for payload in payloads
            ),
            "active_nav": "library",
        },
    )


@router.get("/collections/{collection_id}", include_in_schema=False)
def collection_detail(request: Request, collection_id: str):
    app_runtime = runtime(request)
    bundle = app_runtime.collections.get(collection_id)
    return render(
        request,
        "collection_detail.html",
        {
            "collection": app_runtime.collections.payload(
                bundle, include_items=True
            ),
            "active_nav": "library",
        },
    )


@router.post("/collections/{collection_id}/delete", include_in_schema=False)
def delete_collection(
    request: Request,
    collection_id: str,
    mode: Annotated[str, Form()] = "delete_items",
):
    if mode not in {"delete_items", "ungroup"}:
        raise ValidationError(
            "mode must be delete_items or ungroup",
            details={"code": "collection.invalid_mode"},
        )
    runtime(request).collections.delete(
        collection_id, delete_items=mode == "delete_items"
    )
    return RedirectResponse("/collections", status_code=303)


@router.post("/collections/{collection_id}/retry-failed", include_in_schema=False)
def retry_failed(request: Request, collection_id: str):
    runtime(request).collections.retry_failed(collection_id)
    return RedirectResponse(f"/collections/{collection_id}", status_code=303)


@router.post(
    "/collections/{collection_id}/items/{item_id}/retry", include_in_schema=False
)
def retry_collection_item(request: Request, collection_id: str, item_id: str):
    runtime(request).processing.retry(item_id)
    return RedirectResponse(f"/collections/{collection_id}", status_code=303)
