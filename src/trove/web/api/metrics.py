from __future__ import annotations

from fastapi import APIRouter, Request, Response

from trove import metrics
from trove.web.deps import runtime

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def api_metrics(request: Request):
    app_runtime = runtime(request)
    payload = metrics.render(
        queue_depths=app_runtime.processing.queue_depths(),
        lease_age_seconds=app_runtime.processing.oldest_lease_age_seconds(),
    )
    return Response(content=payload, media_type=metrics.CONTENT_TYPE_LATEST)
