from __future__ import annotations

from fastapi import APIRouter, Query, Request

from trove.domain.links import LinkKind
from trove.errors import ValidationError
from trove.web.deps import runtime
from trove.web.schemas import (
    CollectionCreateRequest,
    CollectionCreateResponse,
    CollectionDeleteResponse,
    CollectionListResponse,
    CollectionSchema,
    LinkInspectRequest,
    LinkInspectResponse,
)

router = APIRouter()


@router.post("/intake/inspect", response_model=LinkInspectResponse)
def api_inspect(request: Request, payload: LinkInspectRequest):
    return runtime(request).inspect.inspect(payload.url).to_dict()


@router.post(
    "/collections",
    response_model=CollectionCreateResponse,
    status_code=201,
)
def api_create_collection(request: Request, payload: CollectionCreateRequest):
    app_runtime = runtime(request)
    inspection = app_runtime.inspect.inspect(payload.url)
    if inspection.kind != LinkKind.COLLECTION:
        raise ValidationError(
            "Link is not a video collection", details={"code": "collection.empty"}
        )
    result = app_runtime.intake.add_collection(inspection)
    return {
        "collection": app_runtime.collections.payload(
            result.collection, include_items=True
        ),
        "added_count": result.added_count,
        "attached_count": result.attached_count,
        "skipped_count": result.skipped_count,
        "run_count": result.run_count,
        "warnings": result.warnings,
    }


@router.get("/collections", response_model=CollectionListResponse)
def api_list_collections(request: Request):
    app_runtime = runtime(request)
    bundles = app_runtime.collections.list_collections()
    return {
        "collections": [
            app_runtime.collections.payload(bundle) for bundle in bundles
        ],
        "count": len(bundles),
    }


@router.get("/collections/{collection_id}", response_model=CollectionSchema)
def api_get_collection(request: Request, collection_id: str):
    app_runtime = runtime(request)
    bundle = app_runtime.collections.get(collection_id)
    return app_runtime.collections.payload(bundle, include_items=True)


@router.delete(
    "/collections/{collection_id}", response_model=CollectionDeleteResponse
)
def api_delete_collection(
    request: Request,
    collection_id: str,
    mode: str = Query("delete_items"),
):
    if mode not in {"delete_items", "ungroup"}:
        raise ValidationError(
            "mode must be delete_items or ungroup",
            details={"code": "collection.invalid_mode"},
        )
    count = runtime(request).collections.delete(
        collection_id, delete_items=mode == "delete_items"
    )
    return {"deleted": True, "deleted_items": count, "mode": mode}


@router.post(
    "/collections/{collection_id}/retry-failed", response_model=CollectionSchema
)
def api_retry_failed(request: Request, collection_id: str):
    app_runtime = runtime(request)
    app_runtime.collections.retry_failed(collection_id)
    bundle = app_runtime.collections.get(collection_id)
    return app_runtime.collections.payload(bundle, include_items=True)
