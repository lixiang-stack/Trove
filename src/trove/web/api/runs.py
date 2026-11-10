from __future__ import annotations

from fastapi import APIRouter, Request

from trove.db.models import Item, Run
from trove.errors import NotFoundError
from trove.services.library import item_bundle
from trove.web.deps import runtime

router = APIRouter()


@router.get("/runs/{run_id}")
def api_run(request: Request, run_id: str):
    app_runtime = runtime(request)
    with app_runtime.sessions() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise NotFoundError("Processing Run not found")
        item = session.get(Item, run.item_id)
        if item is None:
            raise NotFoundError("Content not found")
        bundle = item_bundle(session, item)
        payload = app_runtime.library.run_payload(bundle)
    return {
        "run": payload,
        "item": {"id": item.id, "title": item.title},
    }


@router.post("/runs/{run_id}/cancel")
def api_cancel_run(request: Request, run_id: str):
    app_runtime = runtime(request)
    with app_runtime.sessions() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise NotFoundError("Processing Run not found")
        item_id = run.item_id
    app_runtime.processing.cancel(run_id)
    bundle = app_runtime.library.get(item_id)
    return app_runtime.library.payload(bundle)
