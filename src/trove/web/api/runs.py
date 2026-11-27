from __future__ import annotations

from fastapi import APIRouter, Request

from trove.web.deps import runtime
from trove.web.schemas import ItemSchema, RunDetailResponse

router = APIRouter()


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def api_run(request: Request, run_id: str):
    bundle, payload = runtime(request).library.run_detail(run_id)
    return {
        "run": payload,
        "item": {"id": bundle.item.id, "title": bundle.item.title},
    }


@router.post("/runs/{run_id}/cancel", response_model=ItemSchema)
def api_cancel_run(request: Request, run_id: str):
    app_runtime = runtime(request)
    run = app_runtime.processing.cancel(run_id)
    bundle = app_runtime.library.get(run.item_id)
    return app_runtime.library.payload(bundle)
